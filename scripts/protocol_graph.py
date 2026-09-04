#!/usr/bin/env python3
"""
scripts/protocol_graph.py - Deterministic State Graph Engine for Quant System Protocols
Enforces: Bug Remediation, Feature Development, and Pre-Commit Invariants
"""
import sys
import os
import json
import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = WORKSPACE_ROOT / ".protocol_state.json"


def get_current_state():
    if not STATE_FILE.exists():
        return None
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] Error reading .protocol_state.json: {e}", file=sys.stderr)
        return None


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def append_audit(state, event, details=""):
    now = datetime.now(timezone.utc).isoformat()
    state.setdefault("audit_trail", []).append({
        "timestamp": now,
        "event": event,
        "node": state.get("active_node"),
        "details": details
    })


def cmd_start(args):
    workflow_type = args.type
    name = args.name or "unnamed-task"

    if workflow_type == "bug":
        active_node = "PHASE_0_INTAKE"
    elif workflow_type == "feature":
        active_node = "PHASE_0_INTAKE"
    else:
        active_node = "PHASE_0_POLISH"

    state = {
        "schema_version": "1.0.0",
        "workflow_id": f"WF-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        "workflow_type": workflow_type,
        "task_name": name,
        "active_node": active_node,
        "reproduction_test": None,
        "guards": {
            "plan_approved": False,
            "red_state_verified": False,
            "green_state_verified": False,
            "adversarial_audit_passed": False,
            "staging_verified": False,
            "production_authorized": False
        },
        "audit_trail": []
    }
    append_audit(state, "WORKFLOW_INITIALIZED", f"Started {workflow_type} workflow: {name}")
    save_state(state)
    print(f"[OK] Protocol State Graph Initialized:")
    print(f"   ID:     {state['workflow_id']}")
    print(f"   Type:   {state['workflow_type'].upper()}")
    print(f"   Task:   {state['task_name']}")
    print(f"   Node:   {state['active_node']}")


def cmd_status(args):
    state = get_current_state()
    if not state:
        print("[INFO] No active protocol workflow. Run 'python scripts/protocol_graph.py start --help'.")
        return

    print("==================================================================")
    print(f"  QUANT PROTOCOL STATE GRAPH DASHBOARD ({state['workflow_id']})")
    print("==================================================================")
    print(f"Workflow Type:    {state.get('workflow_type', '').upper()}")
    print(f"Task Name:        {state.get('task_name', '')}")
    print(f"Active Node:      {state.get('active_node', '')}")
    print(f"Reproduction Test:{state.get('reproduction_test') or '[None Registered]'}")
    print("\nGuards & Checkpoints:")
    for k, v in state.get("guards", {}).items():
        status_icon = "[PASS]" if v else "[WAIT]"
        print(f"  {status_icon} {k:<40}: {v}")

    print("\nAudit Trail:")
    for entry in state.get("audit_trail", [])[-5:]:
        print(f"  • [{entry['timestamp'][:19]}] {entry['event']:<25} ({entry.get('node', '')}) - {entry.get('details', '')}")
    print("==================================================================")


def cmd_plan_approve(args):
    state = get_current_state()
    if not state:
        print("[ERROR] No active workflow to approve.", file=sys.stderr)
        sys.exit(1)

    state["guards"]["plan_approved"] = True
    if state["workflow_type"] == "bug":
        state["active_node"] = "PHASE_1_RED_GATE"
    elif state["workflow_type"] == "feature":
        state["active_node"] = "PHASE_2_SEQUENCING"

    append_audit(state, "PLAN_APPROVED", "User/Director approved implementation plan")
    save_state(state)
    print(f"[OK] Plan Approved. Graph advanced to node: {state['active_node']}.")


