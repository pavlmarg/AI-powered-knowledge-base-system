"""
retrieval/finnhub_tool.py
-------------------------
Layer 4 — Live market data fetcher using the official Finnhub REST API.

Finnhub replaces yfinance as our live data source because:
  - It is an official REST API (not a scraper) — reliable and stable
  - Free tier allows 60 calls/minute — more than enough for our use case
  - Returns real-time quote data with clean JSON responses
  - No rate-limiting issues like Yahoo Finance in 2025

Architecture:
  Tier 1 — Attempts a real Finnhub API call
  Tier 2 — Falls back to realistic mock data if the call fails for any reason
             (network issue, market closed, key misconfiguration, etc.)

The 'is_live' key in every response tells the caller and the frontend
whether the data is real-time or from the mock fallback — full transparency.

Finnhub quote endpoint returns:
  c  — current price
  d  — change
  dp — percent change
  h  — high of the day
  l  — low of the day
  o  — open price of the day
  pc — previous close price
  t  — timestamp
"""

import finnhub
from core.config import FINNHUB_API_KEY, KNOWN_TICKERS

# ── Finnhub client (singleton) ────────────────────────────────────────────────
_client: finnhub.Client | None = None


def _get_client() -> finnhub.Client:
    """Return the shared Finnhub client, creating it once."""
    global _client
    if _client is None:
        _client = finnhub.Client(api_key=FINNHUB_API_KEY)
    return _client


# ── Realistic fallback mock data for our 10 tickers ───────────────────────────
# Used ONLY when the live Finnhub call fails
# Values reflect approximate market prices as of March 2026
MOCK_PRICES: dict[str, dict] = {
    "AAPL": {
        "current_price" : 227.50,
        "previous_close": 225.80,
        "change"        : 1.70,
        "change_pct"    : 0.75,
        "day_high"      : 229.10,
        "day_low"       : 225.20,
        "open"          : 226.00,
        "market_cap"    : "3.42T",
    },
    "NVDA": {
        "current_price" : 875.40,
        "previous_close": 862.10,
        "change"        : 13.30,
        "change_pct"    : 1.54,
        "day_high"      : 881.00,
        "day_low"       : 860.50,
        "open"          : 865.00,
        "market_cap"    : "2.15T",
    },
    "TSLA": {
        "current_price" : 248.20,
        "previous_close": 252.40,
        "change"        : -4.20,
        "change_pct"    : -1.66,
        "day_high"      : 253.80,
        "day_low"       : 246.10,
        "open"          : 252.00,
        "market_cap"    : "791.00B",
    },
    "GME": {
        "current_price" : 26.80,
        "previous_close": 25.10,
        "change"        : 1.70,
        "change_pct"    : 6.77,
        "day_high"      : 27.50,
        "day_low"       : 24.90,
        "open"          : 25.20,
        "market_cap"    : "11.60B",
    },
    "PLTR": {
        "current_price" : 82.50,
        "previous_close": 80.20,
        "change"        : 2.30,
        "change_pct"    : 2.87,
        "day_high"      : 83.40,
        "day_low"       : 79.80,
        "open"          : 80.50,
        "market_cap"    : "176.00B",
    },
    "JPM": {
        "current_price" : 238.60,
        "previous_close": 236.90,
        "change"        : 1.70,
        "change_pct"    : 0.72,
        "day_high"      : 239.80,
        "day_low"       : 236.20,
        "open"          : 237.10,
        "market_cap"    : "686.00B",
    },
    "BA": {
        "current_price" : 172.30,
        "previous_close": 170.50,
        "change"        : 1.80,
        "change_pct"    : 1.06,
        "day_high"      : 173.50,
        "day_low"       : 169.80,
        "open"          : 170.80,
        "market_cap"    : "130.00B",
    },
    "PFE": {
        "current_price" : 24.10,
        "previous_close": 23.80,
        "change"        : 0.30,
        "change_pct"    : 1.26,
        "day_high"      : 24.40,
        "day_low"       : 23.70,
        "open"          : 23.90,
        "market_cap"    : "136.00B",
    },
    "NEE": {
        "current_price" : 71.20,
        "previous_close": 70.40,
        "change"        : 0.80,
        "change_pct"    : 1.14,
        "day_high"      : 71.80,
        "day_low"       : 70.10,
        "open"          : 70.60,
        "market_cap"    : "145.00B",
    },
    "XOM": {
        "current_price" : 108.50,
        "previous_close": 107.20,
        "change"        : 1.30,
        "change_pct"    : 1.21,
        "day_high"      : 109.10,
        "day_low"       : 107.00,
        "open"          : 107.50,
        "market_cap"    : "472.00B",
    },
}


def _fetch_live(ticker: str) -> dict | None:
    """
    Attempt a live Finnhub quote call.
    Returns structured dict on success, None on any failure.
    """
    try:
        client = _get_client()
        quote  = client.quote(ticker)

        # Finnhub returns c=0 when market is closed or ticker is invalid
        current_price = quote.get("c", 0)
        if not current_price:
            return None

        return {
            "current_price" : round(current_price, 2),
            "previous_close": round(quote.get("pc", 0), 2),
            "change"        : round(quote.get("d", 0), 2),
            "change_pct"    : round(quote.get("dp", 0), 2),
            "day_high"      : round(quote.get("h", 0), 2),
            "day_low"       : round(quote.get("l", 0), 2),
            "open"          : round(quote.get("o", 0), 2),
            "market_cap"    : "N/A",   # Finnhub free tier: quote endpoint only
        }
    except Exception as e:
        print(f"[Finnhub] ⚠️  API call failed for {ticker}: {e}")
        return None


def get_live_price(ticker: str) -> dict:
    """
    Fetch real-time market data for a given ticker.

    Tries Finnhub first (Tier 1). Falls back to mock data (Tier 2)
    if the API call fails for any reason.

    Args:
        ticker: Stock ticker symbol e.g. "GME", "TSLA"

    Returns:
        dict with market data + is_live flag indicating data source
    """
    if ticker not in KNOWN_TICKERS:
        return {
            "ticker" : ticker,
            "error"  : f"Ticker '{ticker}' is not in the supported list.",
            "is_live": False,
        }

    # Tier 1 — try live Finnhub data
    live_data = _fetch_live(ticker)
    if live_data:
        return {"ticker": ticker, "is_live": True, **live_data}

    # Tier 2 — fall back to mock data
    print(f"[Finnhub] ⚠️  Using mock fallback for {ticker}.")
    mock = MOCK_PRICES.get(ticker, {})
    return {"ticker": ticker, "is_live": False, **mock}


if __name__ == "__main__":
    # Quick test — run with: python -m retrieval.finnhub_tool
    test_tickers = ["GME", "TSLA", "NVDA"]
    for t in test_tickers:
        result = get_live_price(t)
        status = "LIVE 🟢" if result.get("is_live") else "MOCK 🟡"
        print(f"\n{t} [{status}]:")
        for key, val in result.items():
            print(f"  {key:<16} {val}")