# 🛠️ DevOps, Consolidated CI/CD Pipeline & Automated Verification

> **Standard:** Institutional-Grade Automated CI/CD & Verification Lifecycle  
> **Target Production Node:** Synology NAS (`192.168.1.68`, DSM 7.2 Container Manager)  
> **CI/CD Orchestrator:** GitHub Actions Self-Hosted & Hosted Runners (`.github/workflows/deploy.yml`)

---

## 1. Overview & Architectural Philosophy

The Quant System CI/CD architecture implements a **Shift-Left Verification** pattern designed to provide zero-defect deployments on resource-constrained Synology NAS hardware. 

Key engineering mandates:
1. **Zero Broken Builds on Master:** Every PR and commit to `develop2` or `master` is gated by multi-tier automated test suites.
2. **Fast-Fail Pre-Flight Gate (<10s):** Syntax errors, AST compilation failures, and unit test regressions fail immediately on the hosted runner before consuming NAS CPU/RAM or Docker build cycles.
3. **Containerized In-Image Verification:** Pytest runs directly inside the newly built Docker container layer before live deployment.
4. **Live In-Situ Smoke Probes:** Following container launch, an automated smoke probe suite tests all critical endpoints, auth tokens, database queries, and diagnostics before declaring the build green.
5. **Compute Optimization & Ephemeral Teardown:** Production (`master`) deployments automatically tear down ephemeral development containers to keep Synology NAS RAM overhead within target bounds (<1.5 GB total).

---

## 2. The Consolidated 4-Stage CI/CD Pipeline

The GitHub Actions workflow (`quant-pwa/.github/workflows/deploy.yml`) is structured into four sequential, fail-fast stages:

```mermaid
graph TD
    subgraph Stage1 [Stage 1: Pre-Flight Validation Gate]
        A1[Code Commit / Push] --> A2[Python AST & Syntax Check]
        A2 --> A3[Node.js 20+ DOM / Component Tests]
        A3 --> A4[Gateway Fast Unit Tests (pytest -m 'not integration')]
    end

    subgraph Stage2 [Stage 2: Prepare Synology Deployment & Secrets]
        A4 -->|Pass| B1[Resolve Target Path /git-repos/{env}/quant-pwa]
        B1 --> B2[Git Checkout / Pull Latest Branch]
        B2 --> B3[Hydrate .env Secrets from GitHub Vault]
    end

    subgraph Stage3 [Stage 3: Docker Build & Containerized Pytest Gate]
        B3 --> C1[Docker Compose Build Gateway & Frontend]
        C1 --> C2[Run Pytest Inside Fresh Gateway Image]
        C2 --> C3[Validate Multi-Path version.json & Mocks]
    end

    subgraph Stage4 [Stage 4: Launch Containers & Live Smoke Probes]
        C3 -->|Pass| D1[Docker Compose Up -d --force-recreate]
        D1 --> D2[Tear Down Ephemeral Develop Containers (if master)]
        D2 --> D3[Health-Check Polling /api/health]
        D3 --> D4[Execute scripts/smoke_test.py (Live Probes)]
        D4 --> D5[Verify 100% Endpoints 200 OK]
    end
```

### Stage 1: Pre-Flight Validation Gate
* **Environment:** GitHub Actions Hosted Runner (`ubuntu-latest` / runner host).
* **Actions:**
  - Installs Python 3.11+ and Node.js 20+ via `actions/setup-node@v4`.
  - Runs host AST compilation checks: `python -m py_compile **/*.py`.
  - Executes Version Parity Check: `python scripts/bump_version.py --check`.
  - Executes Node.js DOM and Settings Modal unit tests:
    * `node frontend/tests/test_settings_flow_modal.js`
    * `node frontend/tests/test_cockpit_view.js`
    * `node frontend/tests/test_vertical_table_ui.js`
    * `node frontend/tests/audit_layout.js` (UI-01 Layout Geometry Verification)
  - Installs Gateway dependencies (`fastapi`, `httpx`, `pytest`, `pydantic`) and executes offline unit tests:
    ```bash
    pytest -m "not integration" gateway/tests/
    ```
* **Latency:** ~6–10 seconds.
* **Failure Impact:** Halts pipeline immediately without touching the NAS.

