---
name: handoff
description: >-
  MANDATORY: Activate this skill whenever the user types /handoff, asks to prepare
  a handoff, compact context, or summarize current progress for a clean session reset.
  Generates a dense, structured handoff artifact to prevent context-window decay.
---

# 📋 Session Handoff & Context Reset Protocol (`/handoff`)

As conversations grow in size (>50k tokens), AI coding models suffer from **context window decay**—hallucinating constraints, repeating discarded patterns, and producing lower-density output. 

This skill constructs a high-density, standardized **Handoff Document** that allows starting a brand new, lightning-fast session with zero loss of momentum.

## Core Directives

1. **High Information Density**: No conversational pleasantries. Everything must be monospace, tabular, or telegraphic bullet points.
2. **Exact Git Reality**: Report the exact branch, latest commit hash, staged/unstaged diff stats, and active protocol node.
3. **Reproducible Commands**: Include exact shell commands to run tests, start servers, or verify current state.

---

## Handoff Template Specification

When `/handoff` is triggered, create `handoff.md` with the following structure:

```markdown
# Session Handoff: [Task / Feature Name]

## 1. Ground Truth & Git State
- **Workspace**: `path/to/repo`
- **Active Branch**: `develop2` (or current branch)
- **Latest Commit**: `hash` - `commit message`
- **Working Tree**: Clean / Dirty (list modified files)
- **Protocol Graph State**: Active Node (e.g. `PHASE_2_SEQUENCING`, `PHASE_6_PRODUCTION_GATE`)

## 2. What Was Accomplished This Session
- [x] Feature / Bug 1 implemented and verified
- [x] Version bumped to vX.Y.Z
- [x] Unit tests passed (N/N green)

## 3. Active Architectural Decisions & Invariants
- Invariant 1 (e.g. Minimum 10 records for ordinal ranking)
- Invariant 2 (e.g. Rule 3 Master Branch Protection strictly active)
- Storage / Query choices (e.g. Single-scan CTEs instead of client joins)

## 4. Current Blockers / Next Steps (In Priority Order)
1. Next immediate step to execute
2. Following step
3. Verification command to run

## 5. Quick-Resume Prompt for Next Session
Copy and paste this into the fresh session:
> "Resume work on [Task Name]. State is at [Active Node]. Please view `handoff.md` and [implementation_plan.md / walkthrough.md] and proceed with Step 1."
```

## Post-Handoff Guidance
Remind the user to start a fresh chat/session for peak agent intelligence and paste the quick-resume prompt.
