import os
import sys
import json
import subprocess
import pytest
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = WORKSPACE_ROOT / "scripts" / "protocol_graph.py"
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
