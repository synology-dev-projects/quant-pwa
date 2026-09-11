---
name: deslop
description: >-
  MANDATORY: Activate this skill whenever the user types /deslop, asks to deslop,
  declutter, clean up AI code, remove narrative comments, or strip redundant wrappers
  from the codebase. Enforces the 4-Pass Surgical Pruning Protocol with zero regression.
---

# 🧹 The 4-Pass Code Deslop Protocol (`/deslop`)

This skill defines the rigorous, non-destructive methodology for purging AI-generated "slop", conversational filler, defensive over-wrapping, and zombie code while guaranteeing 100% behavioral equivalence.

## Core Directives & Invariants

1. **Behavioral Invariance (Zero Regressions)**:
   - Deslopping is strictly structural and stylistic. It must NEVER alter runtime behavior, API schemas, database contracts, or mathematical results.
   - You MUST run the complete unit test suite before starting and after finishing.

2. **"Delete Anything That Doesn't Break a Test" (The Pocock Razor)**:
   - If speculative defensive checks (`if x is not None and len(x) > 0 and ...`), helper functions, or fallback wrappers can be removed without failing any unit tests or breaking static typing, they are slop and should be pruned.

3. **Strict Ban on Narrative Comments**:
   - Delete all comments that merely narrate *what* the code does (e.g. `# Loop through items`, `# Initialize dictionary`, `# Function to fetch data`).
   - Retain ONLY comments that explain *why* non-obvious code exists (e.g. domain business invariants, specific regulatory/exchange quirks, bug workarounds, mathematical derivations).

---

## The 4-Pass Execution Sequence

### Pass 1: Automated AST & Mechanical Sweep
Always execute automated linter/AST engines first before touching manual logic:

* **Python Subsystems (`gateway/`)**:
  ```bash
  # Purges unused imports (F401), unused variables (F841), and commented-out dead code (ERA001)
  ruff check --select F401,F841,ERA001 --fix gateway/
  ```

* **Frontend Subsystems (`frontend/`)**:
  - Scan for orphaned `console.log()` statements left from debugging.
  - Scan for unreferenced variables or zombie imports in ES modules.

---

### Pass 2: Comment De-conversationalizing & Narrative Purge
Inspect the target file(s) and strip LLM conversational noise:

* **DELETE (AI Preamble & Narrations)**:
  ```python
  # ❌ SLOP:
  # This function takes the spot price and computes the zero flip level
  # We first validate that spot is greater than 0
  if spot <= 0:
      return 0.0
  # Now we loop through all strikes to aggregate total gamma
  for strike in strikes:
      ...
  ```

* **KEEP (Domain Invariants & "Why" Only)**:
  ```python
  # ✅ CLEAN:
  # Invariant: Contract requires at least 10 historical prints for ordinal ranking
  if len(records) < 10:
      return []
  ```

---

### Pass 3: Structural Pruning (YAGNI & Single Source of Truth)
Eliminate unnecessary indirection introduced by AI coding:

1. **Inline Single-Caller Trivial Wrappers**:
   - If a private helper function `_calculate_temp_val(x)` is only called by one function and consists of 1–2 trivial lines, inline it directly into the caller.

2. **Flatten Defensive Over-Wrapping**:
   - Replace 3 nested `try/except Exception: pass` blocks with explicit, typed error boundaries or let errors propagate to the gateway exception handlers.

3. **Prune Speculative Fallback Cascades**:
   - Remove dead fallback branches that were added "just in case" but can never be triggered in real execution.

4. **Consolidate Copy-Paste Divergence**:
   - If identical currency formatting, date arithmetic, or scoring logic is duplicated across multiple views, import it from the shared core single source of truth (e.g., `app.core.flow_criteria`).

---

### Pass 4: Verification & Regression Lock
Before marking the deslop operation complete:
1. Run all unit tests for the touched module:
   ```bash
   pytest gateway/tests/ -v
   node frontend/tests/audit_layout.js
   ```
2. Verify git diff is clean, compact, and focused purely on reduction of lines of code (`git diff --stat`).
3. Report the net line reduction and verified tests to the user.
