---
name: new-feature
description: >-
  MANDATORY: Activate this skill whenever the user types /feature, /new-feature,
  or requests new functionality, enhancement, or capability. Enforces the
  6-Phase Feature Lifecycle and deterministic Protocol Graph State Engine.
---

# 🚀 Feature Development Protocol (`/new-feature`, `/feature`)

Whenever the user requests a new feature, architecture capability, or functional enhancement:

## Phase 0: Graph State Initialization & Scoping Triage
1. Initialize the feature on the deterministic state engine:
   ```bash
   python scripts/protocol_graph.py start --type feature --name "<feature-slug>"
   ```
2. Verify active node is `PHASE_0_INTAKE`:
   ```bash
   python scripts/protocol_graph.py status
   ```
3. Conduct the mandatory scoping triage (via `ask_question` or interactive interview):
   - **User Experience & Interaction Flow**: UI components, views, responsiveness, metrics.
   - **API Contracts & Data Schemas**: Endpoints, request payloads, Pydantic models.
   - **Quantitative & Business Logic**: Specific algorithms, calculations, Greek formulas.
   - **Data & Infrastructure Dependencies**: Pipelines, database tables, caches, rate limits.

## Phase 1: Implementation Plan & User Approval Gate (HARD GATE)
1. Draft or update the `implementation_plan.md` artifact detailing:
   - Architectural design & trade-offs.
   - Exact files to `[NEW]`, `[MODIFY]`, or `[DELETE]`.
   - Automated test verification commands.
   - Open questions and breaking changes.
2. Set `RequestFeedback: true` on the artifact metadata.
3. **STOP AND WAIT** for user approval (`"approved"`, `"proceed"`).
4. Upon approval, record in the state engine:
   ```bash
   python scripts/protocol_graph.py plan-approve
   ```

## Phase 2: Multi-Agent Crew Execution
1. Dispatch domain subagents in parallel where appropriate:
   - `BackendSystemsEngineer`: APIs, models, algorithms, routers.
   - `MobileFrontendEngineer`: PWA components, charts, responsive styling.
   - `DataPipelineEngineer`: Scrapers, loaders, DAG pipelines.
2. Adhere strictly to YAGNI and the smallest viable diff.

## Phase 3: Local In-Situ Test Gate
1. Execute full local verification suites:
   - Backend: `pytest gateway/tests/`
   - Frontend: `node tests/audit_layout.js` (zero overflow on 375px/768px/1280px)
   - Feature integration tests: `node tests/test_<feature>.js`

## Phase 4: Adversarial Quality & Architecture Reviews
1. Dispatch `AdversarialQualityAuditor` and `EnterpriseArchitectureReviewer`.
2. Any 🔴 **CRITICAL** flag or dealbreaker immediately transitions workflow to `BLOCKED`.
3. Run the audit check:
   ```bash
   python scripts/protocol_graph.py audit
   ```

## Phase 5: Staging Deployment Gate
1. Commit changes on `develop2`: `feat(<scope>): <description>`.
2. Push to `origin develop2` (Staging container on port `8096`).
3. Verify live functionality in-situ.
4. Advance the graph:
   ```bash
   python scripts/protocol_graph.py staging-verify
   ```

## Phase 6: Production Promotion Gate (Rule 3 Protection)
1. **HALT.** Never push directly to `master`.
2. Present a concise verification report to the user.
3. Prompt for explicit approval (`"approved"`, `"push to prod"`).
4. Only upon explicit human confirmation, merge `develop2` into `master`, update living docs (`walkthrough.md`, `quant-architecture`), and push.
