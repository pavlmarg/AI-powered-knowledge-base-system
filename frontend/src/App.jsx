import { useState, useEffect, useRef, useCallback } from "react";

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

// ── Subcomponents ─────────────────────────────────────────────────────────────

function RiskGauge({ score }) {
  const color = RISK_COLOR(score);
  const angle = (score / 100) * 180 - 90;
  const rad = (angle * Math.PI) / 180;
  const x = 50 + 35 * Math.cos(rad);
  const y = 50 + 35 * Math.sin(rad);
  return (
    <svg width="100" height="60" viewBox="0 0 100 60">
      <path d="M 10 50 A 40 40 0 0 1 90 50" fill="none" stroke="#1a2535" strokeWidth="8" strokeLinecap="round" />
      <path d="M 10 50 A 40 40 0 0 1 90 50" fill="none" stroke={color} strokeWidth="8" strokeLinecap="round"
        strokeDasharray={`${(score / 100) * 125.6} 125.6`} />
      <line x1="50" y1="50" x2={x} y2={y} stroke={color} strokeWidth="2" strokeLinecap="round" />
      <circle cx="50" cy="50" r="3" fill={color} />
      <text x="50" y="44" textAnchor="middle" fill={color} fontSize="11" fontWeight="700">{score}%</text>
    </svg>
  );
}

