import os
import sys
import json
import subprocess
import pytest
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = WORKSPACE_ROOT / "scripts" / "protocol_graph.py"

if not SCRIPT_PATH.exists():
    alt_path = Path(__file__).resolve().parent.parent / "scripts" / "protocol_graph.py"
    if alt_path.exists():
        SCRIPT_PATH = alt_path
        WORKSPACE_ROOT = alt_path.parent.parent
    else:
        pytest.skip("scripts/protocol_graph.py not present in container environment", allow_module_level=True)

STATE_FILE = WORKSPACE_ROOT / ".protocol_state.json"


@pytest.fixture(scope="session", autouse=True)
def preserve_external_state():
    """Preserve developer's active protocol state across the test session."""
    backup = None
    if STATE_FILE.exists():
        backup = STATE_FILE.read_bytes()
    yield
    if backup is not None:
        STATE_FILE.write_bytes(backup)
    elif STATE_FILE.exists():
        STATE_FILE.unlink()


@pytest.fixture(autouse=True)
def clean_state_per_test():
    """Ensure test isolation between individual test runs."""
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    yield
    if STATE_FILE.exists():
        STATE_FILE.unlink()


def run_protocol_cli(*args, env=None):
    cmd = [sys.executable, str(SCRIPT_PATH)] + list(args)
    return subprocess.run(cmd, cwd=str(WORKSPACE_ROOT), capture_output=True, text=True, env=env)


def test_protocol_graph_start_and_status():
    res = run_protocol_cli("start", "--type", "bug", "--name", "repro-flow-dates")
    assert res.returncode == 0
    assert "Protocol State Graph Initialized" in res.stdout
    assert STATE_FILE.exists()

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)
    assert state["workflow_type"] == "bug"
    assert state["task_name"] == "repro-flow-dates"
    assert state["active_node"] == "PHASE_0_INTAKE"
    assert state["guards"]["red_state_verified"] is False

    res_status = run_protocol_cli("status")
    assert res_status.returncode == 0
    assert "QUANT PROTOCOL STATE GRAPH DASHBOARD" in res_status.stdout
    assert "BUG" in res_status.stdout


def test_protocol_graph_plan_approve():
    run_protocol_cli("start", "--type", "bug", "--name", "plan-test")
    res = run_protocol_cli("plan-approve")
    assert res.returncode == 0
    assert "PHASE_1_RED_GATE" in res.stdout

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)
    assert state["guards"]["plan_approved"] is True
    assert state["active_node"] == "PHASE_1_RED_GATE"


def test_red_gate_rejects_passing_test(tmp_path):
    passing_test = tmp_path / "test_dummy_pass.py"
    passing_test.write_text("def test_always_pass():\n    assert True\n", encoding="utf-8")

    run_protocol_cli("start", "--type", "bug", "--name", "negative-red-test")
    run_protocol_cli("plan-approve")

    res = run_protocol_cli("red", "--test", str(passing_test))
    assert res.returncode == 1
    assert "RED GATE FAILED" in res.stderr
    assert "unexpectedly PASSED" in res.stderr

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)
    assert state["guards"]["red_state_verified"] is False


def test_red_gate_accepts_failing_test_and_green_gate_verifies(tmp_path):
    test_file = tmp_path / "test_dummy_lifecycle.py"
    test_file.write_text("def test_lifecycle():\n    assert False, 'Simulated bug failure'\n", encoding="utf-8")

    run_protocol_cli("start", "--type", "bug", "--name", "lifecycle-test")
    run_protocol_cli("plan-approve")

    res_red = run_protocol_cli("red", "--test", str(test_file))
    assert res_red.returncode == 0
    assert "RED GATE PASSED" in res_red.stdout
    assert "PHASE_2_SURGICAL_FIX" in res_red.stdout

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)
    assert state["guards"]["red_state_verified"] is True
    assert state["active_node"] == "PHASE_2_SURGICAL_FIX"

    res_green_fail = run_protocol_cli("green")
    assert res_green_fail.returncode == 1
    assert "GREEN GATE FAILED" in res_green_fail.stderr

    test_file.write_text("def test_lifecycle():\n    assert True\n", encoding="utf-8")
    res_green_pass = run_protocol_cli("green")
    assert res_green_pass.returncode == 0
    assert "GREEN GATE PASSED" in res_green_pass.stdout
    assert "PHASE_4_AUDIT" in res_green_pass.stdout

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)
    assert state["guards"]["green_state_verified"] is True
    assert state["active_node"] == "PHASE_4_AUDIT"