def _run_test_file(test_path):
    resolved = WORKSPACE_ROOT / test_path if not os.path.isabs(test_path) else Path(test_path)
    if not resolved.exists():
        print(f"[ERROR] Test file not found: {test_path}", file=sys.stderr)
        sys.exit(1)

    # Choose runner
    if str(test_path).endswith(".py"):
        venv_py = WORKSPACE_ROOT / "gateway" / ".venv" / "Scripts" / "python.exe"
        if not venv_py.exists():
            venv_py = WORKSPACE_ROOT / "gateway" / ".venv" / "bin" / "python"
        py_bin = str(venv_py) if venv_py.exists() else sys.executable
        cmd = [py_bin, "-m", "pytest", str(resolved), "-v"]
    elif str(test_path).endswith(".js"):
        cmd = ["node", str(resolved)]
    else:
        print(f"[ERROR] Unsupported test file format: {test_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[RUN] Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=str(WORKSPACE_ROOT), capture_output=True, text=True)
    return res.returncode, res.stdout, res.stderr


def cmd_red(args):
    state = get_current_state()
    if not state:
        print("[ERROR] No active workflow. Run 'start' first.", file=sys.stderr)
        sys.exit(1)

    test_path = args.test
    rc, stdout, stderr = _run_test_file(test_path)

    if rc != 0:
        print(f"\n[OK] RED GATE PASSED: Reproduction test failed as expected (exit code {rc}).")
        print(f"   Failure verified & captured.")
        state["reproduction_test"] = str(test_path)
        state["guards"]["red_state_verified"] = True
        state["guards"]["green_state_verified"] = False
        state["active_node"] = "PHASE_2_SURGICAL_FIX"
        append_audit(state, "RED_STATE_VERIFIED", f"Test {test_path} failed with exit code {rc}")
        save_state(state)
        print(f"   Graph advanced to node: PHASE_2_SURGICAL_FIX.")
        print(f"   Source code modification is now UNLOCKED under strict YAGNI.")
    else:
        print(f"\n[FAIL] RED GATE FAILED: Reproduction test unexpectedly PASSED with exit code 0.", file=sys.stderr)
        print("   A valid RED gate requires a verified failure reproducing the bug.", file=sys.stderr)
        sys.exit(1)


def cmd_green(args):
    state = get_current_state()
    if not state:
        print("[ERROR] No active workflow.", file=sys.stderr)
        sys.exit(1)

    test_path = state.get("reproduction_test")
    if not test_path or not state["guards"].get("red_state_verified"):
        print("[ERROR] Cannot verify GREEN: RED state was never proven or no test registered.", file=sys.stderr)
        sys.exit(1)

    rc, stdout, stderr = _run_test_file(test_path)

    if rc == 0:
        print(f"\n[OK] GREEN GATE PASSED: Reproduction test now passes (exit code 0).")
        print(f"   Bug resolution verified symmetrically.")
        state["guards"]["green_state_verified"] = True
        state["active_node"] = "PHASE_4_AUDIT"
        append_audit(state, "GREEN_STATE_VERIFIED", f"Test {test_path} passed with exit code 0")
        save_state(state)
        print(f"   Graph advanced to node: PHASE_4_AUDIT.")
    else:
        print(f"\n[FAIL] GREEN GATE FAILED: Reproduction test is still failing (exit code {rc}).", file=sys.stderr)
        sys.exit(1)


def cmd_audit(args):
    state = get_current_state()
    if not state:
        print("[ERROR] No active workflow.", file=sys.stderr)
        sys.exit(1)

    res = subprocess.run(["git", "diff", "--name-only"], cwd=str(WORKSPACE_ROOT), capture_output=True, text=True)
    modified_files = [f.strip() for f in res.stdout.splitlines() if f.strip()]

    print(f"[AUDIT] Checking {len(modified_files)} modified files...")
    if state["workflow_type"] == "bug":
        repro_test = state.get("reproduction_test")
        if repro_test:
            repro_name = Path(repro_test).name
            res_staged = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=str(WORKSPACE_ROOT), capture_output=True, text=True)
            all_diff = res.stdout + "\n" + res_staged.stdout
            if repro_name not in all_diff:
                print(f"[ERROR] AUDIT FAILED: Reproduction test ({repro_test}) is not present in diff.", file=sys.stderr)
                sys.exit(1)

    state["guards"]["adversarial_audit_passed"] = True
    state["active_node"] = "PHASE_5_STAGING"
    append_audit(state, "AUDIT_APPROVED", f"Diff approved: {len(modified_files)} files modified")
    save_state(state)
    print("[OK] Adversarial Audit Passed. Ready for Staging deployment.")


def cmd_staging_verify(args):
    state = get_current_state()
    if not state:
        print("[ERROR] No active workflow.", file=sys.stderr)
        sys.exit(1)

    state["guards"]["staging_verified"] = True
    state["active_node"] = "PHASE_6_PRODUCTION_GATE"
    append_audit(state, "STAGING_VERIFIED", "Staging in-situ health confirmed on port 8096")
    save_state(state)
    print("[OK] Staging Verified. Graph advanced to: PHASE_6_PRODUCTION_GATE.")
    print("[LOCK] Production push to master is locked awaiting explicit human command.")


