# 🧠 Financial RAG Reasoning Engine

> **Multi-layer financial intelligence system** — GPT-4.1 synthesis · SEC EDGAR live filings · Real-time market data · Reddit sentiment · Interactive knowledge graphs

---

## 📋 Table of Contents

1. [Concept Overview](#-concept-overview)
2. [System Architecture](#-system-architecture)
3. [Data Layers](#-data-layers)
4. [Key Features](#-key-features)
5. [Knowledge Boundaries & System Constraints](#-knowledge-boundaries--system-constraints)
6. [Setup & Run Instructions](#-setup--run-instructions)
7. [API Reference](#-api-reference)
8. [Use Case Examples](#-use-case-examples)
9. [Query Routing Logic](#-query-routing-logic)
10. [Output Schema](#-output-schema)
11. [Project Structure](#-project-structure)
12. [Technology Stack](#-technology-stack)
13. [Evaluation Guide for Judges](#-evaluation-guide-for-judges)

---

## 💡 Concept Overview

The **Financial RAG Reasoning Engine** is a production-grade Retrieval-Augmented Generation system designed to answer financial intelligence questions with structured, multi-source analysis. It goes beyond simple document search — it **detects contradictions** between what companies officially disclose and what retail investors believe.

Given a natural language question about a stock or portfolio, the system:

1. **Routes** the question to the appropriate analysis path (single stock, comparison, portfolio-wide, or general)
2. **Fans out** across 5 data layers in parallel — news, social media, SEC filings, live prices, and Reddit buzz
3. **Synthesizes** a structured analysis using GPT-4.1 with Chain-of-Thought reasoning
4. **Generates** an interactive knowledge graph showing entities, relationships, and detected contradictions

**Core insight:** The most actionable financial signal is often the *gap* between official regulatory disclosures and retail investor sentiment. The engine is specifically designed to find and surface these contradictions.

---

## 🏗️ System Architecture

```
User Query (natural language)
        │
        ▼
┌───────────────────────────────┐
│  Query Classifier             │
│  + Ticker Resolver            │  ── Regex + Company Name Map + LLM Fallback
└────────────┬──────────────────┘
             │  Route: SINGLE / COMPARE / CROSS_PORTFOLIO / GENERAL / OUT_OF_SCOPE
             ▼
┌────────────────────────────────────────────────────────────────┐
│              Parallel Retrieval  (asyncio fan-out)             │
│                                                                │
│  Layer 1     Layer 2     Layer 3      Layer 4     Layer 5      │
│  News        Social      SEC EDGAR    Live Price  Reddit Buzz  │
│  Finnhub     JSON        10-K/10-Q/8-K Finnhub    ApeWisdom   │
│  ChromaDB    ChromaDB    ChromaDB     Direct API  ChromaDB    │
│  TTL: 3d     Static      TTL: 30d     Real-time   TTL: 1d     │
└──────────────────────────┬─────────────────────────────────────┘
                           │  Unified Context Dict
                           ▼
          ┌──────────────────────────────────┐
          │  GPT-4.1 Synthesis Engine        │
          │  Chain-of-Thought (5-step)       │
          │  Pydantic Structured Output      │
          └──────────────┬───────────────────┘
                         │
            ┌────────────┴────────────┐
            │                         │
            ▼                         ▼
   AnalysisOutput              KnowledgeGraph
 (structured JSON)           (nodes + edges)
 sentiment, risk,            pyvis HTML render
 contradiction, summary      per session_id
```

### Storage & Memory

| Component | Technology | Scope |
|-----------|-----------|-------|
| Vector store | ChromaDB (persistent Docker volume) | Cross-session |
| Conversation memory | In-memory session store | Per-session, 1h TTL, max 10 turns |
| Knowledge graphs | In-memory graph store | Per-session |
| Embeddings | OpenAI `text-embedding-3-small` (1536-dim) | Persisted in ChromaDB |

---

## 📊 Data Layers

### Layer 1 — News Articles
- **Source:** Finnhub REST API
- **What:** Recent news articles with headline + summary for each ticker
- **TTL:** 3 days (auto-refreshed on stale queries)
- **Signal type:** Fundamental events, institutional moves, earnings coverage

### Layer 2 — Social Media Posts
- **Source:** Static curated dataset (`data/layer-2-social.json`)
- **What:** Twitter/Reddit-style posts from retail investors, scored by engagement (likes × 1.0, retweets × 2.0, views × 0.1)
- **TTL:** Static — loaded once at startup
- **Signal type:** Retail sentiment, narrative momentum

### Layer 3 — SEC EDGAR Filings
- **Source:** SEC EDGAR REST API (free, no key required)
- **What:** Official regulatory filings — 10-K (annual), 10-Q (quarterly), 8-K (material events)
- **TTL:** 30 days
- **Signal type:** Official risk disclosures, MD&A, material events (earnings, M&A, CEO changes)
- **Key sections extracted:** Risk Factors, Management Discussion & Analysis, 8-K event body

### Layer 4 — Live Market Price
- **Source:** Finnhub real-time API
- **What:** Current price, change %, day high/low, previous close, open, market cap
- **TTL:** Real-time (fetched on every query)
- **Fallback:** Mock data for seed tickers if Finnhub is unreachable (`is_live: false` flag set)

### Layer 5 — Reddit Buzz (ApeWisdom)
- **Source:** ApeWisdom API (free, no key required)
- **What:** Quantitative Reddit activity — rank across r/wallstreetbets and finance subreddits, 24h mention count, upvote count, momentum direction
- **TTL:** 1 day
- **Signal type:** Community momentum, retail conviction, trending status (RISING / FALLING / STABLE / NEW ENTRY)

---

## ✨ Key Features

### Multi-Layer Contradiction Detection
The synthesis engine is explicitly designed to identify contradictions — for example, a stock whose 10-K Risk Factors warn of existential competitive threats while Reddit momentum is **RISING** and retail sentiment is overwhelmingly bullish.

### Parallel Retrieval (Fan-out / Fan-in)
All 5 data layers are retrieved simultaneously using `asyncio.gather()`. Total query latency is bounded by the slowest single layer, not the sum of all layers.

### On-Demand Ingestion for Any Ticker
The system handles **any publicly traded company**, not only the 10 seed tickers. When a non-seed ticker is queried, the system automatically:
- Fetches news from Finnhub
- Fetches Reddit buzz from ApeWisdom
- Looks up the SEC CIK dynamically via `https://www.sec.gov/files/company_tickers.json` and ingests filings

### Multi-Turn Conversation Memory
Sessions (identified by UUID) persist the last 10 Q&A turns. The classifier uses conversation history to resolve follow-up references like *"Tell me more about the other one"* or *"Compare their risk levels"*.

### Structured Output with Pydantic
Every response is validated against a strict Pydantic schema — no free-form JSON. The output always includes `sentiment`, `risk_score`, `key_contradiction`, `summary`, `tickers_discussed`, and a `knowledge_graph`.

### Interactive Knowledge Graph
After every query, an interactive pyvis graph is generated and stored per session. Nodes are typed (Company, Filing, Sentiment, Event, Price) with colour-coded edges (DISCLOSES_RISK, CONTRADICTS, ALIGNS, WARNS_OF).

### Query Routing Intelligence
The system classifies every query before retrieval using a two-stage resolver (regex + LLM fallback) and routes to one of five paths — single stock, comparison, cross-portfolio, general, or out-of-scope.

---

## 🚧 Knowledge Boundaries & System Constraints

> **This section is critical for fair evaluation.** The system has explicit design boundaries — judges should test within these constraints to assess the system's intended capabilities, and note edge cases as expected behaviour rather than bugs.

### Seed Tickers (Pre-loaded at Startup)

The following 10 tickers are ingested automatically when the system starts. Queries about these tickers receive the fastest, most complete responses because all data layers are pre-cached:

| Ticker | Company | Sector |
|--------|---------|--------|
| `AAPL` | Apple Inc. | Technology |
| `BA` | Boeing Company | Aerospace & Defense |
| `GME` | GameStop Corp. | Consumer Retail |
| `JPM` | JPMorgan Chase & Co. | Financial Services |
| `NEE` | NextEra Energy Inc. | Utilities / Renewable Energy |
| `NVDA` | NVIDIA Corporation | Semiconductors / AI |
| `PFE` | Pfizer Inc. | Pharmaceuticals |
| `PLTR` | Palantir Technologies | Data Analytics / AI |
| `TSLA` | Tesla Inc. | Automotive / EV |
| `XOM` | ExxonMobil Corporation | Energy / Oil & Gas |

### Company Name Resolution (name_map & company_name_map)

The system resolves the following natural language company names to tickers automatically — no ticker symbol is required in the query:

| Name Variant(s) | Resolves To | Pre-cached? |
|---|---|---|
| `apple`, `iphone`, `tim cook` | `AAPL` | ✅ Seed |
| `boeing` | `BA` | ✅ Seed |
| `gamestop`, `game stop`, `roaring kitty` | `GME` | ✅ Seed |
| `jpmorgan`, `jp morgan`, `j.p. morgan` | `JPM` | ✅ Seed |
| `nextera`, `nextera energy` | `NEE` | ✅ Seed |
| `nvidia`, `jensen huang` | `NVDA` | ✅ Seed |
| `pfizer` | `PFE` | ✅ Seed |
| `palantir`, `alex karp` | `PLTR` | ✅ Seed |
| `tesla`, `elon`, `cybertruck` | `TSLA` | ✅ Seed |
| `exxon`, `exxonmobil`, `exxon mobil` | `XOM` | ✅ Seed |
| `microsoft` | `MSFT` | ⏱️ On-demand |
| `amazon` | `AMZN` | ⏱️ On-demand |
| `google`, `alphabet` | `GOOGL` | ⏱️ On-demand |
| `meta` | `META` | ⏱️ On-demand |
| `netflix` | `NFLX` | ⏱️ On-demand |
| `amd` | `AMD` | ⏱️ On-demand |
| `intel` | `INTC` | ⏱️ On-demand |
| `uber` | `UBER` | ⏱️ On-demand |
| `airbnb` | `ABNB` | ⏱️ On-demand |
| `salesforce` | `CRM` | ⏱️ On-demand |

### On-Demand Tickers
Any ticker **not** in the seed list triggers an on-demand ingestion pipeline before the query is answered. First-query latency for a new ticker is higher (~30–60 seconds for SEC filing ingestion due to SEC's 10 req/s rate limit). Subsequent queries use the cache and respond at normal speed.

### Cache TTL Summary

| Layer | Data Source | TTL |
|-------|------------|-----|
| Layer 1 — News | Finnhub | 3 days |
| Layer 2 — Social | Static JSON | Never expires |
| Layer 3 — SEC Filings | SEC EDGAR | 30 days |
| Layer 4 — Live Price | Finnhub | Real-time (no cache) |
| Layer 5 — Reddit Buzz | ApeWisdom | 1 day |

### Out-of-Scope Query Handling
The system **politely rejects** non-financial questions without running any retrieval pipeline. Zero retrieval cost for rejected queries.

Examples of rejected queries: *"Tell me a joke"*, *"What's the weather like?"*, *"Who won the football match?"*, *"Hello, how are you?"*

### Layer 2 Social Data
The social media layer uses a curated static dataset — it does not make live social API calls. Social sentiment reflects the dataset's snapshot, not real-time Twitter/Reddit posts. Live social data would require Twitter API credentials.

### Session Memory Scope
Conversation history is **in-memory only** — it is cleared if the backend container restarts. This is an intentional design trade-off for the hackathon demo environment (no Redis/database dependency).

### SEC Filing Coverage
SEC filings are fetched for the **2 most recent** filings per type (10-K, 10-Q, 8-K) per ticker. Historical filings beyond the 2 most recent are not retrieved.

### Reddit Buzz Coverage
ApeWisdom tracks approximately 800 tickers. Tickers with very low Reddit activity may not appear in ApeWisdom's rankings — Layer 5 data will be absent for those queries, and the system handles this gracefully without error.

---

## ⚙️ Setup & Run Instructions

### Prerequisites

- Docker and Docker Compose installed
- OpenAI API key — for GPT-4.1 synthesis and `text-embedding-3-small` embeddings
- Finnhub API key — for live news and price data (free tier at [finnhub.io](https://finnhub.io))

### 1. Clone & Configure

```bash
git clone <repository-url>
cd <repository-directory>
```

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=sk-...
FINNHUB_API_KEY=your_finnhub_key_here
```

### 2. Launch All Services

```bash
docker compose up --build
```

This starts three services in dependency order:

1. **ChromaDB** on port `8000` — vector database with a persistent volume
2. **Backend** on port `8080` — FastAPI + Uvicorn; waits 8s for ChromaDB, then seeds all 10 tickers automatically
3. **Frontend** on port `5173` — Vite React dev server

> ⏱️ **First startup takes 2–5 minutes.** The backend ingests news, SEC filings, and Reddit buzz for all 10 seed tickers automatically. Subsequent starts are fast because ChromaDB persists data across restarts.

### 3. Access the Application

| Service | URL |
|---------|-----|
| Frontend UI | http://localhost:5173 |
| Backend API (Swagger docs) | http://localhost:8080/docs |
| Architecture diagram | http://localhost:8080/api/architecture |
| Health check | http://localhost:8080/api/health |

### 4. Verify System Health

```bash
curl http://localhost:8080/api/health
```

Expected response:
```json
{
  "status": "healthy",
  "components": {
    "chromadb": {
      "status": "online",
      "counts": {
        "news": 120,
        "social": 50,
        "sec_filings": 240,
        "reddit_buzz": 10
      },
      "total_documents": 420
    },
    "session_store": {
      "status": "online",
      "active_sessions": 0,
      "type": "in-memory",
      "max_turns": 10,
      "ttl_seconds": 3600
    },
    "seed_tickers": ["AAPL", "BA", "GME", "JPM", "NEE", "NVDA", "PFE", "PLTR", "TSLA", "XOM"]
  }
}
```

### 5. Manual Re-ingestion (Optional)

Force a fresh data pull for all layers:

```bash
# Re-ingest all layers
curl -X POST http://localhost:8080/api/ingest

# Check current document counts
curl http://localhost:8080/api/ingest/status
```

### Running Without Docker (Development)

```bash
# Start ChromaDB separately
docker run -p 8000:8000 -e IS_PERSISTENT=TRUE chromadb/chroma:latest

# Backend
cd backend
pip install -r requirements.txt
CHROMA_HOST=localhost uvicorn main:app --host 0.0.0.0 --port 8080 --reload

# Frontend
cd frontend
npm install
npm run dev
```

---

## 📡 API Reference

### `POST /api/query` — Main RAG Pipeline

The primary endpoint. Accepts a natural language question and returns structured analysis.

**Request body:**
```json
{
  "question": "Is Tesla a risky investment right now?",
  "tickers": ["TSLA"],
  "session_id": "optional-uuid-for-multi-turn"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `question` | ✅ | Natural language question (3–500 chars) |
| `tickers` | ❌ | Optional list — auto-resolved from question if omitted |
| `session_id` | ❌ | UUID for multi-turn conversation — omit to start a new session |

**Response (abbreviated):**
```json
{
  "session_id": "generated-uuid",
  "query_type": "single_stock",
  "tickers": ["TSLA"],
  "analysis": {
    "summary": "Tesla presents MIXED signals — strong Reddit momentum contradicts 10-K risk disclosures.",
    "sentiment": "MIXED",
    "risk_score": "HIGH",
    "key_contradiction": "Reddit buzz is RISING (#4 on r/wallstreetbets) while Tesla's 10-K explicitly warns of significant EV competition risk from established automakers.",
    "risk_summary": "...",
    "tickers_discussed": ["TSLA"]
  },
  "knowledge_graph": {
    "nodes": [ ... ],
    "edges": [ ... ]
  },
  "raw_context": { ... }
}
```

### `GET /api/prices` — Live Batch Prices

```bash
GET /api/prices                    # All 10 seed tickers in parallel
GET /api/prices?tickers=GME,NVDA   # Specific tickers
```

Response: `{ "NVDA": { "current_price": 875.40, "change_pct": 1.54, "is_live": true, ... }, ... }`

### `GET /api/health` — System Status
Full health check including ChromaDB counts per layer, active session count, and seed ticker list.

### `GET /api/architecture` — Architecture Diagram
Opens a self-contained interactive HTML architecture diagram in the browser. No parameters required. Safe to call at any time — fully static.

### `GET /api/graph/view/{session_id}` — Knowledge Graph Viewer
Renders the interactive knowledge graph from a previous query session directly in the browser.

```bash
# Step 1: run a query and note the session_id in the response
# Step 2: open in browser
http://localhost:8080/api/graph/view/<session_id>
```

### `POST /api/ingest` — Re-ingest All Data
Triggers a full re-ingestion of all layers for all seed tickers.

### `GET /api/ingest/status` — Ingestion Status
Returns current ChromaDB document counts per collection.

### `GET /api/history/{session_id}` — Conversation History
Returns the full conversation history for a session.

### `DELETE /api/session/{session_id}` — Clear Session
Removes all conversation turns for a session.

### `GET /api/graph/sessions` — List Graph Sessions
Lists all session IDs that have a stored knowledge graph in memory.

---

## 💬 Use Case Examples

### Example 1 — Single Stock Deep Dive

**Query:**
```json
{
  "question": "What does Tesla's SEC filings say about competition risk, and how does that compare to what Reddit investors think?"
}
```

**What happens:** Retrieves Tesla's 10-K Risk Factors section, social media posts, Reddit buzz rank + momentum, and live price. GPT-4.1 reasons through each layer and surfaces the contradiction between official risk disclosures and retail sentiment.

**Expected output highlights:**
- `sentiment`: `MIXED` or `BEARISH`
- `key_contradiction`: 10-K warns of EV competition pressure while Reddit shows RISING momentum
- Knowledge graph: `TSLA_10K` → `CONTRADICTS` → `TSLA_RetailSentiment`

---

### Example 2 — Direct Ticker Comparison

**Query:**
```json
{
  "question": "Compare GME and NVIDIA — which is riskier?",
  "tickers": ["GME", "NVDA"]
}
```

**What happens:** Both tickers are retrieved in parallel across all 5 layers. The synthesizer produces a side-by-side analysis with a top recommendation and comparative risk scoring.

**Expected output highlights:**
- `query_type`: `comparison`
- `tickers_discussed`: `["GME", "NVDA"]`
- Verdict identifies the higher-risk ticker with reasoning grounded in SEC filings and Reddit momentum

---

### Example 3 — Cross-Portfolio Scan

**Query:**
```json
{
  "question": "Which stocks in our portfolio have the most bullish Reddit momentum right now?"
}
```

**What happens:** No ticker is named, so the system runs **cross-portfolio mode** — retrieves Reddit buzz for all 10 seed tickers simultaneously and synthesizes a ranked answer by ApeWisdom momentum direction.

**Expected output:** Ranked tickers by Reddit momentum with RISING/FALLING/STABLE/NEW ENTRY direction and mention counts for each.

---

### Example 4 — SEC Filing Intelligence

**Query:**
```json
{
  "question": "What are Boeing's most significant risk factors according to their latest 10-K?"
}
```

**What happens:** Layer 3 retrieves the most relevant chunks from Boeing's 10-K Risk Factors and MD&A sections via semantic vector search. The synthesizer produces a structured breakdown of disclosed risks.

---

### Example 5 — Multi-Turn Conversation

**Turn 1:**
```json
{ "question": "Analyse Apple for me.", "session_id": "my-session-abc" }
```

**Turn 2 (follow-up):**
```json
{ "question": "How does their Reddit buzz compare to their main semiconductor rival?", "session_id": "my-session-abc" }
```

**What happens:** The classifier reads conversation history, resolves *"their main semiconductor rival"* from context (resolves to `NVDA`), and runs a comparison without requiring the user to name the ticker explicitly.

---

### Example 6 — Out-of-Scope Rejection

**Query:**
```json
{ "question": "What is the weather in New York?" }
```

**Expected output:** Polite rejection with `query_type: out_of_scope`. No retrieval pipeline is triggered — zero API cost.

---

### Example 7 — On-Demand Non-Seed Ticker

**Query:**
```json
{ "question": "What does Microsoft's latest 8-K say about AI strategy?" }
```

**What happens:** MSFT is not a seed ticker. The system automatically looks up Microsoft's SEC CIK via `https://www.sec.gov/files/company_tickers.json`, ingests recent 10-K, 10-Q, and 8-K filings into ChromaDB, then answers the question. First-query latency is ~30–60s. All subsequent queries for MSFT are served from cache.

---

### Example 8 — Portfolio Risk Scan

**Query:**
```json
{
  "question": "Are there any stocks in the portfolio where insiders' official disclosures contradict what retail investors are saying?"
}
```

**What happens:** Cross-portfolio mode runs all 10 seed tickers, and GPT-4.1 specifically looks for CONTRADICTS edges across all tickers — surfacing the most significant signal gaps across the whole watchlist.

---

## 🔀 Query Routing Logic

```
Question received
      │
      ├─ Stage 1: Regex extraction  (e.g. "GME", "NVDA")
      │         + Company name map  (e.g. "Tesla" → TSLA, "Roaring Kitty" → GME)
      │
      └─ Stage 2: LLM fallback resolver  (for ambiguous/freeform questions)
                │
                ├── 1 ticker found   → SINGLE_STOCK       (deep single-company analysis)
                ├── 2+ tickers found → COMPARISON         (parallel side-by-side synthesis)
                ├── 0 tickers + portfolio question → CROSS_PORTFOLIO  (all 10 seeds)
                ├── 0 tickers + financial question → GENERAL
                └── Non-financial question         → OUT_OF_SCOPE  (reject, no retrieval)
```

Follow-up resolution (when `session_id` provided):
- *"the other one"* → ticker from last turn NOT mentioned this turn
- *"both of them"* → all tickers from last turn
- *"the first one"* → first ticker from last turn
- *"them / they / it"* → all or last single ticker discussed

---

## 📦 Output Schema

### `AnalysisOutput` (single stock & comparison)

| Field | Type | Values |
|-------|------|--------|
| `summary` | `str` | One-paragraph verdict |
| `sentiment` | `enum` | `BULLISH` / `BEARISH` / `MIXED` / `NEUTRAL` |
| `risk_score` | `enum` | `LOW` / `MODERATE` / `HIGH` / `VERY_HIGH` |
| `key_contradiction` | `str` | The most important signal contradiction found |
| `risk_summary` | `str` | Detailed risk reasoning paragraph |
| `tickers_discussed` | `list[str]` | Tickers included in this analysis |

### `KnowledgeGraph`

| Field | Description |
|-------|-------------|
| `nodes` | Typed entities: `Company`, `Filing`, `Sentiment`, `Event`, `Price` |
| `edges` | Typed relationships: `DISCLOSES_RISK`, `CONTRADICTS`, `ALIGNS`, `WARNS_OF`, `REPORTS_PRICE` |

### Knowledge Graph Node Colours

| Node Type | Colour | Hex |
|-----------|--------|-----|
| Company | Blue | `#4A90D9` |
| Filing | Orange | `#F5A623` |
| Sentiment | Green | `#7ED321` |
| Event | Purple | `#BD10E0` |
| Price | Red | `#E74C3C` |
| Default | Grey | `#95A5A6` |

---

## 📁 Project Structure

```
.
├── backend/
│   ├── main.py                       # FastAPI app, lifespan hook, CORS, batch prices
│   ├── core/
│   │   └── config.py                 # All env vars, SEED_TICKERS, SEC_CIK_MAP, TTLs
│   ├── api/
│   │   ├── query.py                  # POST /api/query — main RAG pipeline + router
│   │   ├── ingest.py                 # POST /api/ingest, GET /api/ingest/status
│   │   ├── graph.py                  # Graph store, GET /api/graph/view/{session_id}
│   │   ├── classifier.py             # Query type + ticker classifier (LLM-based)
│   │   ├── session.py                # Session CRUD (create, get, add turn)
│   │   └── architecture.py           # GET /api/architecture (static HTML diagram)
│   ├── ingestion/
│   │   ├── ingest_news.py            # Layer 1 — Finnhub news ingestion + cache check
│   │   ├── ingest_social.py          # Layer 2 — Static JSON social posts
│   │   ├── ingest_sec.py             # Layer 3 — SEC EDGAR 10-K/10-Q/8-K + CIK lookup
│   │   ├── ingest_reddit_buzz.py     # Layer 5 — ApeWisdom Reddit buzz
│   │   ├── embedder.py               # OpenAI text-embedding-3-small wrapper
│   │   └── run_ingestion.py          # Master script for manual full re-ingestion
│   ├── retrieval/
│   │   ├── workflow.py               # Parallel fan-out / fan-in orchestrator
│   │   ├── retriever.py              # ChromaDB semantic search per layer
│   │   ├── finnhub_tool.py           # Layer 4 — live price fetcher + mock fallback
│   │   └── chroma_client.py          # ChromaDB client singleton + collection accessors
│   ├── synthesis/
│   │   ├── synthesizer.py            # GPT-4.1 CoT 5-step prompt + Pydantic output
│   │   └── schemas.py                # AnalysisOutput, GeneralAnalysisOutput, RiskScore
│   ├── memory/
│   │   └── session_store.py          # In-memory Q&A history (max 10 turns, 1h TTL)
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   └── App.jsx                   # Main React UI — query input, price dashboard, news
│   ├── index.html
│   └── Dockerfile
├── data/
│   └── layer-2-social.json           # Curated social media post dataset (Layer 2)
├── docker-compose.yml                # 3 services: chromadb, backend, frontend
└── .env                              # OPENAI_API_KEY + FINNHUB_API_KEY (create manually)
```

---

## 🛠️ Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| API Framework | FastAPI + Uvicorn | 0.115.9 / 0.32.1 |
| LLM Synthesis | OpenAI GPT-4.1 | via `openai` 1.57.0 |
| Embeddings | `text-embedding-3-small` (1536-dim) | OpenAI |
| Vector Database | ChromaDB | 1.0.0 |
| Data Validation | Pydantic v2 | 2.10.4 |
| Live Market Data | Finnhub | `finnhub-python` 2.4.27 |
| SEC Filings | SEC EDGAR REST API | Free — no key required |
| Reddit Buzz | ApeWisdom API | Free — no key required |
| Knowledge Graph | pyvis | ≥ 0.3.2 |
| Frontend | React + Vite | Node 20 |
| Containerization | Docker + Docker Compose | — |
| HTTP Client | requests | 2.31.0 |

### External APIs & Credentials Required

| API | Key Required | Cost | Used For |
|-----|-------------|------|---------|
| OpenAI | ✅ Yes | Pay-per-use | Embeddings + GPT-4.1 synthesis |
| Finnhub | ✅ Yes | Free tier available | News articles + live prices |
| SEC EDGAR | ❌ No | Free | 10-K / 10-Q / 8-K filings |
| ApeWisdom | ❌ No | Free | Reddit buzz signals |

---

## 🧑‍⚖️ Evaluation Guide for Judges

### Recommended Testing Sequence

**Step 1 — Verify system health**
```bash
curl http://localhost:8080/api/health
```
Confirm `status: "healthy"` and all ChromaDB collection counts are non-zero.

**Step 2 — View the architecture diagram**

Open `http://localhost:8080/api/architecture` in a browser for a full interactive overview of the data pipeline, API endpoints, and technology stack.

**Step 3 — Run a seed ticker query (fast path)**
```bash
curl -X POST http://localhost:8080/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the investment outlook for NVIDIA based on recent news and SEC filings?"}'
```

**Step 4 — View the knowledge graph**
Copy the `session_id` from the response above, then open:
```
http://localhost:8080/api/graph/view/<session_id>
```

**Step 5 — Test contradiction detection**
```bash
curl -X POST http://localhost:8080/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Compare Tesla and Boeing — where does Reddit sentiment contradict official SEC disclosures?"}'
```

**Step 6 — Test cross-portfolio mode**
```bash
curl -X POST http://localhost:8080/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Which stocks in the portfolio have the strongest Reddit momentum right now?"}'
```

**Step 7 — Test out-of-scope rejection**
```bash
curl -X POST http://localhost:8080/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the capital of France?"}'
```

**Step 8 — Test on-demand non-seed ticker**
```bash
curl -X POST http://localhost:8080/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What does Microsoft latest 8-K say about AI strategy?"}'
```
Note: First query for a non-seed ticker takes ~30–60s due to live SEC EDGAR ingestion.

**Step 9 — Test multi-turn conversation**
```bash
# Turn 1
curl -X POST http://localhost:8080/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Tell me about Palantir.", "session_id": "judge-session-1"}'

# Turn 2 — use the same session_id
curl -X POST http://localhost:8080/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How does it compare to its main competitor?", "session_id": "judge-session-1"}'
```

### What to Evaluate

| Criterion | Where to Look |
|-----------|--------------|
| Retrieval relevance | `raw_context` field — are retrieved chunks on-topic? |
| Contradiction detection | `key_contradiction` field — is the gap real and well-reasoned? |
| Structured output consistency | Schema always matches the Pydantic model — no missing fields |
| Knowledge graph quality | `/api/graph/view/{session_id}` — are edges semantically meaningful? |
| Multi-turn memory | Run follow-up queries with same `session_id` |
| Graceful degradation | Obscure tickers, low Reddit activity, missing filings |
| Out-of-scope handling | Non-financial questions rejected without API calls |
| On-demand ingestion | Non-seed ticker handled automatically end-to-end |

### Known Limitations to Account For in Evaluation

- **Layer 2 social data** is a static curated dataset — not live Twitter/Reddit posts
- **First query for non-seed ticker** is slow (~30–60s) due to SEC EDGAR's enforced rate limit of 10 requests/second
- **Conversation memory resets** on backend container restart (in-memory, intentional design choice)
- **ApeWisdom** may not rank tickers with very low Reddit activity — Layer 5 absent for those; handled gracefully
- **SEC filing extraction** covers Risk Factors, MD&A, and 8-K body sections — not full XBRL financial tables

---

*Financial RAG Engine v2.0.0 — Netcompany Hackathon*