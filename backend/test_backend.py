"""
tests/test_backend.py
---------------------
Automated test suite for the Financial RAG Engine backend.

Covers three levels:
  Level 1 — Syntax   : py_compile checks on all source files
  Level 2 — Imports  : verifies all functions/classes are importable
  Level 3 — Functional: live tests against Finnhub + ChromaDB (requires
                         Docker running and API keys in .env)

Changes vs original:
  - Replaced ingest_insider.py → ingest_sec.py (Layer 3 upgrade)
  - Added memory/session_store.py to syntax + import checks
  - Added QueryType.OUT_OF_SCOPE import check
  - Added RiskScore import check
  - Added session_store function checks

Usage:
  # From the /backend directory:
  python -m tests.test_backend              # all levels
  python -m tests.test_backend --quick      # levels 1 + 2 only (no API calls)

Output:
  Each test prints  ✅ PASS  or  ❌ FAIL  with a reason.
  Final summary shows total passed / failed.
  Exit code 0 = all passed, 1 = any failures.
"""

import sys
import os
import time
import argparse
import py_compile
import importlib
import traceback

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

results: list[tuple[str, bool, str]] = []


def passed(name: str, detail: str = "") -> None:
    results.append((name, True, detail))
    print(f"  {GREEN}✅ PASS{RESET}  {name}" + (f"  {YELLOW}({detail}){RESET}" if detail else ""))


def failed(name: str, reason: str) -> None:
    results.append((name, False, reason))
    print(f"  {RED}❌ FAIL{RESET}  {name}  {RED}{reason}{RESET}")


def section(title: str) -> None:
    print(f"\n{BOLD}{'─' * 55}{RESET}")
    print(f"{BOLD}  {title}{RESET}")
    print(f"{BOLD}{'─' * 55}{RESET}")


# ── Level 1: Syntax checks ────────────────────────────────────────────────────

SYNTAX_FILES = [
    "core/config.py",
    "ingestion/ingest_news.py",
    "ingestion/ingest_social.py",
    "ingestion/ingest_sec.py",          # ← was ingest_insider.py (Layer 3 upgrade)
    "ingestion/embedder.py",
    "retrieval/finnhub_tool.py",
    "retrieval/workflow.py",
    "retrieval/retriever.py",
    "synthesis/schemas.py",
    "synthesis/synthesizer.py",
    "memory/session_store.py",           # ← new: conversation memory
    "api/query.py",
]

def run_syntax_checks() -> None:
    section("LEVEL 1 — Syntax Checks")
    for filepath in SYNTAX_FILES:
        try:
            py_compile.compile(filepath, doraise=True)
            passed(filepath)
        except py_compile.PyCompileError as e:
            failed(filepath, str(e))
        except FileNotFoundError:
            failed(filepath, "File not found")


# ── Level 2: Import checks ────────────────────────────────────────────────────

IMPORT_CHECKS = [
    # (description, module, attributes_to_check)
    ("config — SEED_TICKERS",              "core.config",             ["SEED_TICKERS", "NEWS_CACHE_TTL_DAYS", "SEC_CIK_MAP"]),
    ("config — no KNOWN_TICKERS",          "core.config",             []),   # handled separately below
    ("schemas — QueryType has OUT_OF_SCOPE","synthesis.schemas",       ["QueryType"]),
    ("schemas — RiskScore exists",          "synthesis.schemas",       ["RiskScore", "AnalysisOutput"]),
    ("schemas — GeneralAnalysisOutput",     "synthesis.schemas",       ["GeneralAnalysisOutput", "TickerInsight"]),
    ("schemas — AnalysisOutput intact",     "synthesis.schemas",       ["AnalysisNarrative", "KnowledgeGraph"]),
    ("synthesizer — history params",        "synthesis.synthesizer",   ["synthesize", "synthesize_general"]),
    ("session_store — all functions",       "memory.session_store",    ["get_history", "append_turn", "clear_session",
                                                                         "format_history_for_prompt", "session_count"]),
    ("ingest_sec — live functions",         "ingestion.ingest_sec",    ["ingest_sec_for_ticker", "ingest_sec_if_stale", "ingest_sec"]),
    ("ingest_news — live functions",        "ingestion.ingest_news",   ["ingest_news_for_ticker", "ingest_news_if_stale", "ingest_news"]),
    ("finnhub_tool — get_live_price",       "retrieval.finnhub_tool",  ["get_live_price"]),
    ("workflow — seed_on_startup",          "retrieval.workflow",      ["seed_on_startup", "retrieve_all", "run_cross_portfolio_retrieval"]),
    ("query — router + lifespan",           "api.query",               ["router"]),  # lifespan handled separately in main.py
]

