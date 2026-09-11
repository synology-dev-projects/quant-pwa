---
name: deslop
description: >-
  MANDATORY: Activate this skill whenever the user types /deslop, asks to deslop,
  declutter, clean up AI code, remove narrative comments, or strip redundant wrappers
  from the Quant PWA codebase. Enforces the 4-Pass Surgical Pruning Protocol and
  strict Quant Domain Invariants (Zero Trade Advice, ADHD Brevity, 44px Touch Targets,
  Version Parity).
---

# 🧹 The Quant PWA Code Deslop Protocol (`/deslop`)

This skill defines the rigorous, non-destructive pruning methodology tailor-made for the **Quant PWA & Gateway** architecture. It purges AI-generated slop, conversational filler, defensive over-wrapping, and zombie code while guaranteeing 100% behavioral equivalence and strict Quant Domain Invariants.

## Quant System Core Invariants

1. **Zero Trade Advice Mandate**:
   - Scrub any subjective or advisory trading language ("bullish setup", "consider entering", "profit target", "breakout trigger", "good risk/reward").
   - Retain ONLY purely quantitative, descriptive microstructure and Greek terminology (e.g. "Spot @ $218.36 above Zero Flip @ $211.20 in Positive Gamma (+GEX)").

2. **ADHD-Friendly Brevity Mandate**:
   - Strip wordy preambles, introductory filler, and conversational fluff.
   - Enforce bolded metrics and scannable sub-bullets (max 3 bullets, digestible in < 10 seconds).

3. **Behavioral Invariance & Regression Lock**:
   - Deslopping is purely structural. It must NEVER alter calculation results, API contracts, or database queries.
   - Run unit tests before and after to verify zero regressions.

4. **Version Parity Invariant**:
   - Deslopping must never alter or drift version strings across the 5 synchronized version files. Verify with `python scripts/bump_version.py --check`.

5. **Touch Target & Zero-Overflow Invariant**:
   - Frontend styling cleanup must maintain 44px minimum tap targets and zero horizontal layout overflows across 375px, 768px, and 1280px viewports (`audit_layout.js`).

6. **Synology NAS Memory Budget (< 350MB RAM)**:
   - Strip unneeded in-memory cache duplicates, giant object retention in global scopes, or leaky event listeners.

---

## The 4-Pass Execution Sequence

### Pass 1: Automated AST & Mechanical Sweep
Run deterministic tools first:

* **Backend Gateway (`gateway/`)**:
  ```bash
  ruff check --select F401,F841,ERA001 --fix gateway/
  ```
  *(Removes unused imports F401, unused variables F841, and commented-out code ERA001).*

* **Frontend (`frontend/`)**:
  - Remove all leftover debugging `console.log()` statements.
  - Check ES module imports for unreferenced symbols.

---

### Pass 2: Comment De-conversationalizing & Narrative Purge
Scan touched files and delete all narrative "what" comments:

* **DELETE (AI Narration & Redundancy)**:
  ```python
  # ❌ SLOP:
  # Loop over records to filter out zero strike flow
  filtered = [r for r in records if r.get("strike", 0) > 0]
  # Return the filtered records list
  return filtered
  ```

* **KEEP (Domain Invariants & "Why" Only)**:
  ```python
  # ✅ CLEAN:
  # Invariant: Contract requires at least 10 historical prints for ordinal ranking
  if len(records) < 10:
      return []
  ```

---

### Pass 3: Structural Pruning & Single Source of Truth
Eliminate unnecessary indirection:

1. **Inline Single-Caller Trivial Wrappers**:
   - If a private helper function `_format_date_temp(d)` has exactly 1 call site and is 1–2 lines, inline it.

2. **Flatten Defensive Over-Wrapping**:
   - Replace triple-nested `try/except Exception: pass` blocks with typed exception handling or let gateway global middleware catch them.

3. **Prune Speculative Fallback Cascades**:
   - Remove fake gaussian curve fallbacks or dead code branches that can never execute in production.

4. **Consolidate Copy-Paste Divergence**:
   - Enforce single sources of truth. Shared quantitative math must reside in `gateway/app/core/` (e.g. `flow_criteria.py`), never copy-pasted between routers.

---

### Pass 4: Verification & Regression Lock
Run the complete verification matrix before marking deslop complete:
```bash
# 1. Backend test suite
pytest gateway/tests/ -v

# 2. Frontend layout & DOM integration
node frontend/tests/audit_layout.js
node frontend/tests/test_flow_view.js
node frontend/tests/test_cockpit_view.js

# 3. Version parity check
python scripts/bump_version.py --check
```
Verify git diff is clean, compact, and net-reductive (`git diff --stat`).
