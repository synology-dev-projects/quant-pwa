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


NODE_SKILL_MAP = {
    "PHASE_0_INTAKE": {
        "skill": "captain-orchestrator",
        "path": ".agents/skills/captain-orchestrator/SKILL.md",
        "hint": "Align on user intent, clarify requirements via Grill-Me, triage bug vs feature."
    },
    "PHASE_0_POLISH": {
        "skill": "captain-orchestrator",
        "path": ".agents/skills/captain-orchestrator/SKILL.md",
        "hint": "Review polish items and prepare lightweight plan."
    },
    "PHASE_1_RED_GATE": {
        "skill": "repro-scaffolder",
        "path": ".agents/skills/repro-scaffolder/SKILL.md",
        "hint": "Write failing reproduction test using mocks/fixtures before any source edit."
    },
    "PHASE_2_SEQUENCING": {
        "skill": "captain-orchestrator",
        "path": ".agents/skills/captain-orchestrator/SKILL.md",
        "hint": "Sequence module dependencies and establish contract tests."
    },
    "PHASE_2_SURGICAL_FIX": {
        "skill": "domain-router",
        "hint": "Apply minimal surgical fix following domain skill runbooks (UI: bloomberg-terminal-components, DB: timescale-options-analytics, API: fastapi-sse-streaming)."
    },
    "PHASE_3_EXECUTION": {
        "skill": "domain-router",
        "hint": "Implement feature components conforming to domain skill standards (UI: bloomberg-terminal-components, DB: timescale-options-analytics, API: fastapi-sse-streaming)."
    },
    "PHASE_4_AUDIT": {
        "skill": "no-mistakes-reviewer",
        "path": ".agents/skills/no-mistakes-reviewer/SKILL.md",
        "hint": "Review diff against invariants: security, precision, concurrency, repro test."
    },
    "PHASE_5_STAGING": {
        "skill": "synology-nas-guardian (docker)",
        "path": ".agents/skills/docker/SKILL.md",
        "hint": "Verify Docker multi-stage build, container memory <350MB RAM, and staging health on port 8096."
    },
    "PHASE_6_PRODUCTION_GATE": {
        "skill": "architecture-review-agent",
        "path": ".agents/skills/architecture-review-agent/SKILL.md",
        "hint": "Verify enterprise scalability (1,000 DAU) and obtain explicit human authorization."
    }
}


def get_node_bound_skill(node_name, workflow_type=None, task_name=None):
    """Resolve active domain skill, runbook path, and guidance hint for a protocol node."""
    if not node_name:
        return "general-engineer", ".agents/skills/", "Follow workspace invariants."

    if node_name in ["PHASE_2_SURGICAL_FIX", "PHASE_3_EXECUTION"]:
        task_str = str(task_name or "").lower()
        if any(k in task_str for k in ["ui", "front", "css", "html", "style", "table", "card", "view", "component", "screen", "pwa", "dark"]):
            return (
                "bloomberg-terminal-components",
                ".agents/skills/bloomberg-terminal-components/SKILL.md",
                "Apply dark-theme tokens (#0b0f19), 44px touch targets, zero layout overflow."
            )
        elif any(k in task_str for k in ["db", "sql", "timescale", "hypertable", "query", "oracle", "database", "analytics", "snapshot"]):
            return (
                "timescale-options-analytics",
                ".agents/skills/timescale-options-analytics/SKILL.md",
                "Single-scan CTEs, hypertable chunk constraints, explicit date casting."
            )
        elif any(k in task_str for k in ["sse", "stream", "fastapi", "api", "endpoint", "route", "gateway", "backend"]):
            return (
                "fastapi-sse-streaming",
                ".agents/skills/fastapi-sse-streaming/SKILL.md",
                "FastAPI StreamingResponse, getReader() SSE client loop, keep-alive ping."
            )
        else:
            return (
                "domain-router (bloomberg-ui | timescale-opt | fastapi-sse)",
                ".agents/skills/",
                "Follow domain runbook: UI (bloomberg-terminal-components), DB (timescale-options-analytics), or Streaming (fastapi-sse-streaming)."
            )

    meta = NODE_SKILL_MAP.get(node_name)
    if meta:
        return meta.get("skill", "general-engineer"), meta.get("path", ".agents/skills/"), meta.get("hint", "")
    return "general-engineer", ".agents/skills/", "Adhere to repository invariants."


