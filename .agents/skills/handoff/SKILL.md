---
name: handoff
description: >-
  MANDATORY: Activate this skill whenever the user types /handoff, asks to prepare
  a handoff, compact context, or summarize current progress for a clean session reset.
  Enforces a deterministic state-transfer architecture to prevent context decay.
---

# 📋 Quant System Deterministic Session Handoff Protocol (`/handoff`)

When context approaches >40k tokens or a workflow milestone completes, AI models suffer from **context window decay**—hallucinating constraints, forgetting negative findings, and repeating discarded approaches.

This skill governs the generation of the authoritative, zero-bloat **Deterministic State-Transfer Document** (`HANDOFF.md` at workspace root or `handoff.md` within sub-repos). It replaces narrative summaries with exact file pointers, computational sensors, and deterministic state vectors to ensure incoming agents boot in seconds with zero discovery loops.

---

## The 5 Invariants of Deterministic State Transfer

1. **No-Duplication Discipline (Zero Narrative / Snippet Bloat)**:
   - Strictly forbidden: Conversational summaries, code snippets, pasted diffs, or chat narration.
   - Rely strictly on `git status`, `git diff --stat`, and exact `path/to/file:line_range` pointers (with clickable markdown file links).
2. **Pinned Working Set (Eliminate Discovery Loops)**:
   - Explicitly separate **Target Files** (the exact 2–4 files actively created or modified) from **Reference Contracts** (1–3 read-only interface, schema, or config files to conform to).
   - Prevents incoming agents from wasting turns executing blind `grep` or `find` discovery searches.
3. **Computational Sensors (Executable Verification Gates)**:
   - Every active or pending task MUST supply the exact CLI command (unit test, linter, or parity check) that proves the task is passing.
   - If a task is mid-flight or failing, record the exact one-line error string from the authentic failure trace.
4. **Negative Knowledge (What Failed & Why)**:
   - Mandatory section for disproven hypotheses, failing libraries, dead-end tool loops, or invalid workarounds.
   - Guarantees the incoming agent will never repeat failed experiments or repeat discarded strategies.
5. **Cold-Start Execution Sequence (Imperative 3-Step Boot)**:
   - Conclude every handoff with an imperative, zero-ambiguity 3-step boot sequence defining the exact first file to read, the exact first command to run, and the exact surgical action to take.

---

## Handoff Template Specification (`HANDOFF.md`)

When `/handoff` is triggered, persist state into `HANDOFF.md` adhering strictly to this schema:

```markdown
# Session Handoff: [Task / Feature Name]

## 1. Ground Truth & State Vector
- **Workspace Root**: `C:\Coding\VSCode\Quant System`
- **Active Branch**: `develop2` (Staging) | `master` (Production)
- **Git Commit**: `<hash>` (`<commit title>`)
- **Working Tree**: `git status --porcelain` (Clean / List modified paths)
- **Protocol Graph State**: `<PHASE_ID | IDLE>` (`python scripts/protocol_graph.py status`)
- **Fleet Version Parity**: `vX.Y.Z` (`python scripts/bump_version.py --check`)
- **Deployment Ports**: Production :8095 | Staging :8096 | IBKR Gateway :4001

## 2. Pinned Working Set
### Target Files (Actively Modified)
- `path/to/file1.py:line_start-line_end` - [Brief 1-line purpose]
- `path/to/file2.js:line_start-line_end` - [Brief 1-line purpose]

### Reference Contracts (Read-Only Authority)
- `common-lib/path/to/schema.py:line_range` - [Contract/Schema to conform to]
- `path/to/config.py:line_range` - [Config definition / API parameters]

## 3. Computational Sensors (Verification Commands)
- **Primary Gate**: `<exact test command>` (e.g. `pytest tests/test_reproduce_<issue>.py`) -> `[PASS | FAIL]`
- **Regression Suite**: `<exact test suite command>` (e.g. `./verify.sh` or `node frontend/tests/test_*.js`) -> `[PASS | FAIL]`
- **Mid-Flight Failing Sensor (if in-flight)**:
  - Command: `<exact failing command>`
  - One-Line Trace: `<exact single-line error message>`

## 4. Negative Knowledge (What Failed & Why)
- **Dead End 1**: [Rejected approach / hypothesis] -> [Reason / exact error why it failed]
- **Dead End 2**: [Broken tool / invalid workaround] -> [Why it was abandoned]

## 5. Cold-Start Execution Sequence
1. **Inspect**: Open `path/to/target_file.py:line_range` to review `<state/function>`.
2. **Execute Sensor**: Run `<exact CLI verification command>` to verify baseline state.
3. **Execute Next Action**: Apply surgical edit to `<target file>` to resolve `<exact goal>`.

## 6. 1-Sentence Resume Prompt
> "Resume work on [Task ID / Name]. State is at [Protocol Phase]. Review `HANDOFF.md`, inspect [Target File], and run Step 2 of the Cold-Start Sequence."
```

---

## Post-Handoff Guidance
Upon writing `HANDOFF.md`, verify git status, output the 1-sentence resume prompt, and instruct the user to open a fresh conversation for peak agent reasoning speed.
