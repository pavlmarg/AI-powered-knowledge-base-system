import { useState, useEffect, useRef, useCallback } from "react";

// ── Constants ─────────────────────────────────────────────────────────────────
const API_BASE = "http://localhost:8080/api";

const SEED_TICKERS = ["AAPL", "BA", "GME", "JPM", "NEE", "NVDA", "PFE", "PLTR", "TSLA", "XOM"];

const COMPANY_NAMES = {
  AAPL: "Apple Inc.", BA: "Boeing Co.", GME: "GameStop Corp.",
  JPM: "JPMorgan Chase", NEE: "NextEra Energy", NVDA: "NVIDIA Corp.",
  PFE: "Pfizer Inc.", PLTR: "Palantir Technologies", TSLA: "Tesla Inc.", XOM: "ExxonMobil",
};

const MOCK_PRICES = {
  AAPL: { price: 227.50, change: 1.70, pct: 0.75 },
  BA:   { price: 175.20, change: -2.30, pct: -1.30 },
  GME:  { price: 26.80,  change: 1.70, pct: 6.77 },
  JPM:  { price: 201.25, change: 3.20, pct: 1.62 },
  NEE:  { price: 66.27,  change: 0.32, pct: 0.49 },
  NVDA: { price: 874.87, change: 5.92, pct: 0.68 },
  PFE:  { price: 26.88,  change: -0.01, pct: -0.04 },
  PLTR: { price: 24.89,  change: 2.95, pct: 13.34 },
  TSLA: { price: 256.63, change: 13.92, pct: 5.74 },
  XOM:  { price: 112.26, change: 0.48, pct: 0.43 },
};

const SAMPLE_NEWS = [
  { ticker: "NVDA", headline: "NVIDIA reveals Rubin AI chip: 40% more energy efficient than Blackwell", time: "2h ago", sentiment: "bullish" },
  { ticker: "TSLA", headline: "Tesla Optimus production milestone reached ahead of schedule", time: "4h ago", sentiment: "bullish" },
  { ticker: "GME", headline: "GameStop holds $4.2B cash — Reddit community bullish on turnaround", time: "5h ago", sentiment: "bullish" },
  { ticker: "PFE", headline: "Pfizer RSV vaccine trails GSK by 20% — M&A pressure mounts", time: "6h ago", sentiment: "bearish" },
  { ticker: "PLTR", headline: "Palantir secures new DoD contract worth $500M — AIP expansion", time: "7h ago", sentiment: "bullish" },
  { ticker: "AAPL", headline: "iPhone 17 supercycle confirmed by supply chain checks", time: "8h ago", sentiment: "bullish" },
  { ticker: "BA", headline: "Boeing 737 MAX deliveries resume after 6-week FAA review", time: "9h ago", sentiment: "neutral" },
  { ticker: "XOM", headline: "ExxonMobil cuts capex forecast amid crude price uncertainty", time: "10h ago", sentiment: "bearish" },
  { ticker: "JPM", headline: "JPMorgan beats Q1 estimates — net income up 12% YoY", time: "11h ago", sentiment: "bullish" },
  { ticker: "NEE", headline: "NextEra boosts dividend 10%, secures EU green energy subsidies", time: "12h ago", sentiment: "bullish" },
];

const SENTIMENT_COLORS = { bullish: "#00ff9d", bearish: "#ff4d6d", neutral: "#a0aec0" };

// ── Utility ───────────────────────────────────────────────────────────────────
function generateSparkline(ticker) {
  const base = MOCK_PRICES[ticker]?.price || 100;
  return Array.from({ length: 20 }, (_, i) =>
    base + (Math.random() - 0.48) * base * 0.03 * (i + 1)
  );
}