def cmd_start(args):
    workflow_type = args.type
    name = args.name or "unnamed-task"

    current = get_current_state()
    # Auto-intercept if active feature workflow is sitting at Staging or Prod Gate
    if current and current.get("active_node") in ["PHASE_5_STAGING", "PHASE_6_PRODUCTION_GATE"] and not current.get("parent_workflow") and workflow_type == "bug":
        print(f"[INFO] Active workflow '{current.get('task_name')}' detected at {current.get('active_node')}.")
        print("       Automatically intercepting as a Nested Staging Defect sub-workflow...")
        cmd_staging_bug(args)
        return

    if workflow_type == "bug":
        active_node = "PHASE_0_INTAKE"
    elif workflow_type == "feature":
        active_node = "PHASE_0_INTAKE"
    else:
        active_node = "PHASE_0_POLISH"

    state = {
        "schema_version": "1.1.0",
        "workflow_id": f"WF-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        "workflow_type": workflow_type,
        "task_name": name,
        "active_node": active_node,
        "reproduction_test": None,
        "parent_workflow": None,
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
    skill_name, skill_path, skill_hint = get_node_bound_skill(state['active_node'], state['workflow_type'], state['task_name'])
    print(f"   [ACTIVE SKILL] {skill_name} ({skill_path}): {skill_hint}")


def cmd_staging_bug(args):
    name = args.name or "staging-defect"
    current = get_current_state()
    if not current:
        print("[ERROR] No active workflow. 'staging-bug' requires an active workflow deployed to staging.", file=sys.stderr)
        sys.exit(1)

    if current.get("parent_workflow"):
        print(f"[ERROR] Already in a nested staging defect workflow: '{current.get('task_name')}'. Resolve it first.", file=sys.stderr)
        sys.exit(1)

    valid_nodes = ["PHASE_5_STAGING", "PHASE_6_PRODUCTION_GATE"]
    if current.get("active_node") not in valid_nodes:
        print(f"[ERROR] 'staging-bug' can only be initialized from Staging/Production Gate ({', '.join(valid_nodes)}). Current node: {current.get('active_node')}", file=sys.stderr)
        sys.exit(1)

    # Snapshot parent workflow
    parent_snapshot = dict(current)

    defect_state = {
        "schema_version": "1.1.0",
        "workflow_id": f"DEFECT-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        "workflow_type": "bug",
        "task_name": name,
        "active_node": "PHASE_1_RED_GATE",
        "reproduction_test": None,
        "parent_workflow": parent_snapshot,
        "guards": {
            "plan_approved": True,
            "red_state_verified": False,
            "green_state_verified": False,
            "adversarial_audit_passed": False,
            "staging_verified": False,
            "production_authorized": False
        },
        "audit_trail": [
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "STAGING_DEFECT_SPAWNED",
                "node": "PHASE_1_RED_GATE",
                "details": f"Spawned staging defect '{name}' intercepting parent workflow '{parent_snapshot.get('task_name')}' ({parent_snapshot.get('workflow_id')})"
            }
        ]
    }
    save_state(defect_state)
    print("==================================================================")
    print("  [INTERCEPT] STAGING DEFECT SUB-WORKFLOW INITIALIZED")
    print("==================================================================")
    print(f"   Defect ID:       {defect_state['workflow_id']}")
    print(f"   Defect Task:     {defect_state['task_name']}")
    print("   Active Node:     PHASE_1_RED_GATE (TDD Invariant Active)")
    skill_name, skill_path, skill_hint = get_node_bound_skill(defect_state['active_node'], defect_state['workflow_type'], defect_state['task_name'])
    print(f"   [ACTIVE SKILL]   {skill_name} ({skill_path}): {skill_hint}")
    print(f"   Parent Workflow: {parent_snapshot.get('task_name')} (SUSPENDED at {parent_snapshot.get('active_node')})")
    print("   Next Action:     Write reproduction test and run: python scripts/protocol_graph.py red --test <path>")
    print("==================================================================")


