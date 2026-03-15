import { useState, useEffect, useRef, useCallback, useMemo } from "react";

// ── Constants ─────────────────────────────────────────────────────────────────
const API_BASE = "/api";

const SEED_TICKERS = ["AAPL", "BA", "GME", "JPM", "NEE", "NVDA", "PFE", "PLTR", "TSLA", "XOM"];

const COMPANY_NAMES = {
  AAPL: "Apple Inc.", BA: "Boeing Co.", GME: "GameStop Corp.",
  JPM: "JPMorgan Chase", NEE: "NextEra Energy", NVDA: "NVIDIA Corp.",
  PFE: "Pfizer Inc.", PLTR: "Palantir Technologies", TSLA: "Tesla Inc.", XOM: "ExxonMobil",
};

const RISK_COLOR = (score) =>
  score < 35 ? "#00ff9d" : score < 65 ? "#f6ad55" : "#ff4d6d";

const SENTIMENT_COLORS = {
  bullish: "#00ff9d", bearish: "#ff4d6d", neutral: "#a0aec0",
  BULLISH: "#00ff9d", BEARISH: "#ff4d6d", NEUTRAL: "#a0aec0", MIXED: "#f6ad55",
  LOW: "#00ff9d", MEDIUM: "#f6ad55", HIGH: "#ff4d6d", VERY_HIGH: "#ff2050",
};

// ── Instant mock prices — shown immediately before live data arrives ───────────
// Mirrors finnhub_tool.py MOCK_PRICES so the carousel is never empty.
const MOCK_PRICES = {
  AAPL: { current_price: 227.50, change: 1.70,   change_pct: 0.75,  day_high: 229.10, day_low: 225.20, open: 226.00, previous_close: 225.80, is_live: false },
  NVDA: { current_price: 875.40, change: 13.30,  change_pct: 1.54,  day_high: 881.00, day_low: 860.50, open: 865.00, previous_close: 862.10, is_live: false },
  TSLA: { current_price: 248.20, change: -4.20,  change_pct: -1.66, day_high: 253.80, day_low: 246.10, open: 252.00, previous_close: 252.40, is_live: false },
  GME:  { current_price: 26.80,  change: 1.70,   change_pct: 6.77,  day_high: 27.50,  day_low: 24.90,  open: 25.20,  previous_close: 25.10,  is_live: false },
  PLTR: { current_price: 82.50,  change: 2.30,   change_pct: 2.87,  day_high: 83.40,  day_low: 79.80,  open: 80.50,  previous_close: 80.20,  is_live: false },
  JPM:  { current_price: 238.60, change: 1.70,   change_pct: 0.72,  day_high: 239.80, day_low: 236.20, open: 237.10, previous_close: 236.90, is_live: false },
  BA:   { current_price: 172.30, change: 1.80,   change_pct: 1.06,  day_high: 173.50, day_low: 169.80, open: 170.80, previous_close: 170.50, is_live: false },
  PFE:  { current_price: 24.10,  change: 0.30,   change_pct: 1.26,  day_high: 24.40,  day_low: 23.70,  open: 23.90,  previous_close: 23.80,  is_live: false },
  NEE:  { current_price: 71.20,  change: 0.80,   change_pct: 1.14,  day_high: 71.80,  day_low: 70.10,  open: 70.60,  previous_close: 70.40,  is_live: false },
  XOM:  { current_price: 108.50, change: 1.30,   change_pct: 1.21,  day_high: 109.10, day_low: 107.00, open: 107.50, previous_close: 107.20, is_live: false },
};

// ── Preloaded seed news — shown before any query ───────────────────────────────
const SEED_NEWS = [
  { ticker: "NVDA", headline: "NVIDIA posts record data-center revenue as AI chip demand accelerates", time: "2h ago", sentiment: "bullish" },
  { ticker: "AAPL", headline: "Apple expands services revenue to new high with Vision Pro ecosystem growth", time: "3h ago", sentiment: "bullish" },
  { ticker: "TSLA", headline: "Tesla Q1 deliveries miss analyst estimates amid production retooling", time: "4h ago", sentiment: "bearish" },
  { ticker: "GME",  headline: "GameStop exploring crypto and collectibles pivot as core game sales slide", time: "5h ago", sentiment: "neutral" },
  { ticker: "JPM",  headline: "JPMorgan beats earnings expectations on strong investment banking fees", time: "6h ago", sentiment: "bullish" },
  { ticker: "BA",   headline: "Boeing faces fresh FAA scrutiny over 737 MAX quality-control gaps", time: "7h ago", sentiment: "bearish" },
  { ticker: "PLTR", headline: "Palantir wins $480M US Army AI contract, shares jump 8% in after-hours", time: "8h ago", sentiment: "bullish" },
  { ticker: "PFE",  headline: "Pfizer cuts full-year guidance as COVID vaccine demand continues to fade", time: "9h ago", sentiment: "bearish" },
  { ticker: "NEE",  headline: "NextEra Energy secures $2B offshore wind project off Florida coast", time: "10h ago", sentiment: "bullish" },
  { ticker: "XOM",  headline: "ExxonMobil raises dividend as Permian Basin output hits 25-year high", time: "11h ago", sentiment: "bullish" },
];

// ── Subcomponents ─────────────────────────────────────────────────────────────

function RiskGauge({ score, size = 100 }) {
  const color = RISK_COLOR(score);
  const s = size;
  const cx = s / 2, cy = s * 0.6, r = s * 0.38;
  const angle = (score / 100) * 180 - 90;
  const rad = (angle * Math.PI) / 180;
  const nx = cx + r * Math.cos(rad);
  const ny = cy + r * Math.sin(rad);
  return (
    <svg width={s} height={s * 0.65} viewBox={`0 0 ${s} ${s * 0.65}`}>
      <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none" stroke="#1a2535" strokeWidth={s * 0.08} strokeLinecap="round" />
      <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none" stroke={color} strokeWidth={s * 0.08} strokeLinecap="round"
        strokeDasharray={`${(score / 100) * Math.PI * r} ${Math.PI * r}`} />
      <line x1={cx} y1={cy} x2={nx} y2={ny} stroke={color} strokeWidth="2" strokeLinecap="round" />
      <circle cx={cx} cy={cy} r="3" fill={color} />
      <text x={cx} y={cy - r * 0.3} textAnchor="middle" fill={color} fontSize={s * 0.115} fontWeight="700">{score}%</text>
    </svg>
  );
}