def cmd_prod_authorize(args):
    state = get_current_state()
    if not state:
        print("[ERROR] No active workflow.", file=sys.stderr)
        sys.exit(1)

    state["guards"]["production_authorized"] = True
    append_audit(state, "PROD_AUTHORIZED", "Human authorized promotion to production")
    save_state(state)
    print("[OK] Production Promotion Authorized by Engineering Director.")


def cmd_check_commit(args):
    """Invoked by .git/hooks/pre-commit to enforce protocol invariants physically."""
    if os.environ.get("PROTOCOL_TEST_STAGED_FILES") is not None:
        staged = [f.strip() for f in os.environ["PROTOCOL_TEST_STAGED_FILES"].splitlines() if f.strip()]
    else:
        res = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=str(WORKSPACE_ROOT), capture_output=True, text=True)
        staged = [f.strip() for f in res.stdout.splitlines() if f.strip()]

    if not staged:
        sys.exit(0)

    # Check if app code is modified
    app_files = [f for f in staged if f.startswith("gateway/app/") or f.startswith("frontend/src/")]
    if not app_files:
        sys.exit(0)

    state = get_current_state()
    if not state:
        print("\n[STOP] ==================================================================", file=sys.stderr)
        print("   [GIT PRE-COMMIT BLOCKED BY PROTOCOL GRAPH]", file=sys.stderr)
        print("   Application source code was modified without an active protocol state.", file=sys.stderr)
        print("   Run: python scripts/protocol_graph.py start --type [bug|feature] --name <task>", file=sys.stderr)
        print("==================================================================\n", file=sys.stderr)
        sys.exit(1)

    wtype = state.get("workflow_type")
    guards = state.get("guards", {})

    if wtype == "bug":
        if not guards.get("red_state_verified"):
            print("\n[STOP] [PRE-COMMIT BLOCKED] RED reproduction gate not verified.", file=sys.stderr)
            print("   Protocol requires a proven failing test before code can be committed.", file=sys.stderr)
            print("   Run: python scripts/protocol_graph.py red --test <test_path>", file=sys.stderr)
            sys.exit(1)
        if not guards.get("green_state_verified"):
            print("\n[STOP] [PRE-COMMIT BLOCKED] GREEN resolution gate not verified.", file=sys.stderr)
            print("   Protocol requires proving that the reproduction test passes.", file=sys.stderr)
            print("   Run: python scripts/protocol_graph.py green", file=sys.stderr)
            sys.exit(1)
        repro_test = state.get("reproduction_test")
        if repro_test:
            repro_name = Path(repro_test).name
            if not any(repro_name in s for s in staged):
                print(f"\n[STOP] [PRE-COMMIT BLOCKED] Reproduction test ({repro_test}) is NOT staged with the fix.", file=sys.stderr)
                print(f"   Stage the reproduction test: git add {repro_test}", file=sys.stderr)
                sys.exit(1)

    elif wtype == "feature":
        if not guards.get("plan_approved"):
            print("\n[STOP] [PRE-COMMIT BLOCKED] Feature implementation plan was not approved.", file=sys.stderr)
            print("   Run: python scripts/protocol_graph.py plan-approve", file=sys.stderr)
            sys.exit(1)

    print("[OK] [Protocol Gate] Pre-commit invariants strictly verified. Commit allowed.")
    sys.exit(0)


def cmd_reset(args):
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    print("[OK] Protocol state graph reset cleanly.")


def main():
    parser = argparse.ArgumentParser(description="Quant System Protocol State Graph Engine")
    subparsers = parser.add_subparsers(dest="command")

    p_start = subparsers.add_parser("start")
    p_start.add_argument("--type", choices=["bug", "feature", "polish"], default="bug", help="Workflow type")
    p_start.add_argument("--name", default="unnamed", help="Task name / issue description")

    subparsers.add_parser("status")
    subparsers.add_parser("plan-approve")

    p_red = subparsers.add_parser("red")
    p_red.add_argument("--test", required=True, help="Path to reproduction test file")

    subparsers.add_parser("green")
    subparsers.add_parser("audit")
    subparsers.add_parser("staging-verify")
    subparsers.add_parser("prod-authorize")
    subparsers.add_parser("check-commit")
    subparsers.add_parser("reset")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "start": cmd_start,
        "status": cmd_status,
        "plan-approve": cmd_plan_approve,
        "red": cmd_red,
        "green": cmd_green,
        "audit": cmd_audit,
        "staging-verify": cmd_staging_verify,
        "prod-authorize": cmd_prod_authorize,
        "check-commit": cmd_check_commit,
        "reset": cmd_reset
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