def cmd_reviewer_dealbreaker(args):
    name = args.name or "reviewer-dealbreaker"
    reviewer = getattr(args, "reviewer", "architect") or "architect"
    current = get_current_state()
    if not current:
        print("[ERROR] No active workflow. 'reviewer-dealbreaker' requires an active workflow.", file=sys.stderr)
        sys.exit(1)

    if current.get("parent_workflow"):
        print(f"[ERROR] Already in a nested defect workflow: '{current.get('task_name')}'. Resolve it first.", file=sys.stderr)
        sys.exit(1)

    parent_snapshot = dict(current)

    defect_state = {
        "schema_version": "1.1.0",
        "workflow_id": f"DEALBREAKER-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        "workflow_type": "bug",
        "task_name": f"[{reviewer.upper()}] {name}",
        "active_node": "PHASE_1_RED_GATE",
        "reproduction_test": None,
        "parent_workflow": parent_snapshot,
        "guards": {
            "plan_approved": True,
            "red_state_verified": False,
            "green_state_verified": False,
            "adversarial_audit_passed": False,
            "staging_verified": False,
            "production_authorized": False
        },
        "audit_trail": [
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "REVIEWER_DEALBREAKER_INTERCEPT",
                "node": "PHASE_1_RED_GATE",
                "details": f"Reviewer '{reviewer}' raised dealbreaker '{name}' intercepting parent workflow '{parent_snapshot.get('task_name')}' ({parent_snapshot.get('workflow_id')})"
            }
        ]
    }
    save_state(defect_state)
    print("==================================================================")
    print("  [INTERCEPT] REVIEWER DEALBREAKER SUB-WORKFLOW INITIALIZED")
    print("==================================================================")
    print(f"   Dealbreaker ID:  {defect_state['workflow_id']}")
    print(f"   Reviewer:        {reviewer.upper()}")
    print(f"   Task:            {defect_state['task_name']}")
    print("   Active Node:     PHASE_1_RED_GATE (Bug Remediation Protocol Active)")
    skill_name, skill_path, skill_hint = get_node_bound_skill(defect_state['active_node'], defect_state['workflow_type'], defect_state['task_name'])
    print(f"   [ACTIVE SKILL]   {skill_name} ({skill_path}): {skill_hint}")
    print(f"   Parent Workflow: {parent_snapshot.get('task_name')} (SUSPENDED at {parent_snapshot.get('active_node')})")
    print("   Next Action:     Write reproduction test and run: python scripts/protocol_graph.py red --test <path>")
    print("==================================================================")


def cmd_resolve_defect(args):
    state = get_current_state()
    if not state or not state.get("parent_workflow"):
        print("[ERROR] No active nested defect to resolve.", file=sys.stderr)
        sys.exit(1)

    parent = state["parent_workflow"]
    defect_name = state.get("task_name")
    defect_id = state.get("workflow_id")

    if not state["guards"].get("red_state_verified") or not state["guards"].get("green_state_verified"):
        print("[ERROR] Cannot resolve defect without verified RED and GREEN gates.", file=sys.stderr)
        sys.exit(1)
    if not state["guards"].get("adversarial_audit_passed"):
        print("[ERROR] Cannot resolve defect without passing adversarial audit.", file=sys.stderr)
        sys.exit(1)

    parent_state = dict(parent)
    if parent_state.get("active_node") in ["PHASE_5_STAGING", "PHASE_6_PRODUCTION_GATE"]:
        parent_state["active_node"] = "PHASE_5_STAGING"
        parent_state["guards"]["staging_verified"] = False
    append_audit(parent_state, "DEFECT_RESOLVED", f"Defect '{defect_name}' ({defect_id}) verified and resolved. Parent workflow resumed.")
    save_state(parent_state)

    print("==================================================================")
    print("  [RESOLVED] DEFECT COMPLETED & VERIFIED")
    print("==================================================================")
    print(f"   Defect '{defect_name}' has been successfully verified.")
    print(f"   Parent workflow '{parent_state.get('task_name')}' resumed at: {parent_state.get('active_node')}.")
    skill_name, skill_path, skill_hint = get_node_bound_skill(parent_state['active_node'], parent_state['workflow_type'], parent_state['task_name'])
    print(f"   [ACTIVE SKILL]   {skill_name} ({skill_path}): {skill_hint}")
    print("==================================================================")


def cmd_cancel_bug(args):
    state = get_current_state()
    if not state or not state.get("parent_workflow"):
        print("[ERROR] No active nested staging defect to cancel.", file=sys.stderr)
        sys.exit(1)
    parent = state["parent_workflow"]
    append_audit(parent, "STAGING_DEFECT_CANCELLED", f"Child defect '{state.get('task_name')}' was cancelled.")
    save_state(parent)
    print(f"[OK] Staging defect cancelled. Parent workflow '{parent.get('task_name')}' restored.")


