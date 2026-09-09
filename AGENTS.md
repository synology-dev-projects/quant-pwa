# Quant PWA - Workspace Architecture & Protocol Invariants

## Core Directives for All Agents & Engineers

1. **Mandatory In-Situ Reproduction Gate (RED Gate)**:
   - For any defect, bug, or unexpected behavior, you are strictly forbidden from editing application source code until you have written an isolated test (`tests/test_reproduce_<issue>.py` or `tests/test_reproduce_<issue>.js`) and verified that it fails in the active environment with an authentic error trace.
   - Symmetric verification (GREEN Gate) requires re-executing the exact same test in the exact same environment to prove exit code 0.

2. **AI Governance: Zero Trade Advice Policy**:
   - Absolutely NEVER provide trade recommendations, buy/sell signals, price targets, entry/exit levels, trade setups, or financial advice.
   - Deliver ONLY objective analysis of the quantitative options microstructure and flow data provided.

3. **AI Governance: ADHD-Friendly Brevity Policy**:
   - All AI analysis and Cockpit synthesis must be ultra-short, punchy, and scannable.
   - Use bolded metrics and short bullets (maximum 3 bullet points, e.g., Microstructure Snapshot).
   - Zero conversational fluff, zero wordy preambles, zero lengthy paragraphs. Deliver high-density insight digestible in < 10 seconds.

4. **Smallest Viable Diff (Strict YAGNI)**:
   - Patch ONLY the lines necessary to resolve the approved issue or feature.
   - Avoid speculative refactoring, formatting churn, or modifying unrelated files.

5. **Rule 3 Master Branch Protection**:
   - Never push directly or automatically to the master branch.
   - Deploy to develop2 (Staging, port 8096) for live interactive verification first.
   - Promotion to master strictly requires explicit human authorization (push to prod).

6. **Staging Defect Intercept Mandate**:
   - If an issue or defect is discovered on Staging (`:8096`) or at the Production Gate, you MUST immediately spawn a nested defect workflow (`python scripts/protocol_graph.py staging-bug --name "<issue>"`).
   - Never apply unverified or ad-hoc patches while a feature is at staging. All defects must satisfy the RED/GREEN/AUDIT gates and be verified on staging before production promotion is unlocked.

7. **Mandatory Graph-Bound Domain Skill Adherence**:
   - Every phase in `scripts/protocol_graph.py` is bound to a specialized engineering skill runbook under `.agents/skills/`. Agents MUST consult and adhere strictly to the bound skill before making modifications:
     * **Intake & Orchestration (`PHASE_0_INTAKE`)**: Follow `.agents/skills/captain-orchestrator/SKILL.md` for Grill-Me interviews, user alignment, and task scoping.
     * **Reproduction Scaffolding (`PHASE_1_RED_GATE`)**: Follow `.agents/skills/repro-scaffolder/SKILL.md` for fast TDD reproduction, isolated mock fixtures, and failing assert verification.
     * **UI & PWA Frontend (`PHASE_2_SURGICAL_FIX` / `PHASE_3_EXECUTION`)**: Follow `.agents/skills/bloomberg-terminal-components/SKILL.md` for Bloomberg dark-theme tokens (`#0b0f19`, `#10b981`, `#fbbf24`), 44px minimum touch targets, and zero horizontal/vertical layout overflows.
     * **Database & Hypertables (`PHASE_2_SURGICAL_FIX` / `PHASE_3_EXECUTION`)**: Follow `.agents/skills/timescale-options-analytics/SKILL.md` for single-scan CTE queries, composite partial indexes, and explicit date casting.
     * **Streaming & FastAPI (`PHASE_2_SURGICAL_FIX` / `PHASE_3_EXECUTION`)**: Follow `.agents/skills/fastapi-sse-streaming/SKILL.md` for native `StreamingResponse`, `ReadableStream` client consumer loops, and keep-alive ping headers.
     * **Pre-Commit Code Audit (`PHASE_4_AUDIT`)**: Follow `.agents/skills/no-mistakes-reviewer/SKILL.md` for adversarial diff inspection across security, precision, concurrency, and test coverage.
     * **Staging & Docker Deployment (`PHASE_5_STAGING`)**: Follow `.agents/skills/docker/SKILL.md` (and `.agents/skills/synology-nas-guardian/SKILL.md`) for zero-bloat multi-stage Docker builds, strict `< 350MB` RAM budgets, and healthcheck watchdogs.
     * **Production Gate (`PHASE_6_PRODUCTION_GATE`)**: Follow `.agents/skills/architecture-review-agent/SKILL.md` for 1,000 DAU enterprise scalability validation.
