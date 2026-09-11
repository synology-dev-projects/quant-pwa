# 📚 Quant System: System Architecture & Technical Design Documentation

Welcome to the central technical design documentation for the **Quant System**—an institutional-grade quantitative trading platform featuring options market structure analytics (GEX/DEX), historical tick data pipelines, algorithmic price levels, unusual options flow, AI-powered Discord alerts, and a mobile-first Quant AI PWA with Gemini & MCP integration.

---

## 🗺️ Documentation Directory & Architecture Map

| Document | Purpose & Scope |
| :--- | :--- |
| **[1. System Architecture Overview](file:///C:/Coding/VSCode/Quant%20System/docs/ARCHITECTURE_OVERVIEW.md)** | High-level system architecture, microservices topology, data flow, and NAS deployment layout. |
| **[2. Database & Data Models](file:///C:/Coding/VSCode/Quant%20System/docs/DATABASE_AND_DATA_MODELS.md)** | Oracle database tables, DDL schemas, `db_catalog.yaml`, UUID staging `MERGE` patterns, and indexing. |
| **[3. APIs, Gateways & MCP Protocols](file:///C:/Coding/VSCode/Quant%20System/docs/APIS_AND_GATEWAYS.md)** | `gexdex-api` endpoints, `quant-pwa` FastAPI Gateway, SSE streaming lifecycles, and Model Context Protocol (MCP) tools. |
| **[4. ETL Data Pipelines & Scrapers](file:///C:/Coding/VSCode/Quant%20System/docs/ETL_PIPELINES_AND_INGESTION.md)** | Deep dive into `quant-level`, `ibkr-historical`, `mm-dex-gex`, and `unusual-option-flow` pipelines and financial math. |
| **[5. Frontend & Client Applications](file:///C:/Coding/VSCode/Quant%20System/docs/FRONTEND_AND_BOT_APPLICATIONS.md)** | Architecture of `quant-pwa` (HTML5 Canvas engine, SWR, Lightbox, Service Worker) and `discord-quant-bot`. |
| **[6. Infrastructure, Docker & Containers](file:///C:/Coding/VSCode/Quant%20System/docs/INFRASTRUCTURE_AND_CICD.md)** | Synology NAS Docker orchestration, network topology, Cloudflare edge routing, and resource management. |
| **[7. DevOps, CI/CD & Automated Verification](file:///C:/Coding/VSCode/Quant%20System/docs/DEVOPS_AND_CICD.md)** | Consolidated 4-stage GitHub Actions CI/CD pipeline, Master Agent Test Runner CLI, and pre-commit hooks. |

---

## 🏗️ High-Level System Diagram

```mermaid
graph TB
    subgraph ExternalSources [🌐 External Data Feeds & Platforms]
        TE[TradingEdge Portal / Mighty Networks]
        IBKR[Interactive Brokers Gateway]
        GeminiCloud[Google Gemini AI 2.5/3.5/3.7]
    end

    subgraph SynologyNAS [🏠 Synology NAS Infrastructure (192.168.1.68)]
        subgraph DataLayer [🗄️ Persistence & Core Engine]
            OracleDB[(Oracle Database)]
            CommonLib[📦 common-lib & common_config]
        end

        subgraph IngestionLayer [⚙️ ETL Pipelines]
            PipeQL[quant-level-pipeline]
            PipeIBKR[ibkr-historical-data-pipeline]
            PipeGEX[mm-dex-gex-pipeline]
            PipeFlow[unusual-option-flow-pipeline]
        end

        subgraph ServiceLayer [⚡ Microservices & BFF]
            GexDexAPI[📊 gexdex-api :8090/:8091]
            Gateway[🛡️ quant-pwa Gateway :8000]
        end

        subgraph ClientLayer [📱 Clients]
            PWAFrontend[📱 quant-pwa Frontend :8095/:8096]
            DiscordBot[🤖 discord-quant-bot]
        end
    end

    subgraph EdgeRouting [☁️ Cloudflare Edge]
        CFTunnel[Cloudflare Zero-Port Tunnel]
    end

    subgraph EndUsers [👨‍💻 End-User Interfaces]
        MobilePWA[📱 Mobile PWA / Safari & Chrome]
        DiscordChannel[💬 Discord Server Channel]
    end

    TE --> PipeQL
    TE --> PipeGEX
    TE --> PipeFlow
    TE --> GexDexAPI
    IBKR --> PipeIBKR

    PipeQL --> OracleDB
    PipeIBKR --> OracleDB
    PipeGEX --> OracleDB
    PipeFlow --> OracleDB

    OracleDB <--> GexDexAPI
    GexDexAPI <--> Gateway
    Gateway <--> GeminiCloud

    Gateway <--> PWAFrontend
    CFTunnel <--> PWAFrontend
    MobilePWA <--> CFTunnel
    DiscordBot <--> GexDexAPI
    DiscordBot <--> DiscordChannel
```