def cmd_status(args):
    state = get_current_state()
    if not state:
        print("[INFO] No active protocol workflow. Run 'python scripts/protocol_graph.py start --help'.")
        return

    parent = state.get("parent_workflow")
    skill_name, skill_path, skill_hint = get_node_bound_skill(state.get("active_node"), state.get("workflow_type"), state.get("task_name"))
    print("==================================================================")
    if parent:
        print("  QUANT PROTOCOL STATE GRAPH: NESTED STAGING DEFECT")
        print(f"  Defect ID:       {state['workflow_id']}")
        print(f"  Defect Task:     {state.get('task_name', '')}")
        print(f"  Active Node:     {state.get('active_node', '')}")
        print(f"  Bound Skill:     {skill_name} ({skill_path})")
        print(f"  Skill Directive: {skill_hint}")
        print(f"  Reproduction:    {state.get('reproduction_test') or '[None Registered]'}")
        print(f"  Parent Workflow: {parent.get('task_name')} ({parent.get('workflow_id')})")
        print(f"  Parent Status:   SUSPENDED at {parent.get('active_node')}")
    else:
        print(f"  QUANT PROTOCOL STATE GRAPH DASHBOARD ({state['workflow_id']})")
        print(f"Workflow Type:    {state.get('workflow_type', '').upper()}")
        print(f"Task Name:        {state.get('task_name', '')}")
        print(f"Active Node:      {state.get('active_node', '')}")
        print(f"Bound Skill:      {skill_name} ({skill_path})")
        print(f"Skill Directive:  {skill_hint}")
        print(f"Reproduction Test:{state.get('reproduction_test') or '[None Registered]'}")
    print("------------------------------------------------------------------")
    print("Guards & Checkpoints:")
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
    skill_name, skill_path, skill_hint = get_node_bound_skill(state['active_node'], state['workflow_type'], state['task_name'])
    print(f"   [ACTIVE SKILL] {skill_name} ({skill_path}): {skill_hint}")


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
        skill_name, skill_path, skill_hint = get_node_bound_skill(state['active_node'], state['workflow_type'], state['task_name'])
        print(f"   [ACTIVE SKILL] {skill_name} ({skill_path}): {skill_hint}")
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
        skill_name, skill_path, skill_hint = get_node_bound_skill(state['active_node'], state['workflow_type'], state['task_name'])
        print(f"   [ACTIVE SKILL] {skill_name} ({skill_path}): {skill_hint}")
    else:
        print(f"\n[FAIL] GREEN GATE FAILED: Reproduction test is still failing (exit code {rc}).", file=sys.stderr)
        sys.exit(1)


def cmd_audit(args):
    state = get_current_state()
    if not state:
        print("[ERROR] No active workflow.", file=sys.stderr)
        sys.exit(1)

    if os.environ.get("PROTOCOL_TEST_AUDIT_DIFF") is not None:
        all_diff = os.environ.get("PROTOCOL_TEST_AUDIT_DIFF")
        modified_files = [f.strip() for f in all_diff.splitlines() if f.strip()]
    else:
        res = subprocess.run(["git", "diff", "--name-only"], cwd=str(WORKSPACE_ROOT), capture_output=True, text=True)
        res_staged = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=str(WORKSPACE_ROOT), capture_output=True, text=True)
        all_diff = res.stdout + "\n" + res_staged.stdout
        modified_files = [f.strip() for f in res.stdout.splitlines() if f.strip()]

    print(f"[AUDIT] Checking {len(modified_files)} modified files...")
    if state["workflow_type"] == "bug":
        repro_test = state.get("reproduction_test")
        if repro_test:
            repro_name = Path(repro_test).name
            if repro_name not in all_diff:
                print(f"[ERROR] AUDIT FAILED: Reproduction test ({repro_test}) is not present in diff.", file=sys.stderr)
                sys.exit(1)

    state["guards"]["adversarial_audit_passed"] = True
    state["active_node"] = "PHASE_5_STAGING"
    append_audit(state, "AUDIT_APPROVED", f"Diff approved: {len(modified_files)} files modified")
    save_state(state)
    print("[OK] Adversarial Audit Passed. Ready for Staging deployment.")
    skill_name, skill_path, skill_hint = get_node_bound_skill(state['active_node'], state['workflow_type'], state['task_name'])
    print(f"   [ACTIVE SKILL] {skill_name} ({skill_path}): {skill_hint}")