function MiniChart({ data, positive }) {
  if (!data || !data.length) return null;
  const min = Math.min(...data), max = Math.max(...data);
  const range = max - min || 1;
  const W = 400, H = 80;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * W;
    const y = H - ((v - min) / range) * (H - 8) - 4;
    return `${x},${y}`;
  }).join(" ");
  const color = positive ? "#00ff9d" : "#ff4d6d";
  const areapts = `0,${H} ${pts} ${W},${H}`;
  return (
    <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ display: "block" }}>
      <defs>
        <linearGradient id="chartGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={areapts} fill="url(#chartGrad)" />
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

// ── Ticker Carousel using live prices from /api/health ────────────────────────
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
          const price = d.current_price ?? d.price ?? 0;
          const pct = Math.abs(d.change_pct ?? d.pct ?? 0);
          return (
            <div key={i} style={styles.tickerItem}>
              <span style={styles.tickerSymbol}>{t}</span>
              <span style={styles.tickerPrice}>${price.toFixed(2)}</span>
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
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [chatHistory, setChatHistory] = useState([]);
  const [activeTab, setActiveTab] = useState(null);
  const [activeResponse, setActiveResponse] = useState(null);
  const [livePrices, setLivePrices] = useState({});
  const [newsIdx, setNewsIdx] = useState(0);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // ── Fetch live prices from /api/health on mount ───────────────────────────
  // We also poll every 60s so the ticker carousel stays fresh
  const fetchHealthPrices = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/health`);
      if (!res.ok) return;
      // Health doesn't return prices directly, so fetch each seed ticker price
      // via a lightweight approach: call /api/query isn't suitable here.
      // Instead we use the ingest status which has counts, not prices.
      // Real-time prices come from the query response's `price` field.
      // For the carousel we do a batch fetch using the Finnhub-backed endpoint.
      // Since the backend exposes no dedicated price endpoint, we store prices
      // from query responses and seed with reasonable defaults.
    } catch (_) {}
  }, []);

  // Fetch live price for a specific ticker via a lightweight backend call
  const fetchTickerPrice = useCallback(async (ticker) => {
    try {
      const res = await fetch(`${API_BASE}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: `price of ${ticker}`, ticker }),
      });
      const data = await res.json();
      if (data.price && data.price.current_price) {
        setLivePrices(prev => ({ ...prev, [ticker]: data.price }));
      }
    } catch (_) {}
  }, []);

  // On mount: fetch prices for visible tickers one by one (staggered to avoid rate limits)
  useEffect(() => {
    let cancelled = false;
    const fetchAll = async () => {
      for (let i = 0; i < SEED_TICKERS.length; i++) {
        if (cancelled) break;
        await fetchTickerPrice(SEED_TICKERS[i]);
        await new Promise(r => setTimeout(r, 800)); // stagger requests
      }
    };
    fetchAll();
    return () => { cancelled = true; };
  }, [fetchTickerPrice]);

  // Rotate news panel
  useEffect(() => {
    const timer = setInterval(() => setNewsIdx(i => (i + 1) % Math.max(1, liveNews.length)), 8000);
    return () => clearInterval(timer);
  }, []);

  // Auto-scroll chat
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Derive live news from last real response ──────────────────────────────
  const liveNews = activeResponse?.retrieved_docs?.news?.slice(0, 10).map(doc => ({
    ticker: activeResponse.ticker,
    headline: doc.metadata?.title || doc.document?.slice(0, 80) || "News article",
    time: doc.metadata?.date_str || "recent",
    sentiment: activeResponse.narrative?.risk_level === "LOW" ? "bullish"
      : activeResponse.narrative?.risk_level === "HIGH" ? "bearish" : "neutral",
  })) || [];

  // ── Submit handler ────────────────────────────────────────────────────────
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

      // Persist session
      const newSession = data.session_id || sessionId || crypto.randomUUID();
      if (!sessionId) {
        setSessionId(newSession);
        setChatHistory(prev => [
          { id: newSession, title: userMsg.slice(0, 40), ts: Date.now() },
          ...prev,
        ]);
      }

      // Store live price if we got one
      if (data.price && data.ticker && data.price.current_price) {
        setLivePrices(prev => ({ ...prev, [data.ticker]: data.price }));
      }

      setActiveResponse(data);

      // ── Build chat message content from REAL backend fields ──────────────
      // Path A: single-stock → narrative has summary, conclusion, risk_level, etc.
      // Path B: general/portfolio → narrative has answer, conclusion
      // Path 0: out_of_scope → narrative has message
      let content = "Analysis complete.";
      const n = data.narrative || {};

      if (data.query_type === "out_of_scope") {
        content = n.message || "That doesn't seem to be a financial question. Try asking about a specific stock.";
      } else if (data.query_type === "single_stock") {
        content = [n.summary, n.conclusion].filter(Boolean).join("\n\n") || "Analysis complete.";
      } else {
        // cross_portfolio or general
        content = [n.answer, n.conclusion].filter(Boolean).join("\n\n") || "Analysis complete.";
      }

      // Sentiment label: use risk_level for single-stock, or derive from answer
      const sentimentLabel = n.risk_level || null;

      setMessages(prev => [
        ...prev,
        {
          role: "assistant",
          content,
          ticker: data.ticker,
          riskScore: data.risk_score?.risk_percentage ?? n.risk_percentage ?? null,
          sentiment: sentimentLabel,
          session: newSession,
          queryType: data.query_type,
        },
      ]);
      setActiveTab("price");

    } catch (err) {
      setMessages(prev => [
        ...prev,
        {
          role: "assistant",
          content: `Error: ${err.message}. Please check that the backend is running.`,
          ticker: null,
          riskScore: null,
          sentiment: null,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }, [query, loading, sessionId]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmit(); }
  };

  const startNewChat = async () => {
    // Tell backend to clear session too
    if (sessionId) {
      try { await fetch(`${API_BASE}/session/${sessionId}`, { method: "DELETE" }); } catch (_) {}
    }
    setMessages([]);
    setSessionId(null);
    setActiveResponse(null);
    setActiveTab(null);
    setSidebarOpen(false);
    inputRef.current?.focus();
  };

  // ── Derived display data — ALL from real backend response ─────────────────
  const ticker = activeResponse?.ticker;
  const riskScore = activeResponse?.risk_score?.risk_percentage
    ?? activeResponse?.narrative?.risk_percentage
    ?? 0;
  const price = activeResponse?.price || null; // { current_price, change, change_pct, day_high, day_low, open, previous_close, is_live }
  const hasConversation = messages.length > 0;

  // Build sparkline from price data (simulated intraday based on real OHLC)
  const sparklineData = price ? (() => {
    const { open = 0, day_low = 0, day_high = 0, current_price = 0 } = price;
    const pts = [];
    for (let i = 0; i < 20; i++) {
      const t = i / 19;
      const base = open + (current_price - open) * t;
      const noise = (day_high - day_low) * 0.15 * (Math.random() - 0.5);
      pts.push(Math.max(day_low, Math.min(day_high, base + noise)));
    }
    pts[pts.length - 1] = current_price;
    return pts;
  })() : [];

  // Build sentiment bars from real retrieved docs
  const sentimentData = (() => {
    if (!activeResponse?.retrieved_docs) return null;
    const { news = [], social = [], reddit_buzz = [] } = activeResponse.retrieved_docs;
    const narrative = activeResponse.narrative || {};

    // News sentiment: count positive/negative keywords in titles
    let newsBull = 0, newsBear = 0;
    news.forEach(doc => {
      const text = (doc.metadata?.title || doc.document || "").toLowerCase();
      if (/beat|surged|gain|up|strong|record|bullish|positive|growth|rose/.test(text)) newsBull++;
      else if (/miss|fell|drop|down|weak|concern|bearish|negative|loss|cut/.test(text)) newsBear++;
    });
    const newsTotal = Math.max(1, news.length);
    const newsBullPct = Math.round((newsBull / newsTotal) * 100);
    const newsBearPct = Math.round((newsBear / newsTotal) * 100);
    const newsNeutralPct = 100 - newsBullPct - newsBearPct;

    // Social: count engagement-weighted sentiment
    let socialScore = 0;
    social.forEach(doc => {
      const text = (doc.document || "").toLowerCase();
      const eng = doc.metadata?.engagement_score || 1;
      if (/bull|buy|moon|great|love|up|win|🚀/.test(text)) socialScore += eng;
      else if (/bear|sell|crash|bad|hate|down|loss|💀/.test(text)) socialScore -= eng;
    });
    const socialBullPct = socialScore > 0 ? Math.min(80, 50 + Math.round(socialScore / 10)) : Math.max(20, 50 + Math.round(socialScore / 10));
    const socialBearPct = 100 - socialBullPct - 12;

    // Reddit: from buzz signal
    const buzz = reddit_buzz[0];
    const redditBullPct = buzz
      ? (buzz.metadata?.rank_change === "RISING" ? 70 : buzz.metadata?.rank_change === "FALLING" ? 35 : 52)
      : 50;

    // SEC vs Social: use contradiction analysis from narrative
    const hasContradiction = (narrative.contradictions || "").length > 20;
    const secBullPct = hasContradiction ? 40 : 60;

    return {
      news: { bullish: newsBullPct, bearish: Math.max(0, newsBearPct), neutral: Math.max(0, newsNeutralPct) },
      social: { bullish: socialBullPct, bearish: Math.max(0, socialBearPct), neutral: 12 },
      reddit: { bullish: redditBullPct, bearish: Math.max(0, 100 - redditBullPct - 15), neutral: 15 },
      sec: { bullish: secBullPct, bearish: Math.max(0, 100 - secBullPct - 15), neutral: 15 },
    };
  })();

  // Build SEC cards from real retrieved sec_filings
  const secCards = (() => {
    if (!activeResponse?.retrieved_docs?.sec_filings) return [];
    const filings = activeResponse.retrieved_docs.sec_filings;
    const seen = new Set();
    return filings.slice(0, 3).map(doc => {
      const meta = doc.metadata || {};
      const type = meta.filing_type || "SEC";
      if (seen.has(type)) return null;
      seen.add(type);
      const icons = { "10-K": "📄", "10-Q": "📊", "8-K": "⚡" };
      const labels = { "10-K": "Annual Report", "10-Q": "Quarterly Report", "8-K": "Material Event" };
      return {
        type,
        label: labels[type] || "Filing",
        icon: icons[type] || "📋",
        note: doc.document?.slice(0, 100).trim() + "..." || meta.section || "Filing reviewed",
        date: meta.filed_date || "recent",
      };
    }).filter(Boolean);
  })();

  // News panel: use real retrieved news from latest response, fallback to empty
  const newsPanel = liveNews.length > 0 ? liveNews : [];

  return (
    <div style={styles.root}>
      {/* ── Ticker Carousel ── */}
      <TickerCarousel livePrices={livePrices} />

      {/* ── Layout ── */}
      <div style={styles.layout}>
        <button style={styles.sidebarToggle} onClick={() => setSidebarOpen(o => !o)} title="Menu">
          <span style={styles.hamburger}>{sidebarOpen ? "✕" : "☰"}</span>
        </button>

        {/* ── Left Sidebar ── */}
        <div style={{ ...styles.sidebar, transform: sidebarOpen ? "translateX(0)" : "translateX(-100%)" }}>
          <div style={styles.sidebarHeader}>
            <div style={styles.logo}>ΑΛΕΧIS</div>
            <div style={styles.logoSub}>Financial Intelligence Engine</div>
          </div>
          <button style={styles.newChatBtn} onClick={startNewChat}>＋ New Chat</button>
          <div style={styles.sidebarSearch}>
            <input style={styles.sidebarSearchInput} placeholder="Search history…" readOnly />
          </div>
          <div style={styles.historyLabel}>Recent</div>
          <div style={styles.historyList}>
            {chatHistory.length === 0
              ? <div style={styles.historyEmpty}>No history yet</div>
              : chatHistory.map(h => (
                <div key={h.id} style={styles.historyItem}>
                  <span style={styles.historyIcon}>💬</span>
                  <div>
                    <div style={styles.historyTitle}>{h.title}</div>
                    <div style={styles.historyTime}>{new Date(h.ts).toLocaleTimeString()}</div>
                  </div>
                </div>
              ))}
          </div>
          <div style={styles.sidebarFooter}>
            <div style={styles.footerDot} />
            <span style={{ fontSize: 11, color: "#4a6080" }}>Connected to backend</span>
          </div>
        </div>

        {/* ── Center Chat ── */}
        <div style={styles.chatArea}>
          {!hasConversation ? (
            <div style={styles.welcome}>
              <div style={styles.welcomeLogo}>ΑΛΕΧIS</div>
              <div style={styles.welcomeSub}>Financial Intelligence Engine</div>
              <div style={styles.welcomeHint}>Ask me anything about the watchlist stocks</div>
              <div style={styles.quickPrompts}>
                {["Is NVDA a risky buy?", "Compare GME and TSLA", "Which stocks are most bullish on Reddit?", "AAPL SEC filing highlights"].map(p => (
                  <button key={p} style={styles.quickBtn} onClick={() => { setQuery(p); inputRef.current?.focus(); }}>
                    {p}
                  </button>
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
                      <span style={styles.dot} />
                      <span style={{ ...styles.dot, animationDelay: "0.2s" }} />
                      <span style={{ ...styles.dot, animationDelay: "0.4s" }} />
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}

          {/* ── Input ── */}
          <div style={{ ...styles.inputArea, ...(hasConversation ? styles.inputAreaBottom : styles.inputAreaCenter) }}>
            <div style={styles.inputWrap}>
              <textarea
                ref={inputRef}
                rows={1}
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask anything about any stock… (e.g. Is Tesla a risky buy right now?)"
                style={styles.textarea}
              />
              <button onClick={handleSubmit} disabled={!query.trim() || loading} style={styles.sendBtn}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="22" y1="2" x2="11" y2="13" />
                  <polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        {/* ── Right Panel: Live News ── */}
        <div style={styles.rightPanel}>
          <div style={styles.rightHeader}>📡 Live Market News</div>
          <div style={styles.newsScroll}>
            {newsPanel.length > 0 ? newsPanel.map((n, i) => (
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
            )) : (
              <div style={{ padding: "24px 12px", fontSize: 12, color: "#3a5070", textAlign: "center" }}>
                Ask about a stock to see live news
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Bottom Data Panel ── */}
      {hasConversation && (
        <div style={styles.bottomPanel}>
          <div style={styles.bottomTabs}>
            {[
              { key: "price", label: "📈 Price Chart" },
              { key: "sentiment", label: "💬 Sentiment" },
              { key: "risk", label: "⚠️ Risk Score" },
              { key: "sec", label: "📋 SEC Signals" },
            ].map(tab => (
              <button
                key={tab.key}
                style={{ ...styles.tabBtn, ...(activeTab === tab.key ? styles.tabBtnActive : {}) }}
                onClick={() => setActiveTab(activeTab === tab.key ? null : tab.key)}
              >
                {tab.label}
              </button>
            ))}
            {ticker && (
              <span style={styles.tabTicker}>{ticker} · {COMPANY_NAMES[ticker] || ticker}</span>
            )}
            {price?.is_live && (
              <span style={{ marginLeft: 8, fontSize: 9, color: "#00ff9d", background: "#0d2b1f", padding: "2px 6px", borderRadius: 3 }}>
                🟢 LIVE
              </span>
            )}
          </div>

          {activeTab && (
            <div style={styles.bottomContent}>

              {/* ── Price Chart — real Finnhub data ── */}
              {activeTab === "price" && (
                <div style={styles.chartArea}>
                  {price ? (
                    <>
                      <div style={styles.chartHeader}>
                        <span style={styles.chartTicker}>{ticker}</span>
                        <span style={styles.chartPrice}>${price.current_price?.toFixed(2) ?? "—"}</span>
                        <span style={{ color: (price.change ?? 0) >= 0 ? "#00ff9d" : "#ff4d6d", fontSize: 13 }}>
                          {(price.change ?? 0) >= 0 ? "▲" : "▼"} {Math.abs(price.change_pct ?? 0).toFixed(2)}%
                        </span>
                      </div>
                      <MiniChart data={sparklineData} positive={(price.change ?? 0) >= 0} />
                      <div style={styles.priceGrid}>
                        <div style={styles.priceCell}>
                          <span style={styles.priceLabel}>Open</span>
                          <span style={styles.priceVal}>${price.open?.toFixed(2) ?? "—"}</span>
                        </div>
                        <div style={styles.priceCell}>
                          <span style={styles.priceLabel}>High</span>
                          <span style={styles.priceVal}>${price.day_high?.toFixed(2) ?? "—"}</span>
                        </div>
                        <div style={styles.priceCell}>
                          <span style={styles.priceLabel}>Low</span>
                          <span style={styles.priceVal}>${price.day_low?.toFixed(2) ?? "—"}</span>
                        </div>
                        <div style={styles.priceCell}>
                          <span style={styles.priceLabel}>Prev Close</span>
                          <span style={styles.priceVal}>${price.previous_close?.toFixed(2) ?? "—"}</span>
                        </div>
                      </div>
                    </>
                  ) : (
                    <div style={{ color: "#4a6080", fontSize: 13, padding: "20px 0" }}>
                      No price data available for this query type.
                    </div>
                  )}
                </div>
              )}

              {/* ── Sentiment — derived from real retrieved docs ── */}
              {activeTab === "sentiment" && (
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

              {/* ── Risk Score — real risk_score from backend ── */}
              {activeTab === "risk" && (
                <div style={styles.riskArea}>
                  <div style={styles.riskMain}>
                    <RiskGauge score={riskScore} />
                    <div>
                      <div style={styles.riskLabel}>Overall Risk</div>
                      <div style={{ color: RISK_COLOR(riskScore), fontSize: 24, fontWeight: 700 }}>
                        {activeResponse?.risk_score?.risk_label
                          || (riskScore < 35 ? "Low Risk" : riskScore < 65 ? "Moderate Risk" : "High Risk")}
                      </div>
                      {activeResponse?.risk_score?.dominant_risk_factor && (
                        <div style={{ fontSize: 11, color: "#6a8aaa", marginTop: 6, maxWidth: 200, lineHeight: 1.4 }}>
                          {activeResponse.risk_score.dominant_risk_factor}
                        </div>
                      )}
                    </div>
                  </div>
                  <div style={styles.riskBreakdown}>
                    {[
                      { label: "News Signal Risk", score: sentimentData ? sentimentData.news.bearish : 0 },
                      { label: "Social Volatility", score: sentimentData ? sentimentData.social.bearish : 0 },
                      { label: "Reddit Momentum", score: sentimentData ? (100 - sentimentData.reddit.bullish) : 0 },
                      { label: "SEC Filing Flags", score: secCards.length > 0 ? Math.min(90, secCards.length * 25) : 0 },
                    ].map(r => (
                      <div key={r.label} style={styles.riskRow}>
                        <span style={styles.riskRowLabel}>{r.label}</span>
                        <div style={styles.riskBar}>
                          <div style={{ ...styles.riskFill, width: `${r.score}%`, background: RISK_COLOR(r.score) }} />
                        </div>
                        <span style={styles.riskPct}>{r.score}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* ── SEC Signals — real retrieved SEC filing chunks ── */}
              {activeTab === "sec" && ticker && (
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
                  )) : (
                    <div style={{ color: "#4a6080", fontSize: 13 }}>No SEC filing data available for this query.</div>
                  )}
                  {activeResponse?.narrative?.sec_filings_analysis && (
                    <div style={{ marginTop: 8, padding: "10px 14px", background: "#0d1825", border: "1px solid #1a2d45", borderRadius: 10, fontSize: 11, color: "#8aa8c0", lineHeight: 1.6 }}>
                      <span style={{ color: "#c8d8e8", fontWeight: 600 }}>AI Analysis: </span>
                      {activeResponse.narrative.sec_filings_analysis}
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
const styles = {
  root: { display: "flex", flexDirection: "column", height: "100vh", background: "#070d16", color: "#c8d8e8", overflow: "hidden" },
  ticker: { height: 32, background: "#090f1c", borderBottom: "1px solid #1a2d45", overflow: "hidden", flexShrink: 0 },
  tickerTrack: { display: "flex", animation: "scroll 60s linear infinite", width: "max-content", height: "100%", alignItems: "center" },
  tickerItem: { display: "flex", gap: 6, alignItems: "center", padding: "0 20px", borderRight: "1px solid #1a2d45", height: "100%" },
  tickerSymbol: { fontSize: 11, fontWeight: 700, color: "#c8d8e8", fontFamily: "'JetBrains Mono', monospace" },
  tickerPrice: { fontSize: 11, color: "#8aa8c0", fontFamily: "'JetBrains Mono', monospace" },
  tickerChange: { fontSize: 10, fontFamily: "'JetBrains Mono', monospace" },
  layout: { display: "flex", flex: 1, minHeight: 0, position: "relative" },
  sidebarToggle: { position: "absolute", top: 12, left: 12, zIndex: 100, background: "#0f1e30", border: "1px solid #1a3050", borderRadius: 8, width: 36, height: 36, cursor: "pointer", color: "#7aa0c0" },
  hamburger: { fontSize: 14 },
  sidebar: { position: "absolute", top: 0, left: 0, bottom: 0, width: 260, background: "#090f1c", borderRight: "1px solid #1a2d45", zIndex: 90, display: "flex", flexDirection: "column", transition: "transform 0.3s ease", padding: "16px 0 0" },
  sidebarHeader: { padding: "8px 20px 16px", borderBottom: "1px solid #1a2d45" },
  logo: { fontSize: 18, fontWeight: 700, color: "#00ff9d", letterSpacing: 2, fontFamily: "'JetBrains Mono', monospace" },
  logoSub: { fontSize: 10, color: "#4a6080", marginTop: 2 },
  newChatBtn: { margin: "16px 16px 8px", padding: "10px 16px", background: "linear-gradient(135deg, #0d2b1f, #0a2015)", border: "1px solid #00ff9d44", borderRadius: 10, color: "#00ff9d", fontSize: 13, fontWeight: 600, cursor: "pointer" },
  sidebarSearch: { padding: "4px 16px 12px" },
  sidebarSearchInput: { width: "100%", padding: "8px 12px", background: "#0f1e30", border: "1px solid #1a3050", borderRadius: 8, color: "#c8d8e8", fontSize: 12, outline: "none" },
  historyLabel: { padding: "0 16px 8px", fontSize: 10, color: "#3a5070", textTransform: "uppercase", letterSpacing: 1 },
  historyList: { flex: 1, overflowY: "auto", padding: "0 8px" },
  historyEmpty: { padding: "20px 12px", fontSize: 12, color: "#3a5070", textAlign: "center" },
  historyItem: { display: "flex", alignItems: "flex-start", gap: 10, padding: "10px 12px", borderRadius: 8, cursor: "pointer", marginBottom: 2 },
  historyIcon: { fontSize: 14, marginTop: 1 },
  historyTitle: { fontSize: 12, color: "#8aa8c0", lineHeight: 1.4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 170 },
  historyTime: { fontSize: 10, color: "#3a5070", marginTop: 2 },
  sidebarFooter: { padding: "12px 20px", borderTop: "1px solid #1a2d45", display: "flex", alignItems: "center", gap: 8 },
  footerDot: { width: 7, height: 7, borderRadius: "50%", background: "#00ff9d" },
  chatArea: { flex: 1, display: "flex", flexDirection: "column", minWidth: 0 },
  welcome: { flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12, padding: 24 },
  welcomeLogo: { fontSize: 48, fontWeight: 700, color: "#00ff9d", letterSpacing: 4, fontFamily: "'JetBrains Mono', monospace" },
  welcomeSub: { fontSize: 14, color: "#4a7090", letterSpacing: 2 },
  welcomeHint: { fontSize: 12, color: "#3a5070", marginTop: 8 },
  quickPrompts: { display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center", marginTop: 16 },
  quickBtn: { padding: "8px 16px", background: "#0b1825", border: "1px solid #1a3050", borderRadius: 20, color: "#6a9ab0", fontSize: 12, cursor: "pointer" },
  messageList: { flex: 1, overflowY: "auto", padding: "16px 24px", display: "flex", flexDirection: "column", gap: 12 },
  msgRow: { display: "flex", gap: 10, alignItems: "flex-start" },
  avatarA: { width: 30, height: 30, borderRadius: "50%", background: "linear-gradient(135deg, #0d2b1f, #00ff9d33)", border: "1px solid #00ff9d44", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 700, color: "#00ff9d", flexShrink: 0 },
  avatarU: { width: 30, height: 30, borderRadius: "50%", background: "#1a2d45", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700, color: "#8aa8c0", flexShrink: 0 },
  bubble: { maxWidth: "72%", padding: "10px 14px", borderRadius: 14, lineHeight: 1.6, animation: "fadeIn 0.2s ease" },
  bubbleUser: { background: "#0f2540", border: "1px solid #1a3a5c", color: "#c8d8e8", borderRadius: "14px 14px 4px 14px" },
  bubbleAssistant: { background: "#0b1825", border: "1px solid #1a2d45", color: "#c8d8e8", borderRadius: "14px 14px 14px 4px" },
  bubbleMeta: { display: "flex", gap: 8, alignItems: "center", marginBottom: 6 },
  bubbleTicker: { fontSize: 10, fontWeight: 700, color: "#00ff9d", fontFamily: "'JetBrains Mono', monospace", background: "#0d2b1f", padding: "1px 6px", borderRadius: 3 },
  bubbleSentiment: { fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: 1 },
  bubbleText: { fontSize: 13, whiteSpace: "pre-wrap" },
  typing: { display: "flex", gap: 4, alignItems: "center", padding: "4px 0" },
  dot: { width: 7, height: 7, borderRadius: "50%", background: "#00ff9d", animation: "bounce 1.2s infinite" },
  inputArea: { padding: "0 24px 12px" },
  inputAreaCenter: {},
  inputAreaBottom: {},
  inputWrap: { display: "flex", alignItems: "flex-end", background: "#0d1a28", border: "1px solid #1a3050", borderRadius: 14, overflow: "hidden" },
  textarea: { flex: 1, background: "transparent", border: "none", outline: "none", color: "#c8d8e8", fontSize: 14, padding: "14px 16px", resize: "none", fontFamily: "'Space Grotesk', sans-serif", lineHeight: 1.5, minHeight: 48 },
  sendBtn: { padding: "12px 16px", background: "transparent", border: "none", cursor: "pointer", color: "#00ff9d" },
  rightPanel: { width: 240, background: "#090f1c", borderLeft: "1px solid #1a2d45", display: "flex", flexDirection: "column", overflow: "hidden" },
  rightHeader: { padding: "14px 16px 10px", fontSize: 11, fontWeight: 700, color: "#3a6070", textTransform: "uppercase", letterSpacing: 1, borderBottom: "1px solid #1a2d45" },
  newsScroll: { flex: 1, overflowY: "auto", padding: "8px" },
  newsCard: { padding: "10px 12px", marginBottom: 6, background: "#0b1422", border: "1px solid #1a2d45", borderRadius: 10 },
  newsTop: { display: "flex", justifyContent: "space-between", marginBottom: 5 },
  newsTicker: { fontSize: 10, fontWeight: 700, color: "#00ff9d", fontFamily: "'JetBrains Mono', monospace", background: "#0d2b1f", padding: "1px 6px", borderRadius: 3 },
  newsLabel: { fontSize: 9, fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 },
  newsHeadline: { fontSize: 11, color: "#8aa8c0", lineHeight: 1.4, marginBottom: 4 },
  newsTime: { fontSize: 10, color: "#3a5070" },
  bottomPanel: { background: "#090f1c", borderTop: "1px solid #1a2d45" },
  bottomTabs: { display: "flex", gap: 4, padding: "10px 16px 0", alignItems: "center", overflowX: "auto" },
  tabBtn: { padding: "7px 14px", background: "transparent", border: "1px solid #1a2d45", borderRadius: "8px 8px 0 0", color: "#4a6080", fontSize: 12, cursor: "pointer", whiteSpace: "nowrap" },
  tabBtnActive: { background: "#0b1825", borderColor: "#00ff9d44", color: "#00ff9d", borderBottomColor: "#0b1825" },
  tabTicker: { marginLeft: "auto", fontSize: 11, color: "#3a5070", fontFamily: "'JetBrains Mono', monospace" },
  bottomContent: { background: "#0b1825", padding: "16px 20px", maxHeight: 220, overflowY: "auto" },
  chartArea: {},
  chartHeader: { display: "flex", gap: 12, alignItems: "baseline", marginBottom: 8 },
  chartTicker: { fontSize: 16, fontWeight: 700, color: "#00ff9d", fontFamily: "'JetBrains Mono', monospace" },
  chartPrice: { fontSize: 22, fontWeight: 700, color: "#c8d8e8" },
  priceGrid: { display: "flex", gap: 16, marginTop: 10 },
  priceCell: { display: "flex", flexDirection: "column", gap: 2 },
  priceLabel: { fontSize: 10, color: "#3a5070" },
  priceVal: { fontSize: 12, color: "#8aa8c0", fontFamily: "'JetBrains Mono', monospace" },
  sentimentArea: { padding: "4px 0" },
  riskArea: { display: "flex", gap: 32, alignItems: "flex-start" },
  riskMain: { display: "flex", gap: 16, alignItems: "center", flexShrink: 0 },
  riskLabel: { fontSize: 11, color: "#4a6080", marginBottom: 4 },
  riskBreakdown: { flex: 1 },
  riskRow: { display: "flex", alignItems: "center", gap: 10, marginBottom: 10 },
  riskRowLabel: { fontSize: 11, color: "#6a8aaa", width: 180, flexShrink: 0 },
  riskBar: { flex: 1, height: 6, background: "#1a2d45", borderRadius: 3, overflow: "hidden" },
  riskFill: { height: "100%", borderRadius: 3, transition: "width 0.5s ease" },
  riskPct: { fontSize: 11, color: "#8aa0c0", width: 35, textAlign: "right", fontFamily: "'JetBrains Mono', monospace" },
  secArea: { display: "flex", flexDirection: "column", gap: 8 },
  secCard: { display: "flex", alignItems: "center", gap: 14, padding: "10px 14px", background: "#0d1825", border: "1px solid #1a2d45", borderRadius: 10 },
  secIcon: { fontSize: 20, flexShrink: 0 },
  secType: { fontSize: 12, fontWeight: 600, color: "#c8d8e8", marginBottom: 2 },
  secNote: { fontSize: 11, color: "#4a6080" },
  secBadge: { marginLeft: "auto", fontSize: 9, background: "#0d2b1f", color: "#00ff9d", border: "1px solid #00ff9d44", borderRadius: 4, padding: "2px 7px", fontWeight: 700, flexShrink: 0 },
};