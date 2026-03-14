"""
api/architecture.py
-------------------
Static architecture diagram endpoint — reviewer/judge tooling.

GET /api/architecture
─────────────────────
Returns a self-contained HTML page with an interactive SVG diagram
showing the full system architecture: data layers, retrieval pipeline,
synthesis engine, and API surface.

No runtime dependencies — everything is hardcoded.
Safe to call at any time, even before ChromaDB is ready.

Usage:
  Open in browser: http://localhost:8080/api/architecture
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

_ARCHITECTURE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Financial RAG Engine — Architecture</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet"/>
<style>
  :root {
    --bg:        #0d0f1a;
    --surface:   #13162a;
    --border:    #1e2340;
    --accent:    #00d4ff;
    --accent2:   #7c3aed;
    --green:     #10b981;
    --orange:    #f59e0b;
    --red:       #ef4444;
    --purple:    #8b5cf6;
    --text:      #e2e8f0;
    --muted:     #64748b;
    --layer1:    #0ea5e9;
    --layer2:    #a855f7;
    --layer3:    #f59e0b;
    --layer4:    #ef4444;
    --layer5:    #10b981;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'JetBrains Mono', monospace;
    min-height: 100vh;
    overflow-x: hidden;
  }

  /* ── Background grid ── */
  body::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image:
      linear-gradient(rgba(0,212,255,0.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba(0,212,255,0.03) 1px, transparent 1px);
    background-size: 40px 40px;
    pointer-events: none;
    z-index: 0;
  }

  .container {
    position: relative;
    z-index: 1;
    max-width: 1200px;
    margin: 0 auto;
    padding: 40px 24px 80px;
  }

  /* ── Header ── */
  .header {
    text-align: center;
    margin-bottom: 56px;
    animation: fadeDown 0.6s ease both;
  }

  .header .badge {
    display: inline-block;
    font-size: 10px;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: var(--accent);
    border: 1px solid rgba(0,212,255,0.3);
    padding: 4px 14px;
    border-radius: 20px;
    margin-bottom: 16px;
    background: rgba(0,212,255,0.05);
  }

  .header h1 {
    font-family: 'Syne', sans-serif;
    font-size: clamp(28px, 5vw, 48px);
    font-weight: 800;
    background: linear-gradient(135deg, #fff 0%, var(--accent) 60%, var(--accent2) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1.1;
    margin-bottom: 12px;
  }

  .header p {
    color: var(--muted);
    font-size: 13px;
    letter-spacing: 0.5px;
  }

  /* ── Section label ── */
  .section-label {
    font-size: 10px;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .section-label::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border);
  }

  /* ── Main pipeline ── */
  .pipeline {
    display: flex;
    flex-direction: column;
    gap: 0;
    margin-bottom: 48px;
  }

  /* ── Node cards ── */
  .node {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px 24px;
    position: relative;
    animation: fadeUp 0.5s ease both;
    transition: border-color 0.2s, box-shadow 0.2s;
  }

  .node:hover {
    border-color: rgba(0,212,255,0.3);
    box-shadow: 0 0 24px rgba(0,212,255,0.06);
  }

  .node-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 8px;
  }

  .node-icon {
    width: 36px;
    height: 36px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    flex-shrink: 0;
  }

  .node-title {
    font-family: 'Syne', sans-serif;
    font-size: 15px;
    font-weight: 700;
    color: #fff;
  }

  .node-subtitle {
    font-size: 10px;
    color: var(--muted);
    letter-spacing: 1px;
    text-transform: uppercase;
  }

  .node-desc {
    font-size: 12px;
    color: var(--muted);
    line-height: 1.6;
    margin-left: 48px;
  }

  /* ── Arrow connectors ── */
  .arrow {
    display: flex;
    justify-content: center;
    padding: 6px 0;
    color: var(--muted);
    font-size: 18px;
    position: relative;
  }

  .arrow::before {
    content: '';
    position: absolute;
    left: 50%;
    top: 0;
    bottom: 0;
    width: 1px;
    background: linear-gradient(to bottom, transparent, var(--border), transparent);
  }

  /* ── Query router node ── */
  .node-router .node-icon { background: rgba(0,212,255,0.15); color: var(--accent); }

  /* ── 5 layers grid ── */
  .layers-wrapper {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 24px;
    animation: fadeUp 0.5s 0.3s ease both;
    margin-bottom: 0;
    transition: border-color 0.2s, box-shadow 0.2s;
  }
  .layers-wrapper:hover {
    border-color: rgba(0,212,255,0.2);
  }

  .layers-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 20px;
  }

  .layers-title {
    font-family: 'Syne', sans-serif;
    font-size: 15px;
    font-weight: 700;
    color: #fff;
  }

  .layers-subtitle {
    font-size: 10px;
    color: var(--muted);
    letter-spacing: 1px;
    text-transform: uppercase;
  }

  .layers-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px;
  }

  .layer-card {
    border-radius: 10px;
    padding: 14px 16px;
    border: 1px solid;
    transition: transform 0.2s, box-shadow 0.2s;
    cursor: default;
  }

  .layer-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0,0,0,0.3);
  }

  .layer-card.l1 { background: rgba(14,165,233,0.08); border-color: rgba(14,165,233,0.3); }
  .layer-card.l2 { background: rgba(168,85,247,0.08); border-color: rgba(168,85,247,0.3); }
  .layer-card.l3 { background: rgba(245,158,11,0.08); border-color: rgba(245,158,11,0.3); }
  .layer-card.l4 { background: rgba(239,68,68,0.08);  border-color: rgba(239,68,68,0.3); }
  .layer-card.l5 { background: rgba(16,185,129,0.08); border-color: rgba(16,185,129,0.3); }

  .layer-num {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
    margin-bottom: 6px;
    text-transform: uppercase;
  }
  .l1 .layer-num { color: var(--layer1); }
  .l2 .layer-num { color: var(--layer2); }
  .l3 .layer-num { color: var(--layer3); }
  .l4 .layer-num { color: var(--layer4); }
  .l5 .layer-num { color: var(--layer5); }

  .layer-name {
    font-family: 'Syne', sans-serif;
    font-size: 13px;
    font-weight: 700;
    color: #fff;
    margin-bottom: 4px;
  }

  .layer-source {
    font-size: 10px;
    color: var(--muted);
    margin-bottom: 8px;
  }

  .layer-tag {
    display: inline-block;
    font-size: 9px;
    letter-spacing: 1px;
    text-transform: uppercase;
    padding: 2px 8px;
    border-radius: 4px;
    font-weight: 600;
  }

  .tag-live   { background: rgba(239,68,68,0.2);  color: #ef4444; }
  .tag-daily  { background: rgba(245,158,11,0.2); color: #f59e0b; }
  .tag-30d    { background: rgba(14,165,233,0.2); color: #0ea5e9; }
  .tag-static { background: rgba(100,116,139,0.2);color: var(--muted); }

  /* ── Synthesis node ── */
  .node-synthesis .node-icon {
    background: linear-gradient(135deg, rgba(124,58,237,0.3), rgba(0,212,255,0.2));
    color: var(--accent);
  }

  /* ── Output split ── */
  .outputs-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }

  @media (max-width: 600px) {
    .outputs-grid { grid-template-columns: 1fr; }
    .layers-grid  { grid-template-columns: 1fr 1fr; }
  }

  .output-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px 24px;
    animation: fadeUp 0.5s 0.5s ease both;
    transition: border-color 0.2s;
  }

  .output-card:hover { border-color: rgba(124,58,237,0.4); }

  .output-card .tag {
    display: inline-block;
    font-size: 9px;
    letter-spacing: 2px;
    text-transform: uppercase;
    padding: 2px 8px;
    border-radius: 4px;
    margin-bottom: 10px;
    font-weight: 700;
  }

  .output-card.narrative .tag { background: rgba(16,185,129,0.2); color: var(--green); }
  .output-card.graph     .tag { background: rgba(0,212,255,0.2);  color: var(--accent); }

  .output-card h3 {
    font-family: 'Syne', sans-serif;
    font-size: 14px;
    font-weight: 700;
    color: #fff;
    margin-bottom: 8px;
  }

  .output-card ul {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 5px;
  }

  .output-card ul li {
    font-size: 11px;
    color: var(--muted);
    padding-left: 14px;
    position: relative;
    line-height: 1.5;
  }

  .output-card ul li::before {
    content: '→';
    position: absolute;
    left: 0;
    color: var(--accent2);
  }

  /* ── API endpoint reference ── */
  .endpoints {
    margin-top: 48px;
    animation: fadeUp 0.5s 0.7s ease both;
  }

  .method {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    flex-shrink: 0;
  }

  .method.get  { background: rgba(16,185,129,0.2); color: var(--green); }
  .method.post { background: rgba(245,158,11,0.2); color: var(--orange); }
  .method.del  { background: rgba(239,68,68,0.2);  color: var(--red); }

  .ep-path {
    font-family: 'JetBrains Mono', monospace;
    color: var(--accent);
    font-size: 12px;
    flex-shrink: 0;
  }

  .ep-tag {
    display: inline-block;
    font-size: 9px;
    padding: 1px 6px;
    border-radius: 3px;
    background: rgba(124,58,237,0.2);
    color: var(--purple);
    letter-spacing: 1px;
    text-transform: uppercase;
    font-weight: 600;
    flex-shrink: 0;
  }

  .ep-tag.new {
    background: rgba(0,212,255,0.2);
    color: var(--accent);
  }

  /* ── Expandable endpoint cards ── */
  .ep-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    margin-bottom: 8px;
    overflow: hidden;
    cursor: pointer;
    transition: border-color 0.2s;
  }

  .ep-card:hover { border-color: rgba(0,212,255,0.25); }
  .ep-card.open  { border-color: rgba(0,212,255,0.35); }

  .ep-card-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px 18px;
    user-select: none;
  }

  .ep-summary {
    font-size: 12px;
    color: var(--muted);
    flex: 1;
  }

  .chevron {
    font-size: 11px;
    color: var(--muted);
    transition: transform 0.2s;
    flex-shrink: 0;
  }

  .ep-card.open .chevron { transform: rotate(90deg); }

  .ep-card-body {
    display: none;
    padding: 0 18px 18px;
    border-top: 1px solid var(--border);
    padding-top: 16px;
  }

  .ep-card.open .ep-card-body { display: block; }

  .ep-two-col {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
  }

  @media (max-width: 700px) { .ep-two-col { grid-template-columns: 1fr; } }

  .ep-block-title {
    font-size: 10px;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--accent);
    margin-bottom: 10px;
    font-weight: 600;
  }

  .ep-code {
    background: rgba(0,0,0,0.3);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 12px 14px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: #c9d1d9;
    white-space: pre;
    overflow-x: auto;
    line-height: 1.7;
    margin-bottom: 12px;
  }

  .ep-code .c { color: #6e7681; }

  .ep-note {
    font-size: 11px;
    color: var(--muted);
    line-height: 1.7;
    background: rgba(0,212,255,0.04);
    border: 1px solid rgba(0,212,255,0.1);
    border-radius: 6px;
    padding: 10px 14px;
  }

  .ep-note code {
    color: var(--accent);
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
  }

  .ep-note strong { color: #fff; }

  /* ── Tech stack ── */
  .tech-stack {
    margin-top: 48px;
    animation: fadeUp 0.5s 0.9s ease both;
  }

  .tech-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 12px;
  }

  .tech-pill {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px 16px;
    text-align: center;
    transition: border-color 0.2s, transform 0.2s;
  }

  .tech-pill:hover {
    border-color: rgba(0,212,255,0.25);
    transform: translateY(-1px);
  }

  .tech-pill .name {
    font-family: 'Syne', sans-serif;
    font-size: 13px;
    font-weight: 700;
    color: #fff;
    display: block;
    margin-bottom: 2px;
  }

  .tech-pill .role {
    font-size: 10px;
    color: var(--muted);
    letter-spacing: 0.5px;
  }

  /* ── Animations ── */
  @keyframes fadeUp {
    from { opacity: 0; transform: translateY(16px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  @keyframes fadeDown {
    from { opacity: 0; transform: translateY(-10px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  /* stagger pipeline nodes */
  .pipeline > *:nth-child(1)  { animation-delay: 0.05s; }
  .pipeline > *:nth-child(2)  { animation-delay: 0.10s; }
  .pipeline > *:nth-child(3)  { animation-delay: 0.15s; }
  .pipeline > *:nth-child(4)  { animation-delay: 0.20s; }
  .pipeline > *:nth-child(5)  { animation-delay: 0.25s; }
  .pipeline > *:nth-child(6)  { animation-delay: 0.30s; }
  .pipeline > *:nth-child(7)  { animation-delay: 0.35s; }
  .pipeline > *:nth-child(8)  { animation-delay: 0.40s; }
  .pipeline > *:nth-child(9)  { animation-delay: 0.45s; }
  .pipeline > *:nth-child(10) { animation-delay: 0.50s; }

  /* ── Pulse dot ── */
  .pulse {
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--green);
    margin-right: 6px;
    animation: pulse 2s infinite;
    vertical-align: middle;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(16,185,129,0.4); }
    50%       { opacity: 0.7; box-shadow: 0 0 0 6px rgba(16,185,129,0); }
  }

  /* ── Footer ── */
  .footer {
    margin-top: 64px;
    text-align: center;
    font-size: 11px;
    color: var(--muted);
    padding-top: 24px;
    border-top: 1px solid var(--border);
  }
</style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="header">
    <div class="badge">System Architecture</div>
    <h1>Financial RAG Engine</h1>
    <p>Multi-layer retrieval · GPT-4.1 synthesis · Real-time market data</p>
  </div>

  <!-- Pipeline -->
  <div class="section-label">Data Flow Pipeline</div>
  <div class="pipeline">

    <!-- Step 1: User Query -->
    <div class="node node-router">
      <div class="node-header">
        <div class="node-icon">💬</div>
        <div>
          <div class="node-title">User Query</div>
          <div class="node-subtitle">Natural language input · POST /api/query</div>
        </div>
      </div>
      <div class="node-desc">Any question about stocks, filings, sentiment, or portfolios. Session ID enables multi-turn memory.</div>
    </div>

    <div class="arrow">↓</div>

    <!-- Step 2: Query Router -->
    <div class="node node-router">
      <div class="node-header">
        <div class="node-icon">🔀</div>
        <div>
          <div class="node-title">Query Router</div>
          <div class="node-subtitle">GPT-4.1 · 4 query types</div>
        </div>
      </div>
      <div class="node-desc">
        Classifies intent:
        <strong style="color:#fff">single_stock</strong> → one company deep-dive &nbsp;·&nbsp;
        <strong style="color:#fff">comparison</strong> → 2+ named tickers &nbsp;·&nbsp;
        <strong style="color:#fff">cross_portfolio</strong> → all 10 seed tickers &nbsp;·&nbsp;
        <strong style="color:#fff">general</strong> → broad market questions
      </div>
    </div>

    <div class="arrow">↓</div>

    <!-- Step 3: Parallel Retrieval (5 layers) -->
    <div class="layers-wrapper">
      <div class="layers-header">
        <div class="node-icon" style="background:rgba(0,212,255,0.1);color:var(--accent);width:36px;height:36px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:16px;">⚡</div>
        <div>
          <div class="layers-title">Parallel Retrieval — 5 Data Layers</div>
          <div class="layers-subtitle">All layers fetched concurrently · ChromaDB vector search + live APIs</div>
        </div>
      </div>
      <div class="layers-grid">

        <div class="layer-card l1">
          <div class="layer-num">Layer 1</div>
          <div class="layer-name">News Articles</div>
          <div class="layer-source">Finnhub API → ChromaDB</div>
          <span class="layer-tag tag-daily">TTL: 1 day</span>
        </div>

        <div class="layer-card l2">
          <div class="layer-num">Layer 2</div>
          <div class="layer-name">Social Posts</div>
          <div class="layer-source">Static JSON → ChromaDB</div>
          <span class="layer-tag tag-static">Static</span>
        </div>

        <div class="layer-card l3">
          <div class="layer-num">Layer 3</div>
          <div class="layer-name">SEC Filings</div>
          <div class="layer-source">EDGAR API → ChromaDB</div>
          <span class="layer-tag tag-30d">TTL: 30 days</span>
        </div>

        <div class="layer-card l4">
          <div class="layer-num">Layer 4</div>
          <div class="layer-name">Live Price</div>
          <div class="layer-source">Finnhub (real-time)</div>
          <span class="layer-tag tag-live">Real-time</span>
        </div>

        <div class="layer-card l5">
          <div class="layer-num">Layer 5</div>
          <div class="layer-name">Reddit Buzz</div>
          <div class="layer-source">ApeWisdom → ChromaDB</div>
          <span class="layer-tag tag-daily">TTL: 1 day</span>
        </div>

      </div>
    </div>

    <div class="arrow">↓</div>

    <!-- Step 4: Embedding -->
    <div class="node">
      <div class="node-header">
        <div class="node-icon" style="background:rgba(139,92,246,0.15);color:var(--purple);">🔢</div>
        <div>
          <div class="node-title">Semantic Embedding & Retrieval</div>
          <div class="node-subtitle">text-embedding-3-small · cosine similarity</div>
        </div>
      </div>
      <div class="node-desc">
        Query is embedded (1536-dim vector). ChromaDB runs cosine similarity search per layer.
        Top-K per layer: News ×3 · Social ×5 · SEC ×4 · Reddit ×1 · Price (direct).
      </div>
    </div>

    <div class="arrow">↓</div>

    <!-- Step 5: Synthesis -->
    <div class="node node-synthesis">
      <div class="node-header">
        <div class="node-icon">🧠</div>
        <div>
          <div class="node-title">Synthesis Engine</div>
          <div class="node-subtitle">GPT-4.1 · Chain-of-Thought · Structured output</div>
        </div>
      </div>
      <div class="node-desc">
        All retrieved context + conversation history fed to GPT-4.1.
        Pydantic-enforced structured output guarantees consistent JSON response schema.
        Two paths: <strong style="color:#fff">AnalysisOutput</strong> (single-stock) · <strong style="color:#fff">GeneralAnalysisOutput</strong> (cross-portfolio / comparison).
      </div>
    </div>

    <div class="arrow">↓</div>

    <!-- Step 6: Outputs -->
    <div class="outputs-grid">
      <div class="output-card narrative">
        <span class="tag">Analysis Narrative</span>
        <h3>Structured CoT Breakdown</h3>
        <ul>
          <li>Summary verdict + top ticker</li>
          <li>Sentiment signal (BULLISH / BEARISH / MIXED)</li>
          <li>Risk level (LOW → VERY_HIGH)</li>
          <li>Key contradiction detected</li>
          <li>Risk summary paragraph</li>
        </ul>
      </div>
      <div class="output-card graph">
        <span class="tag">Knowledge Graph</span>
        <h3>Interactive Entity Graph</h3>
        <ul>
          <li>Nodes: Company, Filing, Sentiment, Event, Price</li>
          <li>Edges: DISCLOSES_RISK, CONTRADICTS, ALIGNS, WARNS_OF…</li>
          <li>Stored per session_id in memory</li>
          <li>Viewable at <code style="color:var(--accent);font-size:10px">/api/graph/view/{session_id}</code></li>
        </ul>
      </div>
    </div>

  </div><!-- /pipeline -->

  <!-- API Endpoints Reference -->
  <div class="endpoints">
    <div class="section-label">API Endpoint Reference</div>
    <p style="font-size:11px;color:var(--muted);margin-bottom:20px;">Click any endpoint to expand request &amp; response details.</p>

    <!-- ── POST /api/query ── -->
    <div class="ep-card" onclick="toggle(this)">
      <div class="ep-card-header">
        <span class="method post">POST</span>
        <span class="ep-path">/api/query</span>
        <span class="ep-summary">Full RAG pipeline — the main endpoint</span>
        <span class="ep-tag" style="margin-left:auto">Query</span>
        <span class="chevron">▸</span>
      </div>
      <div class="ep-card-body">
        <div class="ep-two-col">
          <div>
            <div class="ep-block-title">Request Body</div>
            <pre class="ep-code">{
  "question":   "Compare GME and NVIDIA",  <span class="c">// required, 3–500 chars</span>
  "tickers":    ["GME", "NVDA"],            <span class="c">// optional — auto-resolved if omitted</span>
  "session_id": "uuid-string"              <span class="c">// optional — omit for a new session</span>
}</pre>
            <div class="ep-note">
              <strong>Routing logic:</strong> The question is classified into one of four paths:<br/>
              <code>single_stock</code> — 1 ticker detected → deep single-company analysis<br/>
              <code>comparison</code> — 2+ named tickers → side-by-side synthesis<br/>
              <code>cross_portfolio</code> — no ticker, portfolio question → all 10 seed tickers<br/>
              <code>general</code> — no ticker, broad market question<br/>
              <code>out_of_scope</code> — non-financial → polite rejection, no retrieval<br/><br/>
              <strong>Session memory:</strong> Pass the <code>session_id</code> returned from a previous call to enable multi-turn conversation. Follow-up questions like <em>"Is that risky?"</em> automatically inherit the tickers from the prior turn.
            </div>
          </div>
          <div>
            <div class="ep-block-title">Response</div>
            <pre class="ep-code">{
  "query_type":      "single_stock",
  "tickers":         ["GME"],
  "ticker":          "GME",           <span class="c">// primary ticker</span>
  "session_id":      "uuid-string",   <span class="c">// persist for follow-ups</span>
  "turn_number":     1,
  "narrative": {
    "summary":       "...",           <span class="c">// one-sentence verdict</span>
    "sentiment":     "BEARISH",       <span class="c">// BULLISH | BEARISH | MIXED | NEUTRAL</span>
    "risk_level":    "HIGH",          <span class="c">// LOW | MEDIUM | HIGH | VERY_HIGH</span>
    "risk_percentage": 72,            <span class="c">// 0–100</span>
    "contradiction": "...",           <span class="c">// key signal conflict detected</span>
    "risk_summary":  "..."
  },
  "knowledge_graph": {
    "nodes": [...],                   <span class="c">// entity nodes</span>
    "edges": [...]                    <span class="c">// relationships between nodes</span>
  },
  "price": { ... }                    <span class="c">// live price data (single_stock only)</span>
}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- ── GET /api/health ── -->
    <div class="ep-card" onclick="toggle(this)">
      <div class="ep-card-header">
        <span class="method get">GET</span>
        <span class="ep-path">/api/health</span>
        <span class="ep-summary">Full system status check</span>
        <span class="ep-tag" style="margin-left:auto">Health</span>
        <span class="chevron">▸</span>
      </div>
      <div class="ep-card-body">
        <div class="ep-two-col">
          <div>
            <div class="ep-block-title">Request</div>
            <div class="ep-note">No parameters. Always safe to call — does not trigger any retrieval or model calls.</div>
          </div>
          <div>
            <div class="ep-block-title">Response</div>
            <pre class="ep-code">{
  "status":   "ok",
  "chromadb": "connected",  <span class="c">// or "error: ..."</span>
  "finnhub":  "configured", <span class="c">// or "missing key"</span>
  "openai":   "configured",
  "collections": {
    "layer_news":        142,
    "layer_social":       50,
    "layer_sec":         380,
    "layer_reddit_buzz":  10
  }
}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- ── GET /api/prices ── -->
    <div class="ep-card" onclick="toggle(this)">
      <div class="ep-card-header">
        <span class="method get">GET</span>
        <span class="ep-path">/api/prices</span>
        <span class="ep-summary">Batch live prices for one or more tickers</span>
        <span class="ep-tag" style="margin-left:auto">Prices</span>
        <span class="chevron">▸</span>
      </div>
      <div class="ep-card-body">
        <div class="ep-two-col">
          <div>
            <div class="ep-block-title">Query Params</div>
            <pre class="ep-code">GET /api/prices                   <span class="c">// all 10 seed tickers</span>
GET /api/prices?tickers=GME,NVDA  <span class="c">// specific tickers</span></pre>
            <div class="ep-note">All tickers are fetched in parallel (~300ms for all 10). Falls back to mock data for seed tickers if Finnhub is unavailable. Returns an error dict for unknown tickers where Finnhub fails.</div>
          </div>
          <div>
            <div class="ep-block-title">Response</div>
            <pre class="ep-code">{
  "GME": {
    "current_price":  26.80,
    "previous_close": 25.10,
    "change":          1.70,
    "change_pct":      6.77,
    "day_high":       27.50,
    "day_low":        25.00,
    "open":           25.20,
    "market_cap":    "8.5B",
    "is_live":        true   <span class="c">// false = mock fallback</span>
  },
  "NVDA": { ... }
}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- ── POST /api/ingest ── -->
    <div class="ep-card" onclick="toggle(this)">
      <div class="ep-card-header">
        <span class="method post">POST</span>
        <span class="ep-path">/api/ingest</span>
        <span class="ep-summary">Force re-ingest all data layers for a ticker</span>
        <span class="ep-tag" style="margin-left:auto">Ingest</span>
        <span class="chevron">▸</span>
      </div>
      <div class="ep-card-body">
        <div class="ep-two-col">
          <div>
            <div class="ep-block-title">Request Body</div>
            <pre class="ep-code">{
  "ticker": "TSLA"  <span class="c">// required</span>
}</pre>
            <div class="ep-note">Bypasses TTL checks and forces a full re-ingest of all data layers (news, SEC filings, Reddit buzz) for the given ticker. Useful after a major company event or when data feels stale.</div>
          </div>
          <div>
            <div class="ep-block-title">Response</div>
            <pre class="ep-code">{
  "status": "ok",
  "ticker": "TSLA",
  "ingested": {
    "news":        12,
    "sec_chunks":  48,
    "reddit_buzz":  1
  }
}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- ── GET /api/ingest/status ── -->
    <div class="ep-card" onclick="toggle(this)">
      <div class="ep-card-header">
        <span class="method get">GET</span>
        <span class="ep-path">/api/ingest/status</span>
        <span class="ep-summary">ChromaDB document counts per collection</span>
        <span class="ep-tag" style="margin-left:auto">Ingest</span>
        <span class="chevron">▸</span>
      </div>
      <div class="ep-card-body">
        <div class="ep-two-col">
          <div>
            <div class="ep-block-title">Request</div>
            <div class="ep-note">No parameters. Shows how many documents are currently stored in each ChromaDB collection — useful to verify a fresh startup has ingested correctly.</div>
          </div>
          <div>
            <div class="ep-block-title">Response</div>
            <pre class="ep-code">{
  "layer_news":        142,
  "layer_social":       50,
  "layer_sec":         380,
  "layer_reddit_buzz":  10,
  "total":             582
}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- ── GET /api/graph/view/{session_id} ── -->
    <div class="ep-card" onclick="toggle(this)">
      <div class="ep-card-header">
        <span class="method get">GET</span>
        <span class="ep-path">/api/graph/view/{session_id}</span>
        <span class="ep-summary">Interactive knowledge graph for a query session</span>
        <span class="ep-tag" style="margin-left:auto">Graph</span>
        <span class="chevron">▸</span>
      </div>
      <div class="ep-card-body">
        <div class="ep-two-col">
          <div>
            <div class="ep-block-title">Path Param</div>
            <pre class="ep-code">session_id  <span class="c">// from the /api/query response</span></pre>
            <div class="ep-note">
              <strong>How to use:</strong><br/>
              1. Call <code>POST /api/query</code> → note the <code>session_id</code><br/>
              2. Open in browser: <code>http://localhost:8080/api/graph/view/&lt;session_id&gt;</code><br/>
              3. Interactive graph renders immediately<br/>
              4. Refresh after a new query on the same session to see the updated graph<br/><br/>
              Returns <strong>rendered HTML</strong> (not JSON) — open directly in a browser tab.
            </div>
          </div>
          <div>
            <div class="ep-block-title">Rendered page includes</div>
            <div class="ep-note" style="margin-top:0">
              • Draggable, zoomable entity graph (pyvis / vis.js)<br/>
              • Color-coded nodes by type: Company (blue) · Filing (orange) · Sentiment (green) · Event (purple) · Price (red)<br/>
              • Labeled edges showing relationships (CONTRADICTS, ALIGNS, DISCLOSES_RISK…)<br/>
              • Header with risk percentage, risk label, and the key contradiction sentence<br/>
              • One-sentence analysis verdict
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ── POST /api/graph/visualize ── -->
    <div class="ep-card" onclick="toggle(this)">
      <div class="ep-card-header">
        <span class="method post">POST</span>
        <span class="ep-path">/api/graph/visualize</span>
        <span class="ep-summary">Render any knowledge_graph JSON as interactive HTML</span>
        <span class="ep-tag" style="margin-left:auto">Graph</span>
        <span class="chevron">▸</span>
      </div>
      <div class="ep-card-body">
        <div class="ep-two-col">
          <div>
            <div class="ep-block-title">Request Body</div>
            <pre class="ep-code">{
  "nodes": [
    { "id": "GME", "label": "GameStop",
      "type": "Company", "detail": "..." }
  ],
  "edges": [
    { "id": "e1", "source": "GME",
      "target": "10K_Risk",
      "label": "DISCLOSES_RISK" }
  ],
  "title":      "My Graph",  <span class="c">// optional</span>
  "session_id": "uuid"       <span class="c">// optional — stores for GET access</span>
}</pre>
          </div>
          <div>
            <div class="ep-block-title">Response</div>
            <div class="ep-note">Returns rendered <strong>HTML</strong> directly. Paste any <code>knowledge_graph</code> block from a <code>/api/query</code> response to visualise it manually. If <code>session_id</code> is provided, the graph is also stored and accessible via <code>GET /api/graph/view/{session_id}</code>.</div>
          </div>
        </div>
      </div>
    </div>

    <!-- ── GET /api/graph/sessions ── -->
    <div class="ep-card" onclick="toggle(this)">
      <div class="ep-card-header">
        <span class="method get">GET</span>
        <span class="ep-path">/api/graph/sessions</span>
        <span class="ep-summary">List all session IDs with a stored graph</span>
        <span class="ep-tag" style="margin-left:auto">Graph</span>
        <span class="chevron">▸</span>
      </div>
      <div class="ep-card-body">
        <div class="ep-two-col">
          <div>
            <div class="ep-block-title">Request</div>
            <div class="ep-note">No parameters. Shows which sessions currently have a graph in memory (in-memory store — resets on server restart).</div>
          </div>
          <div>
            <div class="ep-block-title">Response</div>
            <pre class="ep-code">{
  "session_ids": [
    "3f2a1b...",
    "9c4d7e..."
  ],
  "count": 2
}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- ── GET /api/history/{session_id} ── -->
    <div class="ep-card" onclick="toggle(this)">
      <div class="ep-card-header">
        <span class="method get">GET</span>
        <span class="ep-path">/api/history/{session_id}</span>
        <span class="ep-summary">Retrieve full conversation history for a session</span>
        <span class="ep-tag" style="margin-left:auto">Session</span>
        <span class="chevron">▸</span>
      </div>
      <div class="ep-card-body">
        <div class="ep-two-col">
          <div>
            <div class="ep-block-title">Path Param</div>
            <pre class="ep-code">session_id  <span class="c">// from a prior /api/query response</span></pre>
          </div>
          <div>
            <div class="ep-block-title">Response</div>
            <pre class="ep-code">{
  "session_id":  "uuid-string",
  "turn_count":  3,
  "turns": [
    { "role": "user",      "content": "...",
      "tickers": ["GME"] },
    { "role": "assistant", "content": "...",
      "tickers": ["GME"] },
    ...
  ]
}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- ── DELETE /api/session/{session_id} ── -->
    <div class="ep-card" onclick="toggle(this)">
      <div class="ep-card-header">
        <span class="method del">DELETE</span>
        <span class="ep-path">/api/session/{session_id}</span>
        <span class="ep-summary">Clear conversation history for a session</span>
        <span class="ep-tag" style="margin-left:auto">Session</span>
        <span class="chevron">▸</span>
      </div>
      <div class="ep-card-body">
        <div class="ep-two-col">
          <div>
            <div class="ep-block-title">Path Param</div>
            <pre class="ep-code">session_id  <span class="c">// session to wipe</span></pre>
            <div class="ep-note">Removes all turns from the session. The session_id remains valid — the next query on it starts a fresh conversation from turn 1.</div>
          </div>
          <div>
            <div class="ep-block-title">Response</div>
            <pre class="ep-code">{
  "status":     "cleared",
  "session_id": "uuid-string"
}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- ── GET /api/architecture ── -->
    <div class="ep-card" onclick="toggle(this)">
      <div class="ep-card-header">
        <span class="method get">GET</span>
        <span class="ep-path">/api/architecture</span>
        <span class="ep-summary">This page — full system architecture &amp; API reference</span>
        <span class="ep-tag new" style="margin-left:auto">Docs</span>
        <span class="chevron">▸</span>
      </div>
      <div class="ep-card-body">
        <div class="ep-note">Returns this static HTML page. No runtime dependencies — safe to open even if ChromaDB or OpenAI are not reachable. Always reflects the current codebase structure.</div>
      </div>
    </div>

  </div><!-- /endpoints -->

  <!-- Tech Stack -->
  <div class="tech-stack">
    <div class="section-label">Technology Stack</div>
    <div class="tech-grid">
      <div class="tech-pill">
        <span class="name">FastAPI</span>
        <span class="role">API framework</span>
      </div>
      <div class="tech-pill">
        <span class="name">GPT-4.1</span>
        <span class="role">Synthesis & routing</span>
      </div>
      <div class="tech-pill">
        <span class="name">ChromaDB</span>
        <span class="role">Vector database</span>
      </div>
      <div class="tech-pill">
        <span class="name">text-embed-3</span>
        <span class="role">1536-dim embeddings</span>
      </div>
      <div class="tech-pill">
        <span class="name">Finnhub</span>
        <span class="role">News + live prices</span>
      </div>
      <div class="tech-pill">
        <span class="name">SEC EDGAR</span>
        <span class="role">10-K / 10-Q / 8-K</span>
      </div>
      <div class="tech-pill">
        <span class="name">ApeWisdom</span>
        <span class="role">Reddit buzz signals</span>
      </div>
      <div class="tech-pill">
        <span class="name">pyvis</span>
        <span class="role">Graph visualization</span>
      </div>
      <div class="tech-pill">
        <span class="name">Pydantic</span>
        <span class="role">Structured outputs</span>
      </div>
      <div class="tech-pill">
        <span class="name">Docker</span>
        <span class="role">Container orchestration</span>
      </div>
    </div>
  </div>

  <div class="footer">
    <span class="pulse"></span>
    Financial RAG Engine v2.0 &nbsp;·&nbsp; <code style="color:var(--accent)">GET /api/architecture</code> &nbsp;·&nbsp; Static · No runtime dependencies
  </div>

</div>

<script>
  function toggle(card) {
    card.classList.toggle('open');
  }
</script>
</body>
</html>"""


@router.get(
    "/architecture",
    response_class=HTMLResponse,
    summary="System architecture diagram",
    tags=["Docs"],
)
async def architecture():
    """
    Static architecture diagram of the Financial RAG Engine.

    Shows:
      - Full data flow pipeline (query → routing → retrieval → synthesis → output)
      - All 5 data layers with sources and TTLs
      - Embedding & retrieval strategy
      - Synthesis engine (GPT-4.1 + Pydantic structured output)
      - Complete API endpoint reference
      - Technology stack

    Open in browser: http://localhost:8080/api/architecture
    No session_id needed — fully static, always available.
    """
    return HTMLResponse(content=_ARCHITECTURE_HTML)