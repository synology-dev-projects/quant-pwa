# 📚 Quant System: System Architecture & Technical Design Documentation

Welcome to the central technical design documentation for the **Quant System**—an institutional-grade quantitative trading platform featuring options market structure analytics (GEX/DEX), historical tick data pipelines, algorithmic price levels, unusual options flow, AI-powered Discord alerts, and a mobile-first Quant AI PWA with Gemini & MCP integration.

---

## 🗺️ Documentation Directory & Architecture Map

| Document | Purpose & Scope |
| :--- | :--- |
| **[1. System Architecture Overview](ARCHITECTURE_OVERVIEW.md)** | High-level system architecture, microservices topology, data flow, and NAS deployment layout. |
| **[2. Database & Data Models](DATABASE_AND_DATA_MODELS.md)** | PostgreSQL / TimescaleDB hypertable schemas, UUID staging patterns, and indexing. |
| **[3. APIs, Gateways & MCP Protocols](APIS_AND_GATEWAYS.md)** | `quant-pwa` FastAPI Gateway, SSE streaming lifecycles, and Model Context Protocol (MCP) tools. |
| **[4. ETL Data Pipelines & Scrapers](ETL_PIPELINES_AND_INGESTION.md)** | Deep dive into `quant-level`, `ibkr-historical`, `gexdex-snapshot`, `market-confluence`, and `unusual-option-flow` pipelines. |
| **[5. Frontend & Client Applications](FRONTEND_AND_BOT_APPLICATIONS.md)** | Architecture of `quant-pwa` (HTML5 Canvas engine, SWR, Lightbox, Service Worker) and mobile-first PWA. |
| **[6. Infrastructure, Docker & Containers](INFRASTRUCTURE_AND_CICD.md)** | Synology NAS Docker orchestration, network topology, Cloudflare edge routing, and resource management. |
| **[7. DevOps, CI/CD & Automated Verification](DEVOPS_AND_CICD.md)** | Consolidated GitHub Actions CI/CD deployment, topological fleet push orchestrator, and pre-commit hooks. |

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