#### 1.1 Automated UI & Layout Geometry Verification Engine (UI-01 / `audit_layout.js`)
To guarantee visual stability, mobile responsiveness, and zero-defect UI layouts across heterogeneous display form factors, the pre-flight gate executes an automated headless CSS geometry analyzer [`frontend/tests/audit_layout.js`](file:///C:/Coding/VSCode/Quant%20System/quant-pwa/frontend/tests/audit_layout.js):

1. **Responsive Viewport Auditing:**
   - Evaluates CSS cascade across simulated viewport widths: **375px (Mobile)**, **768px (Tablet)**, and **1280px (Desktop)**.
   - Parses `@media (max-width: ...)` and `@media (min-width: ...)` query blocks to compute viewport-specific layout properties.
2. **Touch-Target Accessibility (WCAG 2.1 AA):**
   - Validates that all interactive controls (`.btn`, `.nav-item`, `.tab-btn`, `.settings-btn`, `.modal-close`) meet or exceed minimum touch target dimensions ($\ge 44\text{px}$ tap height/width, or $\ge 36\text{px}$ with minimum $8\text{px}$ bounding hit-box padding).
3. **Modal Box-Sizing & Alignment Geometry:**
   - Validates `.modal-body` and `.settings-actions` containers for `box-sizing: border-box`, `width: 100%`, and zero negative margins (`margin-left: 0`, `margin-right: 0`).
   - Ensures `.btn-modal-action` elements render with `flex: 1` and centered content justification without clipping or visual bleeding.
4. **Zero Horizontal Layout Overflow:**
   - Probes Ticker Cockpit Panels (1, 2, and 3) and Bloomberg Options Flow Table container for horizontal scroll containment (`overflow-x: auto` / `overflow: hidden`).
   - Ensures root document elements (`html, body`) enforce strict horizontal scroll locking (`overflow-x: hidden`).
5. **Execution Latency:**
   - Executes in **`< 300ms`** in pure Node.js without requiring Chromium/Puppeteer runtime overhead.

### Stage 2: Prepare Synology Deployment Directory & Secrets
* **Environment:** Synology NAS Self-Hosted Runner.
* **Target Path Resolution:**
  - `master` branch $\rightarrow$ `/volume2/homes/rachardv/git-repos/master/quant-pwa`
  - `develop` / `develop2` branch $\rightarrow$ `/volume2/homes/rachardv/git-repos/develop/quant-pwa`
* **Secret Hydration:** Generates root `.env` and `gateway/.env` containing:
  - `APP_PASSCODE`, `JWT_SECRET`, `GEMINI_API_KEY`
  - `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
  - `GEXDEX_API_URL`, `CLOUDFLARE_TUNNEL_TOKEN`

### Stage 3: Docker Build & Containerized Pytest Gate
* **Environment:** Synology NAS Docker Engine.
* **Build Step:** Executes `docker compose build` using build caches for `quant-gateway` and `quant-frontend`.
* **In-Container Testing:** Runs the full Gateway unit test suite inside the newly built Docker image before creating live daemon containers:
  ```bash
  docker compose run --rm --no-deps quant-gateway \
    pytest -m "not integration" tests/
  ```
* **Features Verified:**
  - FastAPI router instantiation and dependency injection.
  - Multi-path `version.json` semantic discovery (`/app/version.json` vs root vs mock fallback).
  - Defensive error handling, JWT auth lifecycle, and mock database queries.

### Stage 4: Launch Containers & Execute Live Smoke Probes
* **Environment:** Synology NAS Production / Staging Port.
* **Container Lifecycle:**
  - Launches services: `docker compose --profile production up -d --remove-orphans`
  - If deploying to `master`, cleans up ephemeral `develop` containers to release memory:
    ```bash
    if [ -d "/volume2/homes/rachardv/git-repos/develop/quant-pwa" ]; then
      cd /volume2/homes/rachardv/git-repos/develop/quant-pwa
      docker compose down --remove-orphans || true
    fi
    ```
* **Liveness Wait Loop:** Polls `http://localhost:${GATEWAY_PORT}/api/health` with backoff (up to 30s) until HTTP 200 OK is received.
* **Automated In-Situ Smoke Probes:** Executes `python3 scripts/smoke_test.py --host localhost --port ${GATEWAY_PORT}`:
  1. `GET /api/health` — Gateway uptime & service health.
  2. `POST /api/auth/login` — Authentication & JWT bearer token issuance.
  3. `GET /api/options-flow/recent` — Postgres Options Flow table retrieval.
  4. `GET /api/quant-levels/current` — Postgres Quant Levels price ladders.
  5. `GET /api/gexdex/SPY` — Real-time Market Maker gamma/delta exposure.
  6. `GET /api/market-status` — Exchange trading hours & session state.
  7. `GET /api/diagnostics/logs` — In-memory ring buffer logging endpoint.

---

## 3. Master Agent Test Runner CLI (`scripts/agent_test_runner.py`)

The **Master Agent Test Runner** provides a unified CLI for AI agents and developers to execute tests across all 6 repositories from the root workspace.

### CLI Syntax & Flags
```bash
# Run all deterministic offline unit tests across all repositories
python scripts/agent_test_runner.py --unit

# Run unit tests filtered to a single repository
python scripts/agent_test_runner.py --unit --repo quant-pwa
python scripts/agent_test_runner.py --unit --repo common-lib

# Run live integration & scraper tests (requires network/credentials)
python scripts/agent_test_runner.py --integration

# Run live hardware smoke probes against Synology NAS
python scripts/agent_test_runner.py --smoke --host 192.168.1.68 --port 8095

# Run the complete test suite (Unit + Integration + Smoke)
python scripts/agent_test_runner.py --all --host 192.168.1.68 --port 8095
```

### Monospace ASCII Reporting Format
The test runner outputs structured test counts, execution durations, and pass/fail states in a monospace matrix:

```text
+==================================================================================================+
| Suite / Target                                   | Repo               | Type  | Status | Passed / Total | Time (ms)  |
+==================================================================================================+
| common-lib pytest (Unit)                         | common-lib         | Unit  | PASS   | 18/18          | 438.1 ms   |
| discord-quant-bot pytest (Unit)                  | discord-quant-bot  | Unit  | PASS   | 12/12          | 512.4 ms   |
| gexdex-api pytest (Unit)                         | gexdex-api         | Unit  | PASS   | 15/15          | 684.2 ms   |
| ibkr-historical-data-pipeline pytest (Unit)      | ibkr-historical    | Unit  | PASS   | 24/24          | 891.0 ms   |
| quant-level-pipeline pytest (Unit)               | quant-level        | Unit  | PASS   | 20/20          | 610.8 ms   |
| unusual-option-flow-pipeline pytest (Unit)       | unusual-flow       | Unit  | PASS   | 16/16          | 573.5 ms   |
| quant-pwa Gateway pytest (Unit)                  | quant-pwa          | Unit  | PASS   | 22/22          | 920.1 ms   |
| quant-pwa Frontend Settings Modal (Node DOM)     | quant-pwa          | Unit  | PASS   | 10/10          | 210.4 ms   |
| quant-pwa Gateway Smoke Probe (192.168.1.68:8095)| quant-pwa          | Smoke | PASS   | 7/7            | 345.2 ms   |
+--------------------------------------------------------------------------------------------------+
| Status: ALL SUITES PASSED | 9/9 Suites OK | 144/144 Tests Passed               Total Time: 5185.7 ms |
+==================================================================================================+
```

---

## 4. Pre-Commit Hook Standardization

All 6 active repositories contain a standardized `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-added-large-files
        args: ['--maxkb=1000']
  - repo: https://github.com/psf/black
    rev: 24.8.0
    hooks:
      - id: black
        language_version: python3
  - repo: https://github.com/pycqa/flake8
    rev: 7.1.1
    hooks:
      - id: flake8
        args: ['--max-line-length=120', '--extend-ignore=E203,W503']
```

### Workspace Installation
To install git hooks across all repositories in one command:
```bash
python scripts/install_all_hooks.py
```

---

## 5. Repository Promotion Lifecycle

1. **Feature Development:** Completed on `develop2` branch.
2. **Local Pre-Flight:** Verified using `python scripts/agent_test_runner.py --unit`.
3. **Staging Deploy:** Pushed to `origin develop2`, deployed to staging port `8096`.
4. **Master Promotion:** Merged to `master` and pushed:
   ```bash
   git checkout master
   git pull origin master --rebase
   git merge develop2
   git push origin master --no-verify
   git checkout develop2
   ```
5. **CI/CD Master Deployment:** GitHub Actions automatically executes the 4 stages, deploys to port `8095`, tears down develop containers, runs live smoke probes, and marks build green.
