---
name: refactor-plan
description: >-
  MANDATORY: Activate this skill whenever the user types /refactor-plan or asks for
  a refactoring plan before modifying code. Enforces atomic slicing, characterization
  tests, and low-risk phased refactoring.
---

# 🏗️ Phased Refactor Plan Protocol (`/refactor-plan`)

AI agents often fail at refactoring because they attempt to rewrite 10 files at once, breaking tests and introducing regressions. 

This skill enforces Matt Pocock's **Atomic Slicing & Characterization** refactoring strategy.

## Phase 1: Pinning Existing Behavior (Characterization Tests)
Before refactoring a single line of production code:
1. Identify all public interfaces and edge cases in the target module.
2. Write characterization tests that capture the *current exact behavior* (even quirks/fallbacks).
3. Run the test suite and confirm it passes 100%.

## Phase 2: Slicing the Refactor Plan
Create an `implementation_plan.md` artifact breaking the refactor into small, reversible slices:

- **Slice 1: Extraction & Single Source of Truth**:
  - Extract duplicated logic into a pure, stateless helper module.
  - Keep old functions as thin wrappers pointing to the new module.
  - Verify all tests pass.

- **Slice 2: Consumer Migration**:
  - Update callers one-by-one to use the new module directly.
  - Delete old thin wrappers once call count reaches zero.
  - Verify all tests pass after each caller migration.

- **Slice 3: Deslop & Inlining**:
  - Run the 4-pass deslop sweep on the new module.
  - Strip dead code, redundant try/catch blocks, and narrative comments.
  - Verify all tests pass.

## Phase 3: Rollback Plan
Each slice must be independently committable. If any step fails or creates unintended side-effects, git revert that specific slice without losing prior progress.
