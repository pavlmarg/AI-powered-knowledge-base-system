"""
retrieval/finnhub_tool.py
-------------------------
Layer 4 — Live market data fetcher using the official Finnhub REST API.

UPGRADED: Removed the KNOWN_TICKERS whitelist guard. The system now
accepts any valid stock ticker, so the price fetcher must too.
For unknown tickers there is no mock fallback — we return a clear
error dict instead of silently returning stale mock data.

Architecture:
  Tier 1 — Attempts a real Finnhub API call for any ticker
  Tier 2 — Falls back to mock data ONLY for the original seed tickers
            (kept so demos work offline for the 10 known companies)
  Tier 3 — Returns an error dict for unknown tickers if Finnhub fails

The 'is_live' key in every response tells the caller and the frontend
whether the data is real-time or from the mock fallback.
"""

import finnhub
from core.config import FINNHUB_API_KEY, SEED_TICKERS

# ── Finnhub client (singleton) ────────────────────────────────────────────────
_client: finnhub.Client | None = None


def _get_client() -> finnhub.Client:
    """Return the shared Finnhub client, creating it once."""
    global _client
    if _client is None:
        _client = finnhub.Client(api_key=FINNHUB_API_KEY)
    return _client


# ── Realistic fallback mock data for seed tickers only ───────────────────────
# Used ONLY when the live Finnhub call fails for a known seed ticker.
# Values reflect approximate market prices as of March 2026.
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
    Attempt a live Finnhub quote call for any ticker.
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
            "change"        : round(quote.get("d",  0), 2),
            "change_pct"    : round(quote.get("dp", 0), 2),
            "day_high"      : round(quote.get("h",  0), 2),
            "day_low"       : round(quote.get("l",  0), 2),
            "open"          : round(quote.get("o",  0), 2),
            "market_cap"    : "N/A",
        }
    except Exception as e:
        print(f"[Finnhub] ⚠️  API call failed for {ticker}: {e}")
        return None


def get_live_price(ticker: str) -> dict:
    """
    Fetch real-time market data for any stock ticker.

    Tier 1 — tries live Finnhub API (works for any valid ticker).
    Tier 2 — falls back to mock data for seed tickers (offline demo safety).
    Tier 3 — returns an error dict for unknown tickers with no mock data.

    Args:
        ticker: Any stock ticker symbol e.g. "GME", "MSFT", "AMZN"

    Returns:
        dict with market data + is_live flag indicating data source.
    """
    # Tier 1 — try live data for any ticker
    live_data = _fetch_live(ticker)
    if live_data:
        return {"ticker": ticker, "is_live": True, **live_data}

    # Tier 2 — mock fallback for seed tickers only
    if ticker in SEED_TICKERS and ticker in MOCK_PRICES:
        print(f"[Finnhub] ⚠️  Using mock fallback for {ticker}.")
        mock = MOCK_PRICES[ticker]
        return {"ticker": ticker, "is_live": False, **mock}

    # Tier 3 — unknown ticker, live call failed, no mock available
    print(f"[Finnhub] ⚠️  No price data available for {ticker}.")
    return {
        "ticker" : ticker,
        "error"  : f"Could not fetch live price for '{ticker}'. Market may be closed.",
        "is_live": False,
    }


if __name__ == "__main__":
    # Quick test — run with: python -m retrieval.finnhub_tool
    # Tests both a seed ticker and a non-seed ticker
    test_tickers = ["GME", "TSLA", "MSFT", "AMZN"]
    for t in test_tickers:
        result = get_live_price(t)
        status = "LIVE 🟢" if result.get("is_live") else "MOCK 🟡"
        print(f"\n{t} [{status}]:")
        for key, val in result.items():
            print(f"  {key:<16} {val}")