def run_import_checks() -> None:
    section("LEVEL 2 — Import Checks")

    for description, module_path, attrs in IMPORT_CHECKS:
        try:
            mod = importlib.import_module(module_path)

            # Special: KNOWN_TICKERS should no longer exist in config
            if module_path == "core.config" and not attrs:
                if hasattr(mod, "KNOWN_TICKERS"):
                    failed("config — KNOWN_TICKERS removed", "KNOWN_TICKERS still present (should be SEED_TICKERS)")
                else:
                    passed("config — KNOWN_TICKERS removed", "correctly replaced by SEED_TICKERS")
                continue

            # Special: verify OUT_OF_SCOPE exists in QueryType enum
            if description == "schemas — QueryType has OUT_OF_SCOPE":
                qt = getattr(mod, "QueryType", None)
                if qt and hasattr(qt, "OUT_OF_SCOPE"):
                    passed(description, "OUT_OF_SCOPE value present")
                else:
                    failed(description, "QueryType.OUT_OF_SCOPE missing")
                continue

            # Special: verify RiskScore has risk_percentage field
            if description == "schemas — RiskScore exists":
                rs = getattr(mod, "RiskScore", None)
                ao = getattr(mod, "AnalysisOutput", None)
                if rs and ao:
                    # Check AnalysisOutput has risk_score field
                    fields = ao.model_fields if hasattr(ao, "model_fields") else {}
                    if "risk_score" in fields:
                        passed(description, "RiskScore + AnalysisOutput.risk_score present")
                    else:
                        failed(description, "AnalysisOutput.risk_score field missing")
                else:
                    failed(description, f"Missing: {'RiskScore' if not rs else 'AnalysisOutput'}")
                continue

            # Special: verify synthesize() accepts history param
            if description == "synthesizer — history params":
                import inspect
                for fn_name in attrs:
                    fn = getattr(mod, fn_name, None)
                    if fn is None:
                        failed(description, f"{fn_name} not found")
                        continue
                    sig = inspect.signature(fn)
                    if "history" in sig.parameters:
                        passed(f"synthesizer.{fn_name} — history param", "✓")
                    else:
                        failed(f"synthesizer.{fn_name} — history param", "history parameter missing")
                continue

            # Default: check all listed attributes exist
            missing = [a for a in attrs if not hasattr(mod, a)]
            if missing:
                failed(description, f"Missing: {missing}")
            else:
                passed(description)

        except Exception as e:
            failed(description, f"Import error: {e}")


# ── Level 3: Functional tests ─────────────────────────────────────────────────