function MiniChart({ data, positive }) {
  if (!data || !data.length) return null;
  const min = Math.min(...data), max = Math.max(...data);
  const range = max - min || 1;
  const W = 400, H = 80;
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * W},${H - ((v - min) / range) * (H - 8) - 4}`).join(" ");
  const color = positive ? "#00ff9d" : "#ff4d6d";
  return (
    <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ display: "block" }}>
      <defs>
        <linearGradient id="chartGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={`0,${H} ${pts} ${W},${H}`} fill="url(#chartGrad)" />
      <polyline points={pts} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SentimentBar({ label, bullish, bearish, neutral }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
        <span style={{ fontSize: 11, color: "#6a8aaa" }}>{label}</span>
        <span style={{ fontSize: 10, color: "#00ff9d", fontFamily: "monospace" }}>{bullish}% bull</span>
      </div>
      <div style={{ height: 6, background: "#1a2d45", borderRadius: 3, overflow: "hidden", display: "flex" }}>
        <div style={{ width: `${bullish}%`, background: "#00ff9d", transition: "width 0.5s" }} />
        <div style={{ width: `${neutral}%`, background: "#4a6080", transition: "width 0.5s" }} />
        <div style={{ width: `${bearish}%`, background: "#ff4d6d", transition: "width 0.5s" }} />
      </div>
    </div>
  );
}

function TickerPriceCard({ tickerSymbol, priceData, insight }) {
  const price = priceData;
  const up = (price?.change ?? 0) >= 0;
  const riskPct = insight?.risk_percentage ?? 0;
  return (
    <div style={{ background: "#0d1825", border: "1px solid #1a2d45", borderRadius: 10, padding: "10px 14px", minWidth: 150, flex: "1 1 150px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: "#00ff9d", fontFamily: "'JetBrains Mono', monospace" }}>{tickerSymbol}</span>
        {riskPct > 0 && <span style={{ fontSize: 10, color: RISK_COLOR(riskPct), fontFamily: "monospace" }}>Risk {riskPct}%</span>}
      </div>
      {price ? (
        <>
          <div style={{ fontSize: 18, fontWeight: 700, color: "#c8d8e8" }}>${price.current_price?.toFixed(2) ?? "—"}</div>
          <div style={{ fontSize: 11, color: up ? "#00ff9d" : "#ff4d6d", marginBottom: 4 }}>
            {up ? "▲" : "▼"} {Math.abs(price.change_pct ?? 0).toFixed(2)}%
          </div>
          <div style={{ display: "flex", gap: 10 }}>
            <span style={{ fontSize: 10, color: "#3a5070" }}>H: <span style={{ color: "#8aa8c0" }}>${price.day_high?.toFixed(2) ?? "—"}</span></span>
            <span style={{ fontSize: 10, color: "#3a5070" }}>L: <span style={{ color: "#8aa8c0" }}>${price.day_low?.toFixed(2) ?? "—"}</span></span>
          </div>
        </>
      ) : (
        <div style={{ fontSize: 11, color: "#4a6080", marginTop: 4 }}>Loading…</div>
      )}
      {insight?.sentiment_label && (
        <div style={{ marginTop: 6, fontSize: 10, fontWeight: 600, color: SENTIMENT_COLORS[insight.sentiment_label] || "#a0aec0" }}>
          {insight.sentiment_label}
        </div>
      )}
    </div>
  );
}

function TickerCarousel({ livePrices }) {
  const tickers = [...SEED_TICKERS, ...SEED_TICKERS];
  return (
    <div style={styles.ticker}>
      <div style={styles.tickerTrack}>
        {tickers.map((t, i) => {
          const d = livePrices[t];
          if (!d) return (
            <div key={i} style={styles.tickerItem}>
              <span style={styles.tickerSymbol}>{t}</span>
              <span style={{ ...styles.tickerPrice, color: "#4a6080" }}>—</span>
            </div>
          );
          const pos = (d.change ?? d.change_pct ?? 0) >= 0;
          const p = d.current_price ?? 0;
          const pct = Math.abs(d.change_pct ?? 0);
          return (
            <div key={i} style={styles.tickerItem}>
              <span style={styles.tickerSymbol}>{t}</span>
              <span style={styles.tickerPrice}>${p.toFixed(2)}</span>
              <span style={{ ...styles.tickerChange, color: pos ? "#00ff9d" : "#ff4d6d" }}>
                {pos ? "▲" : "▼"} {pct.toFixed(2)}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarSearch, setSidebarSearch] = useState("");
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  // chatHistory entries: { id, title, ts, messages, activeResponse, sessionId }
  const [chatHistory, setChatHistory] = useState([]);
  const [activeTab, setActiveTab] = useState(null);
  const [activeResponse, setActiveResponse] = useState(null);
  const [bottomCollapsed, setBottomCollapsed] = useState(false);
  // Initialise with mock prices so carousel is populated instantly
  const [livePrices, setLivePrices] = useState(MOCK_PRICES);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // ── On mount: fetch all seed prices in parallel via /api/prices ───────────
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/prices`);
        if (!res.ok) return;
        const data = await res.json();
        // data: { AAPL: {...}, NVDA: {...}, ... }
        setLivePrices(prev => ({ ...prev, ...data }));
      } catch (_) {}
    })();
    // Re-fetch every 60s to keep carousel fresh
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/prices`);
        if (!res.ok) return;
        const data = await res.json();
        setLivePrices(prev => ({ ...prev, ...data }));
      } catch (_) {}
    }, 60_000);
    return () => clearInterval(interval);
  }, []);

  // ── Fetch prices for a specific set of tickers in parallel ────────────────
  const fetchPricesFor = useCallback(async (tickers) => {
    if (!tickers || tickers.length === 0) return;
    // Only fetch tickers we don't have live data for yet
    const missing = tickers.filter(t => !livePrices[t] || !livePrices[t].is_live);
    if (missing.length === 0) return;
    try {
      const res = await fetch(`${API_BASE}/prices?tickers=${missing.join(",")}`);
      if (!res.ok) return;
      const data = await res.json();
      setLivePrices(prev => ({ ...prev, ...data }));
    } catch (_) {}
  }, [livePrices]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── News: live from last response OR seed headlines ───────────────────────
  const liveNews = activeResponse?.retrieved_docs?.news?.slice(0, 10).map(doc => ({
    ticker: activeResponse.tickers?.[0] || activeResponse.ticker || "—",
    headline: doc.metadata?.title || doc.document?.slice(0, 80) || "News article",
    time: doc.metadata?.date_str || "recent",
    sentiment: activeResponse.narrative?.risk_level === "LOW" ? "bullish"
      : activeResponse.narrative?.risk_level === "HIGH" ? "bearish" : "neutral",
  })) || [];
  const newsPanel = liveNews.length > 0 ? liveNews : SEED_NEWS;

  // ── Submit ────────────────────────────────────────────────────────────────
  const handleSubmit = useCallback(async () => {
    if (!query.trim() || loading) return;
    const userMsg = query.trim();
    setQuery("");
    setMessages(prev => [...prev, { role: "user", content: userMsg }]);
    setLoading(true);
    setActiveTab(null);

    try {
      const res = await fetch(`${API_BASE}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: userMsg, session_id: sessionId }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      const newSession = data.session_id || sessionId || crypto.randomUUID();
      if (!sessionId) {
        setSessionId(newSession);
      }

      // Cache single-stock price immediately
      if (data.price?.current_price && data.ticker) {
        setLivePrices(prev => ({ ...prev, [data.ticker]: { ...data.price, is_live: true } }));
      }

      // For multi-ticker responses, fetch missing prices in parallel right now
      const involvedTickers = data.tickers?.length > 0
        ? data.tickers
        : (data.narrative?.ticker_insights || []).map(ti => ti.ticker);
      if (involvedTickers.length > 1) {
        fetchPricesFor(involvedTickers);
      }

      setActiveResponse(data);

      const n = data.narrative || {};
      let content = "Analysis complete.";
      if (data.query_type === "out_of_scope") {
        content = n.message || "That doesn't seem to be a financial question.";
      } else if (data.query_type === "single_stock") {
        content = [n.summary, n.conclusion].filter(Boolean).join("\n\n") || "Analysis complete.";
      } else if (data.query_type === "comparison") {
        const insightLines = (n.ticker_insights || [])
          .map(ti => `${ti.ticker}: ${ti.summary} (Risk ${ti.risk_percentage}%)`)
          .join("\n");
        content = [n.answer, insightLines, n.conclusion].filter(Boolean).join("\n\n") || "Analysis complete.";
      } else {
        content = [n.answer, n.conclusion].filter(Boolean).join("\n\n") || "Analysis complete.";
      }

      const displayTicker = data.query_type === "comparison"
        ? (data.tickers || []).join(" vs ")
        : data.ticker;

      const assistantMsg = {
        role: "assistant", content,
        ticker: displayTicker,
        tickers: data.tickers || (data.ticker ? [data.ticker] : []),
        riskScore: data.risk_score?.risk_percentage ?? n.risk_percentage ?? null,
        sentiment: n.risk_level || null,
        queryType: data.query_type,
      };

      setMessages(prev => {
        const updated = [...prev, assistantMsg];
        // Save full conversation snapshot to history
        setChatHistory(hist => {
          const existingIdx = hist.findIndex(h => h.id === newSession);
          const entry = {
            id: newSession,
            title: userMsg.slice(0, 45),
            ts: Date.now(),
            messages: updated,
            activeResponse: data,
            sessionId: newSession,
          };
          if (existingIdx >= 0) {
            const next = [...hist];
            next[existingIdx] = entry;
            return next;
          }
          return [entry, ...hist];
        });
        return updated;
      });
      setActiveTab("price");

    } catch (err) {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: `Error: ${err.message}. Please check that the backend is running.`,
        ticker: null, riskScore: null, sentiment: null,
      }]);
    } finally {
      setLoading(false);
    }
  }, [query, loading, sessionId, fetchPricesFor]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmit(); }
  };

  // ── Start a brand-new empty chat ─────────────────────────────────────────
  const startNewChat = async () => {
    if (sessionId) {
      try { await fetch(`${API_BASE}/session/${sessionId}`, { method: "DELETE" }); } catch (_) {}
    }
    setMessages([]); setSessionId(null); setActiveResponse(null);
    setActiveTab(null); setSidebarOpen(false); setSidebarSearch("");
    inputRef.current?.focus();
  };

  // ── Restore a previous chat from history ─────────────────────────────────
  const loadChat = (entry) => {
    setSessionId(entry.sessionId);
    setMessages(entry.messages || []);
    setActiveResponse(entry.activeResponse || null);
    setActiveTab(entry.activeResponse ? "price" : null);
    setSidebarOpen(false);
    setSidebarSearch("");
  };

  // ── Derived state ─────────────────────────────────────────────────────────
  const isMultiTicker = activeResponse &&
    ["comparison", "cross_portfolio", "general"].includes(activeResponse.query_type);
  const ticker = activeResponse?.ticker;
  const riskScore = activeResponse?.risk_score?.risk_percentage
    ?? activeResponse?.narrative?.risk_percentage ?? 0;
  const price = activeResponse?.price || null;
  const hasConversation = messages.length > 0;

  const multiTickerData = isMultiTicker
    ? (activeResponse?.narrative?.ticker_insights || []).map(ti => ({
        ticker: ti.ticker,
        price: livePrices[ti.ticker] || null,
        insight: ti,
      }))
    : [];

  const sparklineData = useMemo(() => {
    if (!price) return [];
    const { open = 0, day_low = 0, day_high = 0, current_price = 0 } = price;
    const seed = Math.round((open + current_price + day_high + day_low) * 100);
    const pseudoRand = (i) => {
      const x = Math.sin(seed + i * 127.1) * 43758.5453;
      return x - Math.floor(x);
    };
    const pts = Array.from({ length: 20 }, (_, i) => {
      const t = i / 19;
      const base = open + (current_price - open) * t;
      const noise = (day_high - day_low) * 0.15 * (pseudoRand(i) - 0.5);
      return Math.max(day_low, Math.min(day_high, base + noise));
    });
    pts[pts.length - 1] = current_price;
    return pts;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeResponse?.ticker, price?.current_price, price?.open, price?.day_high, price?.day_low]);

  const sentimentData = useMemo(() => {
    if (!activeResponse?.retrieved_docs) return null;
    const { news = [], social = [], reddit_buzz = [] } = activeResponse.retrieved_docs;
    const narrative = activeResponse.narrative || {};

    let newsBull = 0, newsBear = 0;
    news.forEach(doc => {
      const t = (doc.metadata?.title || doc.document || "").toLowerCase();
      if (/beat|surged|gain|up|strong|record|bullish|positive|growth|rose/.test(t)) newsBull++;
      else if (/miss|fell|drop|down|weak|concern|bearish|negative|loss|cut/.test(t)) newsBear++;
    });
    const nt = Math.max(1, news.length);
    const newsBullPct = Math.round((newsBull / nt) * 100);
    const newsBearPct = Math.round((newsBear / nt) * 100);

    const actualRisk  = activeResponse?.risk_score?.risk_percentage ?? narrative?.risk_percentage ?? 50;
    const sentLabel   = narrative?.sentiment_label || "NEUTRAL";
    const labelToBull = { BULLISH: 70, BEARISH: 30, MIXED: 50, NEUTRAL: 50 };
    const socialBullPct = Math.min(95, Math.max(5, labelToBull[sentLabel] ?? 50));
    const socialBearPct = Math.max(0, 100 - socialBullPct - 12);

    const buzz = reddit_buzz[0];
    const rankChange    = buzz?.metadata?.rank_change;
    const redditBullPct = rankChange === "RISING" ? 68 : rankChange === "FALLING" ? 32 : 50;

    const hasContradiction = activeResponse?.risk_score?.contradiction_detected ?? false;
    const contradictionLen = (narrative?.contradictions || "").length;
    const secBullPct = hasContradiction || contradictionLen > 20
      ? Math.max(15, 50 - Math.min(30, Math.round(actualRisk * 0.3)))
      : Math.min(85, 50 + Math.round((100 - actualRisk) * 0.25));

    return {
      news:   { bullish: newsBullPct,   bearish: newsBearPct,   neutral: Math.max(0, 100 - newsBullPct - newsBearPct) },
      social: { bullish: socialBullPct, bearish: socialBearPct, neutral: 12 },
      reddit: { bullish: redditBullPct, bearish: Math.max(0, 100 - redditBullPct - 15), neutral: 15 },
      sec:    { bullish: secBullPct,    bearish: Math.max(0, 100 - secBullPct - 15),    neutral: 15 },
    };
  }, [activeResponse]);

  const secCards = (() => {
    if (!activeResponse?.retrieved_docs?.sec_filings) return [];
    const seen = new Set();
    return activeResponse.retrieved_docs.sec_filings.slice(0, 3).map(doc => {
      const meta = doc.metadata || {};
      const type = meta.filing_type || "SEC";
      if (seen.has(type)) return null;
      seen.add(type);
      return {
        type,
        label: { "10-K": "Annual Report", "10-Q": "Quarterly Report", "8-K": "Material Event" }[type] || "Filing",
        icon:  { "10-K": "📄", "10-Q": "📊", "8-K": "⚡" }[type] || "📋",
        note:  (doc.document?.slice(0, 100).trim() || meta.section || "Filing reviewed") + "...",
        date:  meta.filed_date || "recent",
      };
    }).filter(Boolean);
  })();

  const graphUrl = sessionId ? `${API_BASE}/graph/view/${sessionId}` : null;

  // Filtered history for sidebar search
  const filteredHistory = sidebarSearch.trim()
    ? chatHistory.filter(h => h.title.toLowerCase().includes(sidebarSearch.toLowerCase()))
    : chatHistory;

  return (
    <div style={styles.root}>
      <TickerCarousel livePrices={livePrices} />

      <div style={styles.layout}>
        <button style={styles.sidebarToggle} onClick={() => setSidebarOpen(o => !o)}>
          <span style={styles.hamburger}>{sidebarOpen ? "✕" : "☰"}</span>
        </button>

        {/* ── Sidebar ── */}
        <div style={{ ...styles.sidebar, transform: sidebarOpen ? "translateX(0)" : "translateX(-100%)" }}>
          <div style={styles.sidebarHeader}>
            <div style={styles.logo}>CogniTrade</div>
            <div style={styles.logoSub}>Financial Intelligence Engine</div>
          </div>
          <button style={styles.newChatBtn} onClick={startNewChat}>＋ New Chat</button>

          {/* Functional search */}
          <div style={styles.sidebarSearch}>
            <input
              style={styles.sidebarSearchInput}
              placeholder="Search history…"
              value={sidebarSearch}
              onChange={e => setSidebarSearch(e.target.value)}
            />
          </div>

          <div style={styles.historyLabel}>
            Recent {sidebarSearch && `· ${filteredHistory.length} result${filteredHistory.length !== 1 ? "s" : ""}`}
          </div>
          <div style={styles.historyList}>
            {filteredHistory.length === 0 ? (
              <div style={styles.historyEmpty}>
                {sidebarSearch ? "No matching chats" : "No history yet"}
              </div>
            ) : (
              filteredHistory.map(h => (
                <div
                  key={h.id}
                  style={{
                    ...styles.historyItem,
                    background: h.id === sessionId ? "#0f2030" : "transparent",
                    border: h.id === sessionId ? "1px solid #1a3050" : "1px solid transparent",
                  }}
                  onClick={() => loadChat(h)}
                >
                  <span style={styles.historyIcon}>💬</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={styles.historyTitle}>{h.title}</div>
                    <div style={styles.historyTime}>{new Date(h.ts).toLocaleTimeString()}</div>
                  </div>
                  {h.id === sessionId && (
                    <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#00ff9d", flexShrink: 0, marginTop: 4 }} />
                  )}
                </div>
              ))
            )}
          </div>
          <div style={styles.sidebarFooter}>
            <div style={styles.footerDot} />
            <span style={{ fontSize: 11, color: "#4a6080" }}>Connected to backend</span>
          </div>
        </div>

        {/* ── Chat ── */}
        <div style={styles.chatArea}>
          {!hasConversation ? (
            <div style={styles.welcome}>
              <div style={styles.welcomeLogo}>CogniTrade</div>
              <div style={styles.welcomeSub}>Financial Intelligence Engine</div>
              <div style={styles.welcomeHint}>Ask me anything about the watchlist stocks</div>
              <div style={styles.quickPrompts}>
                {["Is NVDA a risky buy?", "Compare GME and NVDA", "Compare AAPL, MSFT and NVDA",
                  "Which stocks are most bullish on Reddit?", "AAPL SEC filing highlights"].map(p => (
                  <button key={p} style={styles.quickBtn} onClick={() => { setQuery(p); inputRef.current?.focus(); }}>{p}</button>
                ))}
              </div>
            </div>
          ) : (
            <div style={styles.messageList}>
              {messages.map((msg, i) => (
                <div key={i} style={{ ...styles.msgRow, justifyContent: msg.role === "user" ? "flex-end" : "flex-start" }}>
                  {msg.role === "assistant" && <div style={styles.avatarA}>Α</div>}
                  <div style={{ ...styles.bubble, ...(msg.role === "user" ? styles.bubbleUser : styles.bubbleAssistant) }}>
                    {msg.role === "assistant" && msg.ticker && (
                      <div style={styles.bubbleMeta}>
                        <span style={styles.bubbleTicker}>{msg.ticker}</span>
                        {msg.sentiment && (
                          <span style={{ ...styles.bubbleSentiment, color: SENTIMENT_COLORS[msg.sentiment] || "#a0aec0" }}>
                            {msg.sentiment}
                          </span>
                        )}
                        {msg.riskScore != null && (
                          <span style={{ fontSize: 10, color: RISK_COLOR(msg.riskScore), fontFamily: "monospace", marginLeft: 6 }}>
                            Risk {msg.riskScore}%
                          </span>
                        )}
                      </div>
                    )}
                    <div style={styles.bubbleText}>{msg.content}</div>
                  </div>
                  {msg.role === "user" && <div style={styles.avatarU}>U</div>}
                </div>
              ))}
              {loading && (
                <div style={{ ...styles.msgRow, justifyContent: "flex-start" }}>
                  <div style={styles.avatarA}>Α</div>
                  <div style={{ ...styles.bubble, ...styles.bubbleAssistant }}>
                    <div style={styles.typing}>
                      <span style={styles.dot} /><span style={{ ...styles.dot, animationDelay: "0.2s" }} /><span style={{ ...styles.dot, animationDelay: "0.4s" }} />
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
          <div style={{ ...styles.inputArea, ...(hasConversation ? styles.inputAreaBottom : styles.inputAreaCenter) }}>
            <div style={styles.inputWrap}>
              <textarea ref={inputRef} rows={1} value={query}
                onChange={e => setQuery(e.target.value)} onKeyDown={handleKeyDown}
                placeholder="Ask about any stock… (e.g. Compare GME and NVDA)" style={styles.textarea}
              />
              <button onClick={handleSubmit} disabled={!query.trim() || loading} style={styles.sendBtn}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        {/* ── Right Panel: News ── */}
        <div style={styles.rightPanel}>
          <div style={styles.rightHeader}>📡 Live Market News</div>
          <div style={styles.newsScroll}>
            {newsPanel.map((n, i) => (
              <div key={i} style={styles.newsCard}>
                <div style={styles.newsTop}>
                  <span style={styles.newsTicker}>{n.ticker}</span>
                  <span style={{ ...styles.newsLabel, color: SENTIMENT_COLORS[n.sentiment] || "#a0aec0" }}>
                    {n.sentiment === "bullish" ? "▲" : n.sentiment === "bearish" ? "▼" : "◆"} {n.sentiment}
                  </span>
                </div>
                <div style={styles.newsHeadline}>{n.headline}</div>
                <div style={styles.newsTime}>{n.time}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Bottom Panel ── */}
      {hasConversation && (
        <div style={styles.bottomPanel}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", paddingRight: 12 }}>
            <div style={styles.bottomTabs}>
              {[
                { key: "price",     label: "📈 Price" },
                { key: "sentiment", label: "💬 Sentiment" },
                { key: "risk",      label: "⚠️ Risk Score" },
                { key: "sec",       label: "📋 SEC Signals" },
                { key: "graph",     label: "🧠 Knowledge Graph" },
                { key: "reasoning", label: "🔍 Reasoning" },
              ].map(tab => (
                <button key={tab.key}
                  style={{ ...styles.tabBtn, ...(activeTab === tab.key ? styles.tabBtnActive : {}) }}
                  onClick={() => { setActiveTab(activeTab === tab.key ? null : tab.key); setBottomCollapsed(false); }}>
                  {tab.label}
                </button>
              ))}
              {!isMultiTicker && ticker && (
                <span style={styles.tabTicker}>{ticker} · {COMPANY_NAMES[ticker] || ticker}</span>
              )}
              {isMultiTicker && multiTickerData.length > 0 && (
                <span style={styles.tabTicker}>{multiTickerData.map(d => d.ticker).join(" · ")}</span>
              )}
              {price?.is_live && (
                <span style={{ marginLeft: 8, fontSize: 9, color: "#00ff9d", background: "#0d2b1f", padding: "2px 6px", borderRadius: 3 }}>🟢 LIVE</span>
              )}
            </div>
            <button
              onClick={() => setBottomCollapsed(prev => !prev)}
              title={bottomCollapsed ? "Expand panel" : "Minimize panel"}
              style={{
                background: "transparent", border: "1px solid #1a2d45", borderRadius: 6,
                color: "#4a6080", cursor: "pointer", padding: "4px 10px", fontSize: 12,
                display: "flex", alignItems: "center", gap: 5, flexShrink: 0,
                transition: "color 0.2s, border-color 0.2s",
                fontFamily: "'JetBrains Mono', monospace",
              }}
              onMouseEnter={e => { e.currentTarget.style.color = "#00D2FF"; e.currentTarget.style.borderColor = "#00D2FF66"; }}
              onMouseLeave={e => { e.currentTarget.style.color = "#4a6080"; e.currentTarget.style.borderColor = "#1a2d45"; }}
            >
              {bottomCollapsed ? "▲ Expand" : "▼ Minimize"}
            </button>
          </div>

          {activeTab && !bottomCollapsed && (
            <div style={{ ...styles.bottomContent, ...(activeTab === "graph" ? { padding: 0, maxHeight: 420 } : activeTab === "reasoning" ? { maxHeight: 380 } : {}) }}>

              {/* ── PRICE ── */}
              {activeTab === "price" && !isMultiTicker && price && (
                <div style={styles.chartArea}>
                  <div style={styles.chartHeader}>
                    <span style={styles.chartTicker}>{ticker}</span>
                    <span style={styles.chartPrice}>${price.current_price?.toFixed(2) ?? "—"}</span>
                    <span style={{ color: (price.change ?? 0) >= 0 ? "#00ff9d" : "#ff4d6d", fontSize: 13 }}>
                      {(price.change ?? 0) >= 0 ? "▲" : "▼"} {Math.abs(price.change_pct ?? 0).toFixed(2)}%
                    </span>
                  </div>
                  <MiniChart data={sparklineData} positive={(price.change ?? 0) >= 0} />
                  <div style={styles.priceGrid}>
                    {[["Open", price.open], ["High", price.day_high], ["Low", price.day_low], ["Prev Close", price.previous_close]].map(([lbl, val]) => (
                      <div key={lbl} style={styles.priceCell}>
                        <span style={styles.priceLabel}>{lbl}</span>
                        <span style={styles.priceVal}>${val?.toFixed(2) ?? "—"}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {activeTab === "price" && !isMultiTicker && !price && (
                <div style={{ color: "#4a6080", fontSize: 13, padding: "20px 0" }}>No price data available for this query type.</div>
              )}
              {activeTab === "price" && isMultiTicker && (
                <div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
                    {multiTickerData.map(({ ticker: t, price: p, insight }) => (
                      <TickerPriceCard key={t} tickerSymbol={t} priceData={p} insight={insight} />
                    ))}
                  </div>
                  {activeResponse?.narrative?.portfolio_risk_summary && (
                    <div style={{ marginTop: 12, padding: "8px 12px", background: "#0d1825", border: "1px solid #1a2d45", borderRadius: 8, fontSize: 11, color: "#8aa8c0", lineHeight: 1.6 }}>
                      <span style={{ color: "#f6ad55", fontWeight: 600 }}>📊 Portfolio Risk: </span>
                      {activeResponse.narrative.portfolio_risk_summary}
                    </div>
                  )}
                </div>
              )}

              {/* ── SENTIMENT ── */}
              {activeTab === "sentiment" && !isMultiTicker && (
                <div style={styles.sentimentArea}>
                  {sentimentData ? (
                    <>
                      <SentimentBar label="News Sentiment" {...sentimentData.news} />
                      <SentimentBar label="Social Media" {...sentimentData.social} />
                      <SentimentBar label="Reddit Buzz" {...sentimentData.reddit} />
                      <SentimentBar label="SEC vs Social Agreement" {...sentimentData.sec} />
                      {activeResponse?.narrative?.contradictions && (
                        <div style={{ marginTop: 10, padding: "8px 12px", background: "#0d1825", border: "1px solid #1a2d45", borderRadius: 8, fontSize: 11, color: "#8aa8c0", lineHeight: 1.5 }}>
                          <span style={{ color: "#f6ad55", fontWeight: 600 }}>⚠ Key Contradiction: </span>
                          {activeResponse.narrative.contradictions}
                        </div>
                      )}
                    </>
                  ) : (
                    <div style={{ color: "#4a6080", fontSize: 13 }}>Ask about a specific stock for sentiment data.</div>
                  )}
                </div>
              )}
              {activeTab === "sentiment" && isMultiTicker && (
                <div style={styles.sentimentArea}>
                  {multiTickerData.map(({ ticker: t, insight }) => {
                    if (!insight) return null;
                    const sc = SENTIMENT_COLORS[insight.sentiment_label] || "#a0aec0";
                    return (
                      <div key={t} style={{ marginBottom: 14 }}>
                        <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 5 }}>
                          <span style={{ fontSize: 12, fontWeight: 700, color: "#00ff9d", fontFamily: "monospace", minWidth: 50 }}>{t}</span>
                          <span style={{ fontSize: 11, fontWeight: 600, color: sc }}>{insight.sentiment_label}</span>
                          <span style={{ fontSize: 10, color: RISK_COLOR(insight.risk_percentage ?? 0), marginLeft: "auto" }}>Risk {insight.risk_percentage ?? 0}%</span>
                        </div>
                        <div style={{ height: 6, background: "#1a2d45", borderRadius: 3, overflow: "hidden" }}>
                          <div style={{ width: `${(insight.relevance_score ?? 0.5) * 100}%`, background: sc, height: "100%", transition: "width 0.5s" }} />
                        </div>
                        <div style={{ fontSize: 10, color: "#4a6080", marginTop: 4, lineHeight: 1.4 }}>{insight.key_signal}</div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* ── RISK SCORE ── */}
              {activeTab === "risk" && !isMultiTicker && (
                <div style={styles.riskArea}>
                  <div style={styles.riskMain}>
                    <RiskGauge score={riskScore} />
                    <div>
                      <div style={styles.riskLabel}>Overall Risk</div>
                      <div style={{ color: RISK_COLOR(riskScore), fontSize: 24, fontWeight: 700 }}>
                        {activeResponse?.risk_score?.risk_label || (riskScore < 35 ? "Low Risk" : riskScore < 65 ? "Moderate Risk" : "High Risk")}
                      </div>
                      {activeResponse?.risk_score?.dominant_risk_factor && (
                        <div style={{ fontSize: 11, color: "#6a8aaa", marginTop: 6, maxWidth: 200, lineHeight: 1.4 }}>
                          {activeResponse.risk_score.dominant_risk_factor}
                        </div>
                      )}
                    </div>
                  </div>
                  <div style={styles.riskBreakdown}>
                    {(() => {
                      const base = riskScore;
                      const newsBearRaw   = sentimentData?.news.bearish ?? 0;
                      const socialBearRaw = sentimentData?.social.bearish ?? 0;
                      const redditRaw     = sentimentData ? (100 - sentimentData.reddit.bullish) : 0;
                      const secRaw        = secCards.length > 0 ? Math.min(90, secCards.length * 25) : 0;
                      const blend = (raw) => Math.round((raw * 0.4) + (base * 0.6));
                      const rows = [
                        { label: "News Signal Risk",  score: blend(newsBearRaw) },
                        { label: "Social Volatility", score: blend(socialBearRaw) },
                        { label: "Reddit Momentum",   score: blend(redditRaw) },
                        { label: "SEC Filing Flags",  score: secRaw > 0 ? blend(secRaw) : Math.round(base * 0.5) },
                      ];
                      return rows.map(r => (
                        <div key={r.label} style={styles.riskRow}>
                          <span style={styles.riskRowLabel}>{r.label}</span>
                          <div style={styles.riskBar}><div style={{ ...styles.riskFill, width: `${r.score}%`, background: RISK_COLOR(r.score) }} /></div>
                          <span style={styles.riskPct}>{r.score}%</span>
                        </div>
                      ));
                    })()}
                  </div>
                </div>
              )}
              {activeTab === "risk" && isMultiTicker && (
                <div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "flex-start" }}>
                    {multiTickerData.map(({ ticker: t, insight }) => {
                      if (!insight) return null;
                      const rp = insight.risk_percentage ?? 0;
                      return (
                        <div key={t} style={{ textAlign: "center", minWidth: 80 }}>
                          <RiskGauge score={rp} size={80} />
                          <div style={{ fontSize: 11, fontWeight: 700, color: "#00ff9d", fontFamily: "monospace", marginTop: 2 }}>{t}</div>
                          <div style={{ fontSize: 10, color: RISK_COLOR(rp) }}>{insight.risk_level}</div>
                        </div>
                      );
                    })}
                  </div>
                  {activeResponse?.narrative?.portfolio_risk_summary && (
                    <div style={{ marginTop: 12, padding: "8px 12px", background: "#0d1825", border: "1px solid #1a2d45", borderRadius: 8, fontSize: 11, color: "#8aa8c0", lineHeight: 1.6 }}>
                      <span style={{ color: "#c8d8e8", fontWeight: 600 }}>Summary: </span>
                      {activeResponse.narrative.portfolio_risk_summary}
                    </div>
                  )}
                </div>
              )}

              {/* ── SEC SIGNALS ── */}
              {activeTab === "sec" && !isMultiTicker && (
                <div style={styles.secArea}>
                  {secCards.length > 0 ? secCards.map(s => (
                    <div key={s.type} style={styles.secCard}>
                      <div style={styles.secIcon}>{s.icon}</div>
                      <div style={{ flex: 1 }}>
                        <div style={styles.secType}>{s.type} — {s.label}</div>
                        <div style={styles.secNote}>{s.note}</div>
                        {s.date && <div style={{ fontSize: 10, color: "#3a5070", marginTop: 2 }}>Filed: {s.date}</div>}
                      </div>
                      <div style={styles.secBadge}>Live</div>
                    </div>
                  )) : <div style={{ color: "#4a6080", fontSize: 13 }}>No SEC filing data available.</div>}
                  {activeResponse?.narrative?.sec_filings_analysis && (
                    <div style={{ marginTop: 8, padding: "10px 14px", background: "#0d1825", border: "1px solid #1a2d45", borderRadius: 10, fontSize: 11, color: "#8aa8c0", lineHeight: 1.6 }}>
                      <span style={{ color: "#c8d8e8", fontWeight: 600 }}>AI Analysis: </span>
                      {activeResponse.narrative.sec_filings_analysis}
                    </div>
                  )}
                </div>
              )}
              {activeTab === "sec" && isMultiTicker && (
                <div style={styles.secArea}>
                  {multiTickerData.length === 0
                    ? <div style={{ color: "#4a6080", fontSize: 13 }}>No SEC data for this query.</div>
                    : multiTickerData.map(({ ticker: t, insight }) => {
                        if (!insight) return null;
                        return (
                          <div key={t} style={styles.secCard}>
                            <div style={styles.secIcon}>📋</div>
                            <div style={{ flex: 1 }}>
                              <div style={styles.secType}>{t} — {COMPANY_NAMES[t] || t}</div>
                              <div style={styles.secNote}>{insight.key_signal}</div>
                            </div>
                            <div style={{ ...styles.secBadge, color: SENTIMENT_COLORS[insight.sentiment_label] || "#a0aec0", background: "transparent", border: "none" }}>
                              {insight.sentiment_label}
                            </div>
                          </div>
                        );
                      })
                  }
                </div>
              )}

              {/* ── CHAIN-OF-THOUGHT REASONING ── */}
              {activeTab === "reasoning" && (() => {
                const n = activeResponse?.narrative;
                if (!n) return (
                  <div style={{ color: "#4a6080", fontSize: 13 }}>Ask about a specific stock to see the reasoning chain.</div>
                );
                const cotSteps = isMultiTicker ? [
                  { num: "01", title: "Query Classification",        icon: "🎯", text: n.answer },
                  { num: "02", title: "Cross-Portfolio Signal Scan", icon: "📡", text: n.methodology },
                  { num: "03", title: "Ticker-Level Intelligence",   icon: "📊", text: (n.ticker_insights || []).map(ti => `${ti.ticker}: ${ti.summary}`).join(" | ") },
                  { num: "04", title: "Synthesized Conclusion",      icon: "✅", text: n.conclusion },
                ] : [
                  { num: "01", title: "News Signal Analysis",    icon: "📰", text: n.news_analysis },
                  { num: "02", title: "Social Media Sentiment",  icon: "💬", text: n.social_sentiment },
                  { num: "03", title: "Reddit Momentum Signal",  icon: "📈", text: n.reddit_buzz_signal },
                  { num: "04", title: "SEC Filing Intelligence", icon: "📋", text: n.sec_filings_analysis },
                  { num: "05", title: "Price Action Context",    icon: "💹", text: n.price_context },
                  { num: "06", title: "Contradiction Detection", icon: "⚠️", text: n.contradictions || "No significant contradictions detected across data sources." },
                  { num: "07", title: "Synthesized Conclusion",  icon: "✅", text: n.conclusion },
                ];
                const completedCount = cotSteps.filter(s => s.text && s.text.trim().length > 10).length;
                return (
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
                      <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#00ff9d", boxShadow: "0 0 8px #00ff9d" }} />
                      <span style={{ fontSize: 11, fontWeight: 700, color: "#00D2FF", textTransform: "uppercase", letterSpacing: 2, fontFamily: "'JetBrains Mono', monospace" }}>
                        Chain-of-Thought Reasoning
                      </span>
                      <span style={{ marginLeft: "auto", fontSize: 10, color: "#4a6080", fontFamily: "'JetBrains Mono', monospace" }}>
                        {completedCount}/{cotSteps.length} steps
                      </span>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
                      {cotSteps.map((step, idx) => {
                        const isLast     = idx === cotSteps.length - 1;
                        const hasContent = step.text && step.text.trim().length > 10;
                        const isContra   = step.num === "06";
                        const noContra   = step.text === "No significant contradictions detected across data sources.";
                        const stepColor  = isContra && hasContent && !noContra ? "#f6ad55" : isLast ? "#00ff9d" : "#00D2FF";
                        const numBg      = isContra && hasContent && !noContra ? "#2a1a00" : isLast ? "#002a1a" : "#0a1e2f";
                        const numBorder  = isContra && hasContent && !noContra ? "#f6ad5544" : isLast ? "#00ff9d44" : "#00D2FF44";
                        return (
                          <div key={step.num} style={{ display: "flex", gap: 14, position: "relative" }}>
                            {!isLast && (
                              <div style={{ position: "absolute", left: 17, top: 36, bottom: 0, width: 1, background: "linear-gradient(to bottom, #1a3050, transparent)", zIndex: 0 }} />
                            )}
                            <div style={{ width: 36, height: 36, borderRadius: 8, flexShrink: 0, background: numBg, border: `1px solid ${numBorder}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, color: stepColor, fontFamily: "'JetBrains Mono', monospace", zIndex: 1, marginTop: 2 }}>
                              {step.num}
                            </div>
                            <div style={{ flex: 1, paddingBottom: isLast ? 0 : 16 }}>
                              <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 4 }}>
                                <span style={{ fontSize: 13 }}>{step.icon}</span>
                                <span style={{ fontSize: 12, fontWeight: 700, color: hasContent ? "#c8d8e8" : "#3a5070" }}>{step.title}</span>
                              </div>
                              {hasContent
                                ? <div style={{ fontSize: 11, color: "#8aa8c0", lineHeight: 1.65, paddingRight: 8 }}>{step.text}</div>
                                : <div style={{ fontSize: 11, color: "#2a4060", fontStyle: "italic" }}>Awaiting data…</div>
                              }
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })()}

              {/* ── KNOWLEDGE GRAPH ── */}
              {activeTab === "graph" && (
                <div style={{ height: 420, width: "100%", position: "relative" }}>
                  {graphUrl ? (
                    <iframe key={graphUrl} src={graphUrl} title="Knowledge Graph"
                      style={{ width: "100%", height: "100%", border: "none", background: "#1a1a2e" }} />
                  ) : (
                    <div style={{ color: "#4a6080", fontSize: 13, padding: 20 }}>
                      Run a query first to generate a knowledge graph.
                    </div>
                  )}
                </div>
              )}

            </div>
          )}
        </div>
      )}

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #070d16; font-family: 'Space Grotesk', sans-serif; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #1e3050; border-radius: 2px; }
        @keyframes scroll { 0% { transform: translateX(0); } 100% { transform: translateX(-50%); } }
        @keyframes bounce { 0%, 80%, 100% { transform: translateY(0); } 40% { transform: translateY(-6px); } }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
      `}</style>
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────
// ── Styles (Cyber-Vantage Palette Updated) ────────────────────────────────────
const styles = {
  root: { display: "flex", flexDirection: "column", height: "100vh", background: "#0A0E17", color: "#E0E6ED", overflow: "hidden" },
  ticker: { height: 32, background: "#0D121F", borderBottom: "1px solid #1A2D45", overflow: "hidden", flexShrink: 0 },
  tickerTrack: { display: "flex", animation: "scroll 60s linear infinite", width: "max-content", height: "100%", alignItems: "center" },
  tickerItem: { display: "flex", gap: 6, alignItems: "center", padding: "0 20px", borderRight: "1px solid #1A2D45", height: "100%" },
  tickerSymbol: { fontSize: 11, fontWeight: 700, color: "#00D2FF", fontFamily: "'JetBrains Mono', monospace" },
  tickerPrice: { fontSize: 11, color: "#E0E6ED", fontFamily: "'JetBrains Mono', monospace" },
  tickerChange: { fontSize: 10, fontFamily: "'JetBrains Mono', monospace" }, // Τα χρώματα (green/red) ορίζονται συνήθως inline στο component
  layout: { display: "flex", flex: 1, minHeight: 0, position: "relative" },
  sidebarToggle: { position: "absolute", top: 12, left: 12, zIndex: 100, background: "#162130", border: "1px solid #00D2FF44", borderRadius: 8, width: 36, height: 36, cursor: "pointer", color: "#00D2FF" },
  hamburger: { fontSize: 14 },
  sidebar: { position: "absolute", top: 0, left: 0, bottom: 0, width: 260, background: "#0D121F", borderRight: "1px solid #1A2D45", zIndex: 90, display: "flex", flexDirection: "column", transition: "transform 0.3s ease", padding: "16px 0 0" },
  sidebarHeader: { padding: "8px 20px 16px", borderBottom: "1px solid #1A2D45" },
  logo: { fontSize: 18, fontWeight: 700, color: "#00D2FF", letterSpacing: 2, fontFamily: "'JetBrains Mono', monospace", textShadow: "0 0 10px #00D2FF66" },
  logoSub: { fontSize: 10, color: "#4A6080", marginTop: 2 },
  newChatBtn: { margin: "16px 16px 8px", padding: "10px 16px", background: "linear-gradient(135deg, #0A1E2F, #06121A)", border: "1px solid #00D2FF66", borderRadius: 10, color: "#00D2FF", fontSize: 13, fontWeight: 600, cursor: "pointer" },
  sidebarSearch: { padding: "4px 16px 12px" },
  sidebarSearchInput: { width: "100%", padding: "8px 12px", background: "#162130", border: "1px solid #1A3050", borderRadius: 8, color: "#E0E6ED", fontSize: 12, outline: "none" },
  historyLabel: { padding: "0 16px 8px", fontSize: 10, color: "#4A6080", textTransform: "uppercase", letterSpacing: 1 },
  historyList: { flex: 1, overflowY: "auto", padding: "0 8px" },
  historyEmpty: { padding: "20px 12px", fontSize: 12, color: "#4A6080", textAlign: "center" },
  historyItem: { display: "flex", alignItems: "flex-start", gap: 10, padding: "10px 12px", borderRadius: 8, cursor: "pointer", marginBottom: 2, transition: "background 0.15s" },
  historyIcon: { fontSize: 14, marginTop: 1, color: "#00D2FF" },
  historyTitle: { fontSize: 12, color: "#8AA8C0", lineHeight: 1.4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 160 },
  historyTime: { fontSize: 10, color: "#3A5070", marginTop: 2 },
  sidebarFooter: { padding: "12px 20px", borderTop: "1px solid #1A2D45", display: "flex", alignItems: "center", gap: 8 },
  footerDot: { width: 7, height: 7, borderRadius: "50%", background: "#39FF14", boxShadow: "0 0 8px #39FF14" },
  chatArea: { flex: 1, display: "flex", flexDirection: "column", minWidth: 0 },
  welcome: { flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12, padding: 24 },
  welcomeLogo: { fontSize: 48, fontWeight: 700, color: "#00D2FF", letterSpacing: 4, fontFamily: "'JetBrains Mono', monospace", textShadow: "0 0 20px #00D2FF44" },
  welcomeSub: { fontSize: 14, color: "#8AA8C0", letterSpacing: 2 },
  welcomeHint: { fontSize: 12, color: "#4A6080", marginTop: 8 },
  quickPrompts: { display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center", marginTop: 16 },
  quickBtn: { padding: "8px 16px", background: "#162130", border: "1px solid #1A3050", borderRadius: 20, color: "#00D2FF", fontSize: 12, cursor: "pointer", transition: "all 0.2s" },
  messageList: { flex: 1, overflowY: "auto", padding: "16px 24px", display: "flex", flexDirection: "column", gap: 12 },
  msgRow: { display: "flex", gap: 10, alignItems: "flex-start" },
  avatarA: { width: 30, height: 30, borderRadius: "50%", background: "linear-gradient(135deg, #0A1E2F, #00D2FF33)", border: "1px solid #00D2FF66", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 700, color: "#00D2FF", flexShrink: 0 },
  avatarU: { width: 30, height: 30, borderRadius: "50%", background: "#1A2D45", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700, color: "#E0E6ED", flexShrink: 0 },
  bubble: { maxWidth: "72%", padding: "10px 14px", borderRadius: 14, lineHeight: 1.6, animation: "fadeIn 0.2s ease" },
  bubbleUser: { background: "#162130", border: "1px solid #1A3A5C", color: "#E0E6ED", borderRadius: "14px 14px 4px 14px" },
  bubbleAssistant: { background: "#0D121F", border: "1px solid #1A2D45", color: "#E0E6ED", borderRadius: "14px 14px 14px 4px" },
  bubbleMeta: { display: "flex", gap: 8, alignItems: "center", marginBottom: 6 },
  bubbleTicker: { fontSize: 10, fontWeight: 700, color: "#39FF14", fontFamily: "'JetBrains Mono', monospace", background: "#0A2015", padding: "1px 6px", borderRadius: 3 },
  bubbleSentiment: { fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: 1 },
  bubbleText: { fontSize: 13, whiteSpace: "pre-wrap" },
  typing: { display: "flex", gap: 4, alignItems: "center", padding: "4px 0" },
  dot: { width: 7, height: 7, borderRadius: "50%", background: "#00D2FF", animation: "bounce 1.2s infinite" },
  inputArea: { padding: "0 24px 12px" },
  inputAreaCenter: {},
  inputAreaBottom: {},
  inputWrap: { display: "flex", alignItems: "flex-end", background: "#0D121F", border: "1px solid #1A3050", borderRadius: 14, overflow: "hidden", transition: "border 0.2s" },
  textarea: { flex: 1, background: "transparent", border: "none", outline: "none", color: "#E0E6ED", fontSize: 14, padding: "14px 16px", resize: "none", fontFamily: "'Space Grotesk', sans-serif", lineHeight: 1.5, minHeight: 48 },
  sendBtn: { padding: "12px 16px", background: "transparent", border: "none", cursor: "pointer", color: "#FF007F" },
  rightPanel: { width: 240, background: "#0D121F", borderLeft: "1px solid #1A2D45", display: "flex", flexDirection: "column", overflow: "hidden" },
  rightHeader: { padding: "14px 16px 10px", fontSize: 11, fontWeight: 700, color: "#4A6080", textTransform: "uppercase", letterSpacing: 1, borderBottom: "1px solid #1A2D45" },
  newsScroll: { flex: 1, overflowY: "auto", padding: "8px" },
  newsCard: { padding: "10px 12px", marginBottom: 6, background: "#111827", border: "1px solid #1A2D45", borderRadius: 10 },
  newsTop: { display: "flex", justifyContent: "space-between", marginBottom: 5 },
  newsTicker: { fontSize: 10, fontWeight: 700, color: "#00D2FF", fontFamily: "'JetBrains Mono', monospace", background: "#0A1E2F", padding: "1px 6px", borderRadius: 3 },
  newsLabel: { fontSize: 9, fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 },
  newsHeadline: { fontSize: 11, color: "#E0E6ED", lineHeight: 1.4, marginBottom: 4 },
  newsTime: { fontSize: 10, color: "#4A6080" },
  bottomPanel: { background: "#0D121F", borderTop: "1px solid #1A2D45" },
  bottomTabs: { display: "flex", gap: 4, padding: "10px 16px 0", alignItems: "center", overflowX: "auto" },
  tabBtn: { padding: "7px 14px", background: "transparent", border: "1px solid #1A2D45", borderRadius: "8px 8px 0 0", color: "#4A6080", fontSize: 12, cursor: "pointer", whiteSpace: "nowrap" },
  tabBtnActive: { background: "#162130", borderColor: "#00D2FF66", color: "#00D2FF", borderBottomColor: "#162130" },
  tabTicker: { marginLeft: "auto", fontSize: 11, color: "#4A6080", fontFamily: "'JetBrains Mono', monospace" },
  bottomContent: { background: "#162130", padding: "16px 20px", maxHeight: 220, overflowY: "auto" },
  chartArea: {},
  chartHeader: { display: "flex", gap: 12, alignItems: "baseline", marginBottom: 8 },
  chartTicker: { fontSize: 16, fontWeight: 700, color: "#00D2FF", fontFamily: "'JetBrains Mono', monospace" },
  chartPrice: { fontSize: 22, fontWeight: 700, color: "#E0E6ED" },
  priceGrid: { display: "flex", gap: 16, marginTop: 10 },
  priceCell: { display: "flex", flexDirection: "column", gap: 2 },
  priceLabel: { fontSize: 10, color: "#4A6080" },
  priceVal: { fontSize: 12, color: "#E0E6ED", fontFamily: "'JetBrains Mono', monospace" },
  sentimentArea: { padding: "4px 0" },
  riskArea: { display: "flex", gap: 32, alignItems: "flex-start" },
  riskMain: { display: "flex", gap: 16, alignItems: "center", flexShrink: 0 },
  riskLabel: { fontSize: 11, color: "#4A6080", marginBottom: 4 },
  riskBreakdown: { flex: 1 },
  riskRow: { display: "flex", alignItems: "center", gap: 10, marginBottom: 10 },
  riskRowLabel: { fontSize: 11, color: "#8AA8C0", width: 180, flexShrink: 0 },
  riskBar: { flex: 1, height: 6, background: "#1A2D45", borderRadius: 3, overflow: "hidden" },
  riskFill: { height: "100%", borderRadius: 3, transition: "width 0.5s ease" }, // Το χρώμα ορίζεται βάσει score (π.χ. Neon Green ή Pink)
  riskPct: { fontSize: 11, color: "#00D2FF", width: 35, textAlign: "right", fontFamily: "'JetBrains Mono', monospace" },
  secArea: { display: "flex", flexDirection: "column", gap: 8 },
  secCard: { display: "flex", alignItems: "center", gap: 14, padding: "10px 14px", background: "#111827", border: "1px solid #1A2D45", borderRadius: 10 },
  secIcon: { fontSize: 20, flexShrink: 0 },
  secType: { fontSize: 12, fontWeight: 600, color: "#E0E6ED", marginBottom: 2 },
  secNote: { fontSize: 11, color: "#4A6080" },
  secBadge: { marginLeft: "auto", fontSize: 9, background: "#0A2015", color: "#39FF14", border: "1px solid #39FF1444", borderRadius: 4, padding: "2px 7px", fontWeight: 700, flexShrink: 0 },
};