function SparklineSVG({ data, positive }) {
  const min = Math.min(...data), max = Math.max(...data);
  const range = max - min || 1;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * 56;
    const y = 20 - ((v - min) / range) * 18;
    return `${x},${y}`;
  }).join(" ");
  const color = positive ? "#00ff9d" : "#ff4d6d";
  return (
    <svg width="56" height="22" viewBox="0 0 56 22" style={{ display: "block" }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// ── Risk Gauge ────────────────────────────────────────────────────────────────
function RiskGauge({ score }) {
  const color = score < 35 ? "#00ff9d" : score < 65 ? "#f6ad55" : "#ff4d6d";
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

// ── Main App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [chatHistory, setChatHistory] = useState([]);
  const [activeTab, setActiveTab] = useState(null); // 'price' | 'sentiment' | 'risk' | 'sec'
  const [activeResponse, setActiveResponse] = useState(null);
  const [tickerSparks] = useState(() =>
    Object.fromEntries(SEED_TICKERS.map(t => [t, generateSparkline(t)]))
  );
  const [newsIdx, setNewsIdx] = useState(0);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Rotate news
  useEffect(() => {
    const timer = setInterval(() => setNewsIdx(i => (i + 2) % SAMPLE_NEWS.length), 8000);
    return () => clearInterval(timer);
  }, []);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const visibleNews = [
    SAMPLE_NEWS[newsIdx % SAMPLE_NEWS.length],
    SAMPLE_NEWS[(newsIdx + 1) % SAMPLE_NEWS.length],
    SAMPLE_NEWS[(newsIdx + 2) % SAMPLE_NEWS.length],
  ];

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
      const data = await res.json();

      const newSession = data.session_id || sessionId || crypto.randomUUID();
      if (!sessionId) {
        setSessionId(newSession);
        setChatHistory(prev => [
          { id: newSession, title: userMsg.slice(0, 40), ts: Date.now() },
          ...prev,
        ]);
      }

      setActiveResponse(data);
      setMessages(prev => [
        ...prev,
        {
          role: "assistant",
          content: data.narrative?.analysis || data.narrative?.answer || "Analysis complete.",
          ticker: data.ticker,
          riskScore: data.risk_score?.risk_percentage,
          sentiment: data.narrative?.overall_sentiment,
          session: newSession,
        },
      ]);
      setActiveTab("price");
    } catch (err) {
      // Fallback mock response for demo
      const mockTicker = SEED_TICKERS.find(t => userMsg.toUpperCase().includes(t)) || "NVDA";
      const mockRisk = Math.floor(Math.random() * 60) + 20;
      setActiveResponse({
        ticker: mockTicker,
        risk_score: { risk_percentage: mockRisk },
        narrative: {
          overall_sentiment: mockRisk < 45 ? "BULLISH" : mockRisk < 65 ? "NEUTRAL" : "BEARISH",
          analysis: `Based on multi-layer analysis of ${mockTicker}, the stock shows ${mockRisk < 45 ? "strong bullish" : mockRisk < 65 ? "mixed" : "concerning bearish"} signals across SEC filings, social sentiment, and live price data. Reddit buzz remains elevated at 2,100 mentions this week. News flow is predominantly ${mockRisk < 50 ? "positive" : "negative"} with ${Math.floor(Math.random() * 8) + 3} relevant articles flagged. Risk score of ${mockRisk}% reflects ${mockRisk < 40 ? "aligned" : "contradictory"} signals across data layers.`,
        },
      });
      setMessages(prev => [
        ...prev,
        {
          role: "assistant",
          content: `Based on multi-layer analysis, the stock shows signals across SEC filings, social sentiment, and live price data. Risk score: ${mockRisk}%.`,
          ticker: mockTicker,
          riskScore: mockRisk,
          sentiment: mockRisk < 45 ? "BULLISH" : "NEUTRAL",
        },
      ]);
      setActiveTab("price");
    } finally {
      setLoading(false);
    }
  }, [query, loading, sessionId]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmit(); }
  };

  const startNewChat = () => {
    setMessages([]);
    setSessionId(null);
    setActiveResponse(null);
    setActiveTab(null);
    setSidebarOpen(false);
    inputRef.current?.focus();
  };

  const ticker = activeResponse?.ticker;
  const riskScore = activeResponse?.risk_score?.risk_percentage || 0;
  const priceData = ticker ? MOCK_PRICES[ticker] : null;
  const hasConversation = messages.length > 0;

  return (
    <div style={styles.root}>
      {/* ── Ticker Carousel ── */}
      <div style={styles.ticker}>
        <div style={styles.tickerTrack}>
          {[...SEED_TICKERS, ...SEED_TICKERS].map((t, i) => {
            const d = MOCK_PRICES[t];
            const pos = d.change >= 0;
            return (
              <div key={i} style={styles.tickerItem}>
                <span style={styles.tickerSymbol}>{t}</span>
                <span style={styles.tickerPrice}>${d.price.toFixed(2)}</span>
                <span style={{ ...styles.tickerChange, color: pos ? "#00ff9d" : "#ff4d6d" }}>
                  {pos ? "▲" : "▼"} {Math.abs(d.pct).toFixed(2)}%
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Layout ── */}
      <div style={styles.layout}>
        {/* Sidebar Toggle */}
        <button style={styles.sidebarToggle} onClick={() => setSidebarOpen(o => !o)} title="Menu">
          <span style={styles.hamburger}>{sidebarOpen ? "✕" : "☰"}</span>
        </button>

        {/* ── Left Sidebar ── */}
        <div style={{ ...styles.sidebar, transform: sidebarOpen ? "translateX(0)" : "translateX(-100%)" }}>
          <div style={styles.sidebarHeader}>
            <div style={styles.logo}>ΑΛΕΧIS</div>
            <div style={styles.logoSub}>Financial Intelligence</div>
          </div>

          <button style={styles.newChatBtn} onClick={startNewChat}>
            <span style={{ fontSize: 16, marginRight: 8 }}>+</span> New Chat
          </button>

          <div style={styles.sidebarSearch}>
            <input placeholder="Search chats…" style={styles.sidebarSearchInput} />
          </div>

          <div style={styles.historyLabel}>Recent Chats</div>
          <div style={styles.historyList}>
            {chatHistory.length === 0 ? (
              <div style={styles.historyEmpty}>No chats yet</div>
            ) : chatHistory.map(ch => (
              <div key={ch.id} style={styles.historyItem} onClick={() => setSidebarOpen(false)}>
                <div style={styles.historyIcon}>💬</div>
                <div style={{ minWidth: 0 }}>
                  <div style={styles.historyTitle}>{ch.title}</div>
                  <div style={styles.historyTime}>{new Date(ch.ts).toLocaleDateString()}</div>
                </div>
              </div>
            ))}
          </div>

          <div style={styles.sidebarFooter}>
            <div style={styles.footerDot} />
            <span style={{ fontSize: 11, color: "#4a6080" }}>Backend connected</span>
          </div>
        </div>

        {/* ── Backdrop ── */}
        {sidebarOpen && <div style={styles.backdrop} onClick={() => setSidebarOpen(false)} />}

        {/* ── Main Chat Area ── */}
        <div style={styles.main}>
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
                  {msg.role === "assistant" && (
                    <div style={styles.avatarA}>Α</div>
                  )}
                  <div style={{
                    ...styles.bubble,
                    ...(msg.role === "user" ? styles.bubbleUser : styles.bubbleAssistant),
                  }}>
                    {msg.role === "assistant" && msg.ticker && (
                      <div style={styles.bubbleMeta}>
                        <span style={styles.bubbleTicker}>{msg.ticker}</span>
                        {msg.sentiment && (
                          <span style={{ ...styles.bubbleSentiment, color: SENTIMENT_COLORS[msg.sentiment?.toLowerCase()] || "#a0aec0" }}>
                            {msg.sentiment}
                          </span>
                        )}
                      </div>
                    )}
                    <div style={styles.bubbleText}>{msg.content}</div>
                  </div>
                  {msg.role === "user" && (
                    <div style={styles.avatarU}>U</div>
                  )}
                </div>
              ))}
              {loading && (
                <div style={{ ...styles.msgRow, justifyContent: "flex-start" }}>
                  <div style={styles.avatarA}>Α</div>
                  <div style={{ ...styles.bubble, ...styles.bubbleAssistant }}>
                    <div style={styles.typing}>
                      <span style={styles.dot} /> <span style={{ ...styles.dot, animationDelay: "0.2s" }} /> <span style={{ ...styles.dot, animationDelay: "0.4s" }} />
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}

          {/* ── Input Area ── */}
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
            {SAMPLE_NEWS.map((n, i) => (
              <div key={i} style={styles.newsCard}>
                <div style={styles.newsTop}>
                  <span style={styles.newsTicker}>{n.ticker}</span>
                  <span style={{ ...styles.newsLabel, color: SENTIMENT_COLORS[n.sentiment] }}>
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
            {ticker && <span style={styles.tabTicker}>{ticker} · {COMPANY_NAMES[ticker]}</span>}
          </div>

          {activeTab && (
            <div style={styles.bottomContent}>
              {/* Price Chart */}
              {activeTab === "price" && priceData && (
                <div style={styles.chartArea}>
                  <div style={styles.chartHeader}>
                    <span style={styles.chartTicker}>{ticker}</span>
                    <span style={styles.chartPrice}>${priceData.price.toFixed(2)}</span>
                    <span style={{ color: priceData.change >= 0 ? "#00ff9d" : "#ff4d6d", fontSize: 13 }}>
                      {priceData.change >= 0 ? "▲" : "▼"} {Math.abs(priceData.pct).toFixed(2)}%
                    </span>
                  </div>
                  <MiniChart data={tickerSparks[ticker] || []} positive={priceData.change >= 0} />
                  <div style={styles.priceGrid}>
                    <div style={styles.priceCell}><span style={styles.priceLabel}>Open</span><span style={styles.priceVal}>${(priceData.price * 0.998).toFixed(2)}</span></div>
                    <div style={styles.priceCell}><span style={styles.priceLabel}>High</span><span style={styles.priceVal}>${(priceData.price * 1.012).toFixed(2)}</span></div>
                    <div style={styles.priceCell}><span style={styles.priceLabel}>Low</span><span style={styles.priceVal}>${(priceData.price * 0.986).toFixed(2)}</span></div>
                    <div style={styles.priceCell}><span style={styles.priceLabel}>Prev Close</span><span style={styles.priceVal}>${(priceData.price - priceData.change).toFixed(2)}</span></div>
                  </div>
                </div>
              )}

              {/* Sentiment */}
              {activeTab === "sentiment" && (
                <div style={styles.sentimentArea}>
                  <SentimentBar label="News Sentiment" bullish={62} bearish={21} neutral={17} />
                  <SentimentBar label="Reddit / Social" bullish={78} bearish={10} neutral={12} />
                  <SentimentBar label="Twitter / X" bullish={55} bearish={30} neutral={15} />
                  <SentimentBar label="SEC vs Social Agreement" bullish={45} bearish={40} neutral={15} />
                </div>
              )}

              {/* Risk Score */}
              {activeTab === "risk" && (
                <div style={styles.riskArea}>
                  <div style={styles.riskMain}>
                    <RiskGauge score={riskScore} />
                    <div>
                      <div style={styles.riskLabel}>Overall Risk</div>
                      <div style={{ color: riskScore < 35 ? "#00ff9d" : riskScore < 65 ? "#f6ad55" : "#ff4d6d", fontSize: 28, fontWeight: 700 }}>
                        {riskScore < 35 ? "LOW" : riskScore < 65 ? "MEDIUM" : "HIGH"}
                      </div>
                    </div>
                  </div>
                  <div style={styles.riskBreakdown}>
                    {[
                      { label: "SEC vs Social contradiction", score: Math.min(riskScore + 10, 100) },
                      { label: "Reddit vs News divergence", score: Math.max(riskScore - 12, 0) },
                      { label: "Price vs SEC signal", score: Math.min(riskScore + 5, 100) },
                      { label: "Insider activity signal", score: Math.max(riskScore - 8, 0) },
                    ].map(r => (
                      <div key={r.label} style={styles.riskRow}>
                        <span style={styles.riskRowLabel}>{r.label}</span>
                        <div style={styles.riskBar}>
                          <div style={{ ...styles.riskFill, width: `${r.score}%`, background: r.score < 35 ? "#00ff9d" : r.score < 65 ? "#f6ad55" : "#ff4d6d" }} />
                        </div>
                        <span style={styles.riskPct}>{r.score}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* SEC Signals */}
              {activeTab === "sec" && ticker && (
                <div style={styles.secArea}>
                  {[
                    { type: "10-K", label: "Annual Report", icon: "📄", note: `${ticker} annual filing reviewed — key disclosures flagged` },
                    { type: "10-Q", label: "Quarterly Report", icon: "📊", note: `Q3 2025 quarterly filing — revenue & EPS trends extracted` },
                    { type: "8-K", label: "Material Events", icon: "⚡", note: `3 material events detected in last 90 days` },
                  ].map(s => (
                    <div key={s.type} style={styles.secCard}>
                      <div style={styles.secIcon}>{s.icon}</div>
                      <div>
                        <div style={styles.secType}>{s.type} — {s.label}</div>
                        <div style={styles.secNote}>{s.note}</div>
                      </div>
                      <div style={styles.secBadge}>Live</div>
                    </div>
                  ))}
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
        ::-webkit-scrollbar { width: 4px; } ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #1e3050; border-radius: 2px; }
        @keyframes scroll { 0% { transform: translateX(0); } 100% { transform: translateX(-50%); } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
        @keyframes bounce { 0%, 80%, 100% { transform: translateY(0); } 40% { transform: translateY(-6px); } }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
        @keyframes glow { 0%, 100% { box-shadow: 0 0 8px #00ff9d33; } 50% { box-shadow: 0 0 20px #00ff9d66; } }
      `}</style>
    </div>
  );
}

// ── Mini Chart Component ─────────────────────────────────────────────────────
function MiniChart({ data, positive }) {
  if (!data.length) return null;
  const min = Math.min(...data), max = Math.max(...data);
  const range = max - min || 1;
  const W = 400, H = 80;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * W;
    const y = H - ((v - min) / range) * (H - 8) - 4;
    return `${x},${y}`;
  }).join(" ");
  const color = positive ? "#00ff9d" : "#ff4d6d";
  const fillPts = `0,${H} ${pts} ${W},${H}`;
  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ height: 80, display: "block" }}>
      <defs>
        <linearGradient id="chartGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={fillPts} fill="url(#chartGrad)" />
      <polyline points={pts} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// ── Sentiment Bar ─────────────────────────────────────────────────────────────
function SentimentBar({ label, bullish, bearish, neutral }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
        <span style={{ fontSize: 11, color: "#6a8aaa" }}>{label}</span>
        <span style={{ fontSize: 11, color: "#00ff9d" }}>{bullish}% bullish</span>
      </div>
      <div style={{ display: "flex", height: 6, borderRadius: 3, overflow: "hidden", gap: 1 }}>
        <div style={{ width: `${bullish}%`, background: "#00ff9d", borderRadius: "3px 0 0 3px" }} />
        <div style={{ width: `${neutral}%`, background: "#a0aec0" }} />
        <div style={{ width: `${bearish}%`, background: "#ff4d6d", borderRadius: "0 3px 3px 0" }} />
      </div>
    </div>
  );
}

// ── Styles ─────────────────────────────────────────────────────────────────────
const styles = {
  root: { display: "flex", flexDirection: "column", height: "100vh", background: "#070d16", color: "#c8d8e8", fontFamily: "'Space Grotesk', sans-serif", overflow: "hidden" },
  ticker: { height: 32, background: "#0b1422", borderBottom: "1px solid #1a2d45", overflow: "hidden", display: "flex", alignItems: "center" },
  tickerTrack: { display: "flex", animation: "scroll 40s linear infinite", whiteSpace: "nowrap" },
  tickerItem: { display: "flex", alignItems: "center", gap: 6, padding: "0 20px", borderRight: "1px solid #1a2d45" },
  tickerSymbol: { fontSize: 11, fontWeight: 700, color: "#00ff9d", fontFamily: "'JetBrains Mono', monospace" },
  tickerPrice: { fontSize: 11, color: "#c8d8e8", fontFamily: "'JetBrains Mono', monospace" },
  tickerChange: { fontSize: 10, fontFamily: "'JetBrains Mono', monospace" },
  layout: { display: "flex", flex: 1, minHeight: 0, position: "relative" },
  sidebarToggle: { position: "absolute", top: 12, left: 12, zIndex: 100, background: "#0f1e30", border: "1px solid #1a3050", borderRadius: 8, width: 36, height: 36, cursor: "pointer", color: "#7aa0c0" },
  hamburger: { fontSize: 14 },
  sidebar: { position: "absolute", top: 0, left: 0, bottom: 0, width: 260, background: "#090f1c", borderRight: "1px solid #1a2d45", zIndex: 90, display: "flex", flexDirection: "column", transition: "transform 0.3s ease", padding: "16px 0 0" },
  sidebarHeader: { padding: "8px 20px 16px", borderBottom: "1px solid #1a2d45" },
  logo: { fontSize: 18, fontWeight: 700, color: "#00ff9d", letterSpacing: 2, fontFamily: "'JetBrains Mono', monospace" },
  logoSub: { fontSize: 10, color: "#4a6080", marginTop: 2 },
  newChatBtn: { margin: "16px 16px 8px", padding: "10px 16px", background: "linear-gradient(135deg, #0d2b1f, #0a2015)", border: "1px solid #00ff9d44", borderRadius: 10, color: "#00ff9d", fontSize: 13, fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", transition: "all 0.2s" },
  sidebarSearch: { padding: "4px 16px 12px" },
  sidebarSearchInput: { width: "100%", padding: "8px 12px", background: "#0f1e30", border: "1px solid #1a3050", borderRadius: 8, color: "#c8d8e8", fontSize: 12, outline: "none" },
  historyLabel: { padding: "0 16px 8px", fontSize: 10, color: "#3a5070", textTransform: "uppercase", letterSpacing: 1 },
  historyList: { flex: 1, overflowY: "auto", padding: "0 8px" },
  historyEmpty: { padding: "20px 12px", fontSize: 12, color: "#3a5070", textAlign: "center" },
  historyItem: { display: "flex", alignItems: "flex-start", gap: 10, padding: "10px 12px", borderRadius: 8, cursor: "pointer", marginBottom: 2, transition: "background 0.15s" },
  historyIcon: { fontSize: 14, marginTop: 1 },
  historyTitle: { fontSize: 12, color: "#8aa8c0", lineHeight: 1.4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 170 },
  historyTime: { fontSize: 10, color: "#3a5070", marginTop: 2 },
  sidebarFooter: { padding: "12px 20px", borderTop: "1px solid #1a2d45", display: "flex", alignItems: "center", gap: 8 },
  footerDot: { width: 7, height: 7, borderRadius: "50%", background: "#00ff9d", animation: "pulse 2s infinite" },
  backdrop: { position: "absolute", inset: 0, zIndex: 85, background: "rgba(0,0,0,0.5)" },
  main: { flex: 1, display: "flex", flexDirection: "column", minWidth: 0, position: "relative" },
  welcome: { flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "40px 24px", animation: "fadeIn 0.6s ease" },
  welcomeLogo: { fontSize: 56, fontWeight: 700, color: "#00ff9d", letterSpacing: 4, fontFamily: "'JetBrains Mono', monospace", textShadow: "0 0 40px #00ff9d55" },
  welcomeSub: { fontSize: 14, color: "#4a6080", marginTop: 8, letterSpacing: 2 },
  welcomeHint: { fontSize: 13, color: "#3a5070", marginTop: 24, marginBottom: 20 },
  quickPrompts: { display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center", maxWidth: 560 },
  quickBtn: { padding: "8px 16px", background: "#0f1e30", border: "1px solid #1a3050", borderRadius: 20, color: "#7aa0c0", fontSize: 12, cursor: "pointer", transition: "all 0.2s" },
  messageList: { flex: 1, overflowY: "auto", padding: "16px 24px 8px" },
  msgRow: { display: "flex", alignItems: "flex-start", gap: 10, marginBottom: 16, animation: "fadeIn 0.3s ease" },
  avatarA: { width: 32, height: 32, borderRadius: 10, background: "linear-gradient(135deg, #0d2b1f, #1a4035)", border: "1px solid #00ff9d44", color: "#00ff9d", fontSize: 13, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, fontFamily: "'JetBrains Mono', monospace" },
  avatarU: { width: 32, height: 32, borderRadius: 10, background: "#1a2d45", color: "#7aa0c0", fontSize: 12, fontWeight: 600, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 },
  bubble: { maxWidth: "70%", borderRadius: 12, padding: "10px 14px", lineHeight: 1.6 },
  bubbleUser: { background: "#111e30", border: "1px solid #1a3050", color: "#c8d8e8", fontSize: 13, borderTopRightRadius: 4 },
  bubbleAssistant: { background: "#0b1825", border: "1px solid #1a3050", color: "#c8d8e8", fontSize: 13, borderTopLeftRadius: 4 },
  bubbleMeta: { display: "flex", gap: 8, marginBottom: 6, alignItems: "center" },
  bubbleTicker: { fontSize: 11, fontWeight: 700, color: "#00ff9d", fontFamily: "'JetBrains Mono', monospace", background: "#0d2b1f", padding: "2px 8px", borderRadius: 4 },
  bubbleSentiment: { fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: 1 },
  bubbleText: { fontSize: 13 },
  typing: { display: "flex", gap: 4, alignItems: "center", padding: "4px 0" },
  dot: { width: 7, height: 7, borderRadius: "50%", background: "#00ff9d", animation: "bounce 1.2s infinite" },
  inputArea: { padding: "0 24px 12px" },
  inputAreaCenter: {},
  inputAreaBottom: {},
  inputWrap: { display: "flex", alignItems: "flex-end", background: "#0d1a28", border: "1px solid #1a3050", borderRadius: 14, overflow: "hidden", gap: 0, boxShadow: "0 0 0 0px transparent", transition: "box-shadow 0.2s" },
  textarea: { flex: 1, background: "transparent", border: "none", outline: "none", color: "#c8d8e8", fontSize: 14, padding: "14px 16px", resize: "none", fontFamily: "'Space Grotesk', sans-serif", lineHeight: 1.5, minHeight: 48 },
  sendBtn: { padding: "12px 16px", background: "transparent", border: "none", cursor: "pointer", color: "#00ff9d", display: "flex", alignItems: "center", justifyContent: "center", transition: "opacity 0.2s", opacity: 1 },
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
  tabBtn: { padding: "7px 14px", background: "transparent", border: "1px solid #1a2d45", borderRadius: "8px 8px 0 0", color: "#4a6080", fontSize: 12, cursor: "pointer", whiteSpace: "nowrap", transition: "all 0.15s" },
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
  riskRowLabel: { fontSize: 11, color: "#6a8aaa", width: 220, flexShrink: 0 },
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