def run_functional_tests() -> None:
    section("LEVEL 3 — Functional Tests (requires API keys + Docker)")

    # ── 3a: Finnhub live price — seed ticker ─────────────────────────────────
    try:
        from retrieval.finnhub_tool import get_live_price
        result = get_live_price("GME")
        if result.get("current_price", 0) > 0:
            passed("Finnhub price — GME (seed)", f"${result['current_price']} is_live={result['is_live']}")
        else:
            failed("Finnhub price — GME (seed)", f"Price was 0 or missing: {result}")
    except Exception as e:
        failed("Finnhub price — GME (seed)", str(e))

    # ── 3b: Finnhub live price — non-seed ticker ──────────────────────────────
    try:
        from retrieval.finnhub_tool import get_live_price
        result = get_live_price("MSFT")
        if result.get("current_price", 0) > 0:
            passed("Finnhub price — MSFT (non-seed)", f"${result['current_price']} is_live={result['is_live']}")
        else:
            failed("Finnhub price — MSFT (non-seed)", f"Returned: {result}")
    except Exception as e:
        failed("Finnhub price — MSFT (non-seed)", str(e))

    # ── 3c: ChromaDB connectivity ─────────────────────────────────────────────
    try:
        from retrieval.chroma_client import get_client
        client = get_client()
        client.heartbeat()
        passed("ChromaDB — heartbeat", "connection OK")
    except Exception as e:
        failed("ChromaDB — heartbeat", str(e))

    # ── 3d: ChromaDB collections exist ───────────────────────────────────────
    try:
        from retrieval.chroma_client import (
            get_news_collection, get_social_collection,
            get_sec_collection, get_reddit_buzz_collection,
        )
        news_count   = get_news_collection().count()
        social_count = get_social_collection().count()
        sec_count    = get_sec_collection().count()
        reddit_count = get_reddit_buzz_collection().count()
        passed("ChromaDB — collections",
               f"news={news_count} social={social_count} sec={sec_count} reddit={reddit_count}")
    except Exception as e:
        failed("ChromaDB — collections", str(e))

    # ── 3e: SEC EDGAR — fetch one ticker ─────────────────────────────────────
    try:
        from ingestion.ingest_sec import _get_submissions
        from core.config import SEC_CIK_MAP
        cik  = SEC_CIK_MAP["AAPL"]
        data = _get_submissions(cik)
        if data and "filings" in data:
            passed("SEC EDGAR — submissions fetch (AAPL)", f"CIK={cik}")
        else:
            failed("SEC EDGAR — submissions fetch (AAPL)", f"Unexpected response: {str(data)[:100]}")
    except Exception as e:
        failed("SEC EDGAR — submissions fetch (AAPL)", str(e))

    # ── 3f: Session store — basic round-trip ─────────────────────────────────
    try:
        from memory.session_store import get_history, append_turn, clear_session
        test_sid = "test-session-123"
        assert get_history(test_sid) == [], "Fresh session should return empty list"
        append_turn(test_sid, "What is Tesla doing?", "Tesla's 10-K warns of margin pressure. Risk: 75%.", "TSLA")
        history = get_history(test_sid)
        assert len(history) == 2, f"Expected 2 entries, got {len(history)}"
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"
        assert history[0]["ticker"] == "TSLA"
        clear_session(test_sid)
        assert get_history(test_sid) == [], "Session should be empty after clear"
        passed("Session store — round-trip", "append + get + clear all working")
    except AssertionError as e:
        failed("Session store — round-trip", str(e))
    except Exception as e:
        failed("Session store — round-trip", str(e))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Financial RAG Engine test suite")
    parser.add_argument("--quick", action="store_true",
                        help="Run only syntax + import checks (no API calls)")
    args = parser.parse_args()

    print(f"\n{BOLD}{'═' * 55}{RESET}")
    print(f"{BOLD}  Financial RAG Engine — Backend Test Suite{RESET}")
    print(f"{BOLD}{'═' * 55}{RESET}")

    start = time.time()

    run_syntax_checks()
    run_import_checks()

    if not args.quick:
        run_functional_tests()
    else:
        section("LEVEL 3 — Functional Tests")
        print("  (skipped — run without --quick to include)")

    # ── Summary ───────────────────────────────────────────────────────────────
    elapsed     = time.time() - start
    total       = len(results)
    num_passed  = sum(1 for _, p, _ in results if p)
    num_failed  = total - num_passed

    print(f"\n{BOLD}{'═' * 55}{RESET}")
    print(f"{BOLD}  RESULTS: {num_passed}/{total} passed  ({elapsed:.1f}s){RESET}")
    if num_failed:
        print(f"\n{RED}{BOLD}  Failed tests:{RESET}")
        for name, ok, reason in results:
            if not ok:
                print(f"    {RED}✗ {name}: {reason}{RESET}")
    print(f"{BOLD}{'═' * 55}{RESET}\n")

    sys.exit(0 if num_failed == 0 else 1)


if __name__ == "__main__":
    main()