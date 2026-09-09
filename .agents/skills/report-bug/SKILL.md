---
name: report-bug
description: >-
  MANDATORY: Activate this skill whenever the user types /bug, /report-bug,
  reports a defect, or says 'I want to report a bug'. Enforces the 5-Step Bug
  Remediation Protocol and deterministic Protocol Graph State Engine.
---

# 🛡️ Bug Reporting & Remediation Protocol (`/report-bug`, `/bug`)

Whenever the user reports a bug, defect, discrepancy, or unexpected behavior:

## Phase 0: Graph State Initialization (HARD GATE)
**Do NOT touch or modify any application source code yet.**

1. Initialize the defect on the deterministic state engine:
   ```bash
   # If at Staging / Production Gate:
   python scripts/protocol_graph.py staging-bug --name "<issue-slug>"
   
   # If no active workflow:
   python scripts/protocol_graph.py start --type bug --name "<issue-slug>"
   ```
2. Verify active node is `PHASE_1_RED_GATE`:
   ```bash
   python scripts/protocol_graph.py status
   ```

## Phase 1: In-Situ Reproduction Gate (RED Gate)
1. Ask targeted questions to clarify:
   - **Expected behavior** vs **Actual behavior**.
   - Affected tab, API endpoint, or data table.
2. Write a dedicated, isolated reproduction test:
   - Backend: `gateway/tests/test_reproduce_<issue>.py`
   - Frontend: `frontend/tests/test_reproduce_<issue>.js`
3. Execute and verify the RED state through the protocol graph:
   ```bash
   python scripts/protocol_graph.py red --test <test_path>
   ```
   **Invariant:** The test MUST fail (exit code != 0) with an authentic error trace reproducing the bug.

## Phase 2: Surgical Fix (Smallest Viable Diff)
1. Review the failing trace.
2. Apply the smallest viable diff to resolve the root cause under strict YAGNI.
3. Do not make speculative changes, refactors, or formatting churn.

## Phase 3: Symmetric Verification Gate (GREEN Gate)
1. Execute and verify the GREEN state through the protocol graph:
   ```bash
   python scripts/protocol_graph.py green
   ```
   **Invariant:** The reproduction test MUST now pass (exit code 0).
2. Run the full regression test suite (e.g. `pytest gateway/tests/`, `audit_layout.js`).

## Phase 4: Adversarial Audit Gate
1. Stage modified files and the reproduction test (`git add`).
2. Run the adversarial audit gate:
   ```bash
   python scripts/protocol_graph.py audit
   ```

## Phase 5: Staging Verification Gate
1. Commit changes on `develop2` with standard prefix: `fix(<scope>): <description>`.
2. Push to `origin develop2` (Staging, port `8096`).
3. Verify the fix in-situ on the live staging environment.
4. Advance the graph:
   ```bash
   python scripts/protocol_graph.py staging-verify
   ```

## Phase 6: Production Promotion Gate (Rule 3 Protection)
1. **HALT.** Never push directly to `master`.
2. Present a concise verification report to the user.
3. Prompt for explicit approval (`"approved"`, `"push to prod"`).
4. Only upon explicit human confirmation, merge `develop2` into `master` and push.
