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
