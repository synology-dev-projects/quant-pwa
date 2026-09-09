---
name: no-mistakes-reviewer
description: Performs an adversarial, multi-perspective code review on git diffs for security, concurrency, numerical math, and test isolation.
---

# "No-Mistakes" Code Review Skill

When this skill is activated to review code changes or PRs on `develop2`:

## 1. Inspection Protocol
1. Execute `git diff develop...develop2` (or inspect unstaged modified files).
2. Audit against the 4 Core Pillars:
   - **Security:** Check for hardcoded credentials, unauthenticated routes, timing leaks, and open CORS.
   - **Database & Concurrency:** Check for static temporary table names, missing engine pooling, unclosed transactions, and connection leaks.
   - **Math & Precision:** Check DTE logic, Greek calculations, regex bounds (`\d{2,6}`), and datetime timezone conversions.
   - **Test Safety:** Verify that tests use mocks/sandboxes and DO NOT perform write/delete operations against production database tables.

## 2. Output Format
Produce a clean review report:
- 🔴 **Blockers (Must Fix):** Critical flaws or regressions.
- 🟡 **Suggestions:** Minor optimizations or style improvements.
- 🟢 **Verdict:** `APPROVED` or `CHANGES_REQUESTED`.
