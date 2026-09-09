---
name: captain-orchestrator
description: Coordinates cross-repository features, drafts implementation plans, checks dependency order, and dispatches parallel subagent tasks.
---

# Captain Orchestrator Skill

When leading a task across the Quant System:

## 1. Sequence & Dependency Order
Always sequence cross-repository tasks in dependency order:
1. **Core Library:** `common-lib` / `common_config`
2. **Backends / APIs:** `gexdex-api` & `gateway`
3. **Pipelines / Consumers:** `quant-level-pipeline`, `mm-dex-gex-pipeline`, `unusual-option-flow-pipeline`
4. **Clients:** `quant-pwa` & `discord-quant-bot`

## 2. Planning Protocol
1. Draft an `implementation_plan.md` in `implementation_plans/`.
2. List exact files to `[NEW]`, `[MODIFY]`, or `[DELETE]`.
3. Define the local test commands (`verify.sh` / `pytest`).
4. Wait for user approval before dispatching subagent crews.