def test_staging_and_prod_authorization_lifecycle():
    run_protocol_cli("start", "--type", "feature", "--name", "auth-feature")
    run_protocol_cli("plan-approve")
    
    res_staging = run_protocol_cli("staging-verify")
    assert res_staging.returncode == 0
    assert "PHASE_6_PRODUCTION_GATE" in res_staging.stdout

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)
    assert state["guards"]["staging_verified"] is True
    assert state["guards"]["production_authorized"] is False

    res_prod = run_protocol_cli("prod-authorize")
    assert res_prod.returncode == 0
    assert "Authorized" in res_prod.stdout

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)
    assert state["guards"]["production_authorized"] is True


def test_protocol_graph_reset():
    run_protocol_cli("start", "--type", "bug", "--name", "reset-me")
    assert STATE_FILE.exists()
    res = run_protocol_cli("reset")
    assert res.returncode == 0
    assert not STATE_FILE.exists()


def test_check_commit_gate_when_no_staged_app_files(monkeypatch):
    # When no files or only docs are staged, check-commit passes with 0
    env = os.environ.copy()
    env["PROTOCOL_TEST_STAGED_FILES"] = "README.md\ndocs/architecture.md"
    res = run_protocol_cli("check-commit", env=env)
    assert res.returncode == 0


def test_staging_bug_spawns_child_and_suspends_parent():
    run_protocol_cli("start", "--type", "feature", "--name", "parent-feature")
    run_protocol_cli("plan-approve")
    run_protocol_cli("audit")
    
    # Feature is now at PHASE_5_STAGING
    res_bug = run_protocol_cli("staging-bug", "--name", "radar-empty-staging")
    assert res_bug.returncode == 0
    assert "[INTERCEPT] STAGING DEFECT SUB-WORKFLOW INITIALIZED" in res_bug.stdout
    assert "PHASE_1_RED_GATE" in res_bug.stdout

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)
    assert state["workflow_type"] == "bug"
    assert state["task_name"] == "radar-empty-staging"
    assert state["active_node"] == "PHASE_1_RED_GATE"
    assert state["parent_workflow"] is not None
    assert state["parent_workflow"]["task_name"] == "parent-feature"
    assert state["parent_workflow"]["active_node"] == "PHASE_5_STAGING"

    # Status shows nested defect layout
    res_status = run_protocol_cli("status")
    assert res_status.returncode == 0
    assert "NESTED STAGING DEFECT" in res_status.stdout
    assert "parent-feature" in res_status.stdout


def test_staging_bug_blocks_prod_authorize():
    run_protocol_cli("start", "--type", "feature", "--name", "feature-x")
    run_protocol_cli("plan-approve")
    run_protocol_cli("audit")
    run_protocol_cli("staging-bug", "--name", "bug-y")

    res_prod = run_protocol_cli("prod-authorize")
    assert res_prod.returncode == 1
    assert "PROD BLOCKED" in res_prod.stderr
    assert "Cannot authorize production while nested staging defect" in res_prod.stderr


def test_staging_bug_pre_commit_enforces_red_green_gates():
    run_protocol_cli("start", "--type", "feature", "--name", "feature-z")
    run_protocol_cli("plan-approve")
    run_protocol_cli("audit")
    run_protocol_cli("staging-bug", "--name", "bug-z")

    env = os.environ.copy()
    env["PROTOCOL_TEST_STAGED_FILES"] = "gateway/app/main.py"
    res_commit = run_protocol_cli("check-commit", env=env)
    assert res_commit.returncode == 1
    assert "RED reproduction gate not verified" in res_commit.stderr