def cmd_staging_verify(args):
    state = get_current_state()
    if not state:
        print("[ERROR] No active workflow.", file=sys.stderr)
        sys.exit(1)

    # Check if this is a nested staging defect workflow
    if state.get("parent_workflow"):
        parent = state["parent_workflow"]
        defect_name = state.get("task_name")
        defect_id = state.get("workflow_id")

        if not state["guards"].get("red_state_verified") or not state["guards"].get("green_state_verified"):
            print("[ERROR] Cannot verify defect on staging without verified RED and GREEN gates.", file=sys.stderr)
            sys.exit(1)
        if not state["guards"].get("adversarial_audit_passed"):
            print("[ERROR] Cannot verify defect on staging without passing adversarial audit.", file=sys.stderr)
            sys.exit(1)

        parent_state = dict(parent)
        parent_state["active_node"] = "PHASE_5_STAGING"
        parent_state["guards"]["staging_verified"] = False  # Must re-verify staging for parent feature
        append_audit(parent_state, "STAGING_DEFECT_RESOLVED", f"Defect '{defect_name}' ({defect_id}) verified on staging. Parent workflow resumed.")
        save_state(parent_state)

        print("==================================================================")
        print("  [RESOLVED] STAGING DEFECT COMPLETED & VERIFIED")
        print("==================================================================")
        print(f"   Defect '{defect_name}' has been successfully verified on staging.")
        print(f"   Parent workflow '{parent_state.get('task_name')}' resumed at: PHASE_5_STAGING.")
        parent_skill, parent_path, parent_hint = get_node_bound_skill(parent_state['active_node'], parent_state['workflow_type'], parent_state['task_name'])
        print(f"   [ACTIVE SKILL]   {parent_skill} ({parent_path}): {parent_hint}")
        print("   Run 'python scripts/protocol_graph.py staging-verify' when full parent staging acceptance is confirmed.")
        print("==================================================================")
        return

    state["guards"]["staging_verified"] = True
    state["active_node"] = "PHASE_6_PRODUCTION_GATE"
    append_audit(state, "STAGING_VERIFIED", "Staging in-situ health confirmed on port 8096")
    save_state(state)
    print("[OK] Staging Verified. Graph advanced to: PHASE_6_PRODUCTION_GATE.")
    skill_name, skill_path, skill_hint = get_node_bound_skill(state['active_node'], state['workflow_type'], state['task_name'])
    print(f"   [ACTIVE SKILL] {skill_name} ({skill_path}): {skill_hint}")
    print("[LOCK] Production push to master is locked awaiting explicit human command.")


def cmd_prod_authorize(args):
    state = get_current_state()
    if not state:
        print("[ERROR] No active workflow.", file=sys.stderr)
        sys.exit(1)

    if state.get("parent_workflow"):
        print(f"\n[STOP] [PROD BLOCKED] Cannot authorize production while nested staging defect '{state.get('task_name')}' is active.", file=sys.stderr)
        print("   The defect must be resolved and verified on staging before parent feature can be promoted.", file=sys.stderr)
        sys.exit(1)

    if not state["guards"].get("staging_verified"):
        print("\n[STOP] [PROD BLOCKED] Staging verification not completed.", file=sys.stderr)
        print("   Run: python scripts/protocol_graph.py staging-verify", file=sys.stderr)
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

    p_sbug = subparsers.add_parser("staging-bug", help="Spawn a nested bug remediation workflow from staging")
    p_sbug.add_argument("--name", required=True, help="Defect description / bug name")

    p_rdeal = subparsers.add_parser("reviewer-dealbreaker", help="Spawn a nested bug remediation workflow from reviewer dealbreaker")
    p_rdeal.add_argument("--name", required=True, help="Dealbreaker description / bug name")
    p_rdeal.add_argument("--reviewer", default="architect", help="Reviewer role (e.g. architect, quality, security)")

    subparsers.add_parser("resolve-defect", help="Resolve active nested defect / dealbreaker and resume parent workflow")
    subparsers.add_parser("cancel-bug", help="Cancel active staging defect and resume parent workflow")
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
        "staging-bug": cmd_staging_bug,
        "reviewer-dealbreaker": cmd_reviewer_dealbreaker,
        "resolve-defect": cmd_resolve_defect,
        "cancel-bug": cmd_cancel_bug,
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
