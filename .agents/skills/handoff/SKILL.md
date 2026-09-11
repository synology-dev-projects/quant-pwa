---
name: handoff
description: >-
  MANDATORY: Activate this skill whenever the user types /handoff, asks to prepare
  a handoff, compact context, or summarize current progress for a clean session reset.
  Generates a high-density, Quant-PWA specific handoff artifact to prevent context decay.
---

# 📋 Quant PWA Session Handoff & Context Reset Protocol (`/handoff`)

As conversations grow in size (>40k tokens), AI coding models suffer from **context window decay**—hallucinating constraints, repeating discarded approaches, and degrading response speed.

This skill compiles an authoritative, high-density **Quant PWA Handoff Document** (`handoff.md`) allowing you to start a fresh chat session with 100% intelligence and zero lost momentum.

## Core Directives

1. **Exact Git & Protocol Ground Truth**:
   - Report active branch (`develop2` vs `master`).
   - Report latest commit hash and message.
   - Report protocol state via `python scripts/protocol_graph.py status`.
   - Report target production version (e.g. `v1.1.20`).
2. **Multi-Environment Status**:
   - Dev / Staging: Port `8096` (`http://192.168.1.68:8096`).
   - Production: Port `8095` (`http://192.168.1.68:8095`).
3. **High Information Density**:
   - Zero conversational pleasantries.
   - Crisp monospace bullet points, test commands, and exact file paths.

---

## Handoff Template Specification

When `/handoff` is invoked, generate `handoff.md` with this exact structure:

```markdown
# Session Handoff: [Task / Feature Name]

## 1. Ground Truth & Environment State
- **Workspace**: `C:\Coding\VSCode\Quant System\quant-pwa`
- **Active Branch**: `develop2` (Rule 3 Protection Active - never on `master`)
- **Latest Commit**: `hash` - `feat(...): description`
- **Working Tree**: Clean / Dirty (list modified files)
- **Protocol Graph State**: `ACTIVE_NODE` (e.g. `PHASE_2_SEQUENCING`, `PHASE_6_PRODUCTION_GATE`)
- **App Version**: `vX.Y.Z` (Build `YYYY-MM-DD-NN`)
- **NAS Deployment Ports**: Production :8095 | Staging :8096

## 2. What Was Accomplished This Session
- [x] Feature / Bug fixed and verified
- [x] Version parity strictly synchronized across 5 files
- [x] Test suite passing: Backend (N/N) | Frontend (N/N) | Layout (171/171)

## 3. Active Architectural Decisions & Invariants
- **Rule 3 Master Branch Protection**: Push only to `develop2`. Merge to `master` strictly requires human authorization ("approve").
- **Zero Trade Advice**: Purely quantitative microstructure; no buy/sell recommendations.
- **Single Source of Truth**: Shared calculations reside in `gateway/app/core/`.
- **Hardware Footprint**: Synology NAS `< 350MB` RAM budget maintained.

## 4. Current Blockers & Next Immediate Steps
1. Next immediate step to execute
2. Following step
3. Verification command to run

## 5. Quick-Resume Prompt for Fresh Session
Copy and paste this into a new chat:
> "Resume work on [Task Name]. State is at [Active Node]. Review `handoff.md` and [implementation_plan.md / walkthrough.md]. Begin with Step 1."
```

## Post-Handoff Guidance
Remind the user to open a new conversation for peak agent reasoning speed and paste the quick-resume prompt.