def test_staging_bug_lifecycle_and_parent_restoration(tmp_path):
    run_protocol_cli("start", "--type", "feature", "--name", "radar-tab3")
    run_protocol_cli("plan-approve")
    run_protocol_cli("audit")
    run_protocol_cli("staging-bug", "--name", "radar-fetch-fix")

    # 1. RED Gate
    test_file = tmp_path / "test_reproduce_radar.py"
    test_file.write_text("def test_radar_bug():\n    assert False, 'Expected fetch fail'\n", encoding="utf-8")

    res_red = run_protocol_cli("red", "--test", str(test_file))
    assert res_red.returncode == 0
    assert "RED GATE PASSED" in res_red.stdout

    # 2. GREEN Gate
    test_file.write_text("def test_radar_bug():\n    assert True\n", encoding="utf-8")
    res_green = run_protocol_cli("green")
    assert res_green.returncode == 0
    assert "GREEN GATE PASSED" in res_green.stdout

    # 3. Audit Gate
    env = os.environ.copy()
    env["PROTOCOL_TEST_AUDIT_DIFF"] = f"{test_file.name}\ngateway/app/main.py"
    res_audit = run_protocol_cli("audit", env=env)
    assert res_audit.returncode == 0

    # 4. Staging Verify on Child -> Pops & Restores Parent
    res_v = run_protocol_cli("staging-verify")
    assert res_v.returncode == 0
    assert "[RESOLVED] STAGING DEFECT COMPLETED & VERIFIED" in res_v.stdout
    assert "radar-tab3" in res_v.stdout

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        restored = json.load(f)
    assert restored["workflow_type"] == "feature"
    assert restored["task_name"] == "radar-tab3"
    assert restored["active_node"] == "PHASE_5_STAGING"
    assert restored["parent_workflow"] is None
    assert any("STAGING_DEFECT_RESOLVED" in a["event"] for a in restored["audit_trail"])

    # 5. Parent completes staging & prod authorize
    res_v2 = run_protocol_cli("staging-verify")
    assert res_v2.returncode == 0
    assert "PHASE_6_PRODUCTION_GATE" in res_v2.stdout

    res_prod = run_protocol_cli("prod-authorize")
    assert res_prod.returncode == 0
    assert "Authorized" in res_prod.stdout


def test_staging_bug_cancel_restores_parent():
    run_protocol_cli("start", "--type", "feature", "--name", "feature-alpha")
    run_protocol_cli("plan-approve")
    run_protocol_cli("audit")
    run_protocol_cli("staging-bug", "--name", "bug-accidental")

    res_cancel = run_protocol_cli("cancel-bug")
    assert res_cancel.returncode == 0
    assert "Staging defect cancelled" in res_cancel.stdout

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)
    assert state["task_name"] == "feature-alpha"
    assert state["parent_workflow"] is None


def test_start_bug_auto_intercepts_at_staging():
    run_protocol_cli("start", "--type", "feature", "--name", "feature-beta")
    run_protocol_cli("plan-approve")
    run_protocol_cli("audit")
    
    # Run start --type bug instead of staging-bug
    res_auto = run_protocol_cli("start", "--type", "bug", "--name", "defect-beta")
    assert res_auto.returncode == 0
    assert "Automatically intercepting as a Nested Staging Defect" in res_auto.stdout

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)
    assert state["workflow_type"] == "bug"
    assert state["task_name"] == "defect-beta"
    assert state["parent_workflow"]["task_name"] == "feature-beta"


def test_reviewer_dealbreaker_intercept_and_resolve(tmp_path):
    run_protocol_cli("start", "--type", "feature", "--name", "feature-gamma")
    run_protocol_cli("plan-approve")

    # Reviewer intercepts with dealbreaker
    res_deal = run_protocol_cli("reviewer-dealbreaker", "--name", "partition-key-incompatible", "--reviewer", "architect")
    assert res_deal.returncode == 0
    assert "REVIEWER DEALBREAKER SUB-WORKFLOW INITIALIZED" in res_deal.stdout

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)
    assert state["workflow_type"] == "bug"
    assert "[ARCHITECT] partition-key-incompatible" in state["task_name"]
    assert state["parent_workflow"]["task_name"] == "feature-gamma"
    assert state["active_node"] == "PHASE_1_RED_GATE"

    # RED Gate
    repro = tmp_path / "test_repro.py"
    repro.write_text("def test_fail(): assert False", encoding="utf-8")
    res_red = run_protocol_cli("red", "--test", str(repro))
    assert res_red.returncode == 0

    # GREEN Gate
    repro.write_text("def test_fail(): assert True", encoding="utf-8")
    res_green = run_protocol_cli("green")
    assert res_green.returncode == 0

    # Audit & Resolve Defect
    env = os.environ.copy()
    env["PROTOCOL_TEST_AUDIT_DIFF"] = f"{repro.name}\n"
    res_audit = run_protocol_cli("audit", env=env)
    assert res_audit.returncode == 0

    res_resolve = run_protocol_cli("resolve-defect")
    assert res_resolve.returncode == 0
    assert "DEFECT COMPLETED & VERIFIED" in res_resolve.stdout

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        parent_state = json.load(f)
    assert parent_state["task_name"] == "feature-gamma"
    assert parent_state["parent_workflow"] is None


