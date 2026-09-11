---
name: refactor-plan
description: >-
  MANDATORY: Activate this skill whenever the user types /refactor-plan or asks for
  a refactoring plan before modifying code in the Quant PWA. Enforces atomic slicing,
  characterization tests, Single Source of Truth, and low-risk phased execution.
---

# 🏗️ Quant PWA Phased Refactor Plan Protocol (`/refactor-plan`)

Large un-sliced refactors in quantitative systems cause silent calculation drift, broken hypertable queries, and layout regressions.

This skill enforces Matt Pocock's **Atomic Slicing & Characterization** protocol tailored to the Quant PWA architecture.

## Phase 1: Pinning Existing Behavior (Characterization Tests)
Before refactoring any production code:
1. Identify all affected public API endpoints and UI rendering components.
2. Write characterization tests that freeze current outputs (e.g. verify GEX/DEX totals, strike calculations, or payload structures).
3. Verify test suite passes 100% on the unrefactored code.

## Phase 2: Slicing the Refactor Plan
Draft an `implementation_plan.md` artifact breaking the refactor into independent, testable slices:

- **Slice 1: Single Source of Truth Extraction**:
  - Extract duplicated logic into a shared module under `gateway/app/core/` (e.g. `flow_criteria.py`).
  - Keep legacy router functions as thin forwarders pointing to the core module.
  - Verify all existing tests pass (`pytest gateway/tests/`).

- **Slice 3: Consumer & Router Migration**:
  - Migrate callers (Cockpit router, Flow router, etc.) one-by-one to use the core module directly.
  - Delete legacy forwarders once all callers are migrated.
  - Verify all tests pass after each caller migration.

- **Slice 3: Database & Hypertable Query Optimization**:
  - Optimize TimescaleDB / PostgreSQL queries using single-scan CTEs (`WITH ...`).
  - Maintain ANSI standard syntax that works across SQLite in-memory tests and production TimescaleDB.

- **Slice 4: Deslop & Cleanup**:
  - Run `/deslop` on modified files.
  - Purge conversational comments, unused imports, and dead wrappers.
  - Verify layout (`audit_layout.js`) and version parity (`bump_version.py --check`).

## Phase 3: Rollback Plan
Every slice must be an independent commit on `develop2`. If any slice creates unexpected latency or regressions, revert that specific commit without losing other progress.
