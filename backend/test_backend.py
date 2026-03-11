"""
tests/test_backend.py
---------------------
Automated test suite for the Financial RAG Engine backend.

Covers three levels:
  Level 1 — Syntax   : py_compile checks on all modified files
  Level 2 — Imports  : verifies all new functions/classes are importable
  Level 3 — Functional: live tests against Finnhub + ChromaDB (requires
                         Docker running and API keys in .env)

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

results: list[tuple[str, bool, str]] = []   # (test_name, passed, detail)


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
    "ingestion/ingest_insider.py",
    "ingestion/embedder.py",
    "retrieval/finnhub_tool.py",
    "retrieval/workflow.py",
    "retrieval/retriever.py",
    "synthesis/schemas.py",
    "synthesis/synthesizer.py",
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
    ("config — SEED_TICKERS",           "core.config",             ["SEED_TICKERS", "NEWS_CACHE_TTL_DAYS", "NEWS_FETCH_DAYS"]),
    ("config — no KNOWN_TICKERS",       "core.config",             []),   # handled separately below
    ("schemas — GeneralAnalysisOutput", "synthesis.schemas",       ["GeneralAnalysisOutput", "QueryType", "TickerInsight"]),
    ("schemas — AnalysisOutput intact", "synthesis.schemas",       ["AnalysisOutput", "AnalysisNarrative", "KnowledgeGraph"]),
    ("synthesizer — synthesize_general","synthesis.synthesizer",   ["synthesize", "synthesize_general"]),
    ("ingest_news — live functions",    "ingestion.ingest_news",   ["ingest_news_for_ticker", "ingest_news_if_stale", "ingest_news"]),
    ("finnhub_tool — get_live_price",   "retrieval.finnhub_tool",  ["get_live_price"]),
    ("workflow — seed_on_startup",      "retrieval.workflow",      ["seed_on_startup", "retrieve_all", "run_cross_portfolio_retrieval"]),
    ("query — lifespan hook",           "api.query",               ["router", "lifespan"]),
]

def run_import_checks() -> None:
    section("LEVEL 2 — Import Checks")

    for description, module_path, attrs in IMPORT_CHECKS:
        try:
            mod = importlib.import_module(module_path)

            # Special check: KNOWN_TICKERS should no longer exist in config
            if module_path == "core.config" and not attrs:
                if hasattr(mod, "KNOWN_TICKERS"):
                    failed("config — KNOWN_TICKERS removed", "KNOWN_TICKERS still present (should be SEED_TICKERS)")
                else:
                    passed("config — KNOWN_TICKERS removed", "correctly replaced by SEED_TICKERS")
                continue

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
        if "error" in result and result.get("is_live") is False:
            failed("Finnhub price — GME (seed)", f"API error: {result['error']}")
        elif result.get("current_price", 0) > 0:
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

    # ── 3c: Finnhub news fetch — any ticker ───────────────────────────────────
    try:
        from ingestion.ingest_news import ingest_news_for_ticker
        count = ingest_news_for_ticker("GME")
        if count > 0:
            passed("Finnhub news fetch — GME", f"{count} articles ingested")
        else:
            failed("Finnhub news fetch — GME", "0 articles returned (check Finnhub key or date range)")
    except Exception as e:
        failed("Finnhub news fetch — GME", str(e))

    # ── 3d: Cache hit — second call should return 0 ───────────────────────────
    try:
        from ingestion.ingest_news import ingest_news_if_stale
        count = ingest_news_if_stale("GME")
        if count == 0:
            passed("News cache hit — GME", "correctly skipped re-fetch (cache fresh)")
        else:
            failed("News cache hit — GME", f"Expected 0 (cache hit) but got {count}")
    except Exception as e:
        failed("News cache hit — GME", str(e))

    # ── 3e: Non-seed ticker auto-ingestion ────────────────────────────────────
    try:
        from ingestion.ingest_news import ingest_news_for_ticker
        count = ingest_news_for_ticker("MSFT")
        if count > 0:
            passed("Non-seed ticker ingestion — MSFT", f"{count} articles ingested")
        else:
            failed("Non-seed ticker ingestion — MSFT", "0 articles — MSFT may not be supported on your Finnhub plan")
    except Exception as e:
        failed("Non-seed ticker ingestion — MSFT", str(e))

    # ── 3f: Regex ticker extraction ───────────────────────────────────────────
    try:
        from api.query import _extract_ticker_regex
        cases = [
            ("Should I buy $GME right now?",        "GME"),
            ("What is happening with Tesla stock?", "TSLA"),
            ("Tell me about NVDA earnings",         "NVDA"),
            ("What should I invest in?",            None),
        ]
        all_ok = True
        for question, expected in cases:
            result = _extract_ticker_regex(question)
            if result != expected:
                failed(f"Regex extraction — '{question[:40]}'", f"Expected {expected}, got {result}")
                all_ok = False
        if all_ok:
            passed("Regex ticker extraction — all 4 cases", f"{len(cases)} cases correct")
    except Exception as e:
        failed("Regex ticker extraction", str(e))

    # ── 3g: Full async retrieval — seed ticker ────────────────────────────────
    try:
        import asyncio
        from retrieval.workflow import retrieve_all
        start   = time.time()
        context = asyncio.run(retrieve_all("GME", "Should I buy GME?"))
        elapsed = round(time.time() - start, 2)

        has_news  = len(context.get("news", [])) > 0
        has_price = context.get("price", {}).get("current_price", 0) > 0

        if has_news and has_price:
            passed("Full retrieval — GME", f"{len(context['news'])} news, price=${context['price']['current_price']}, {elapsed}s")
        else:
            failed("Full retrieval — GME", f"news={len(context.get('news',[]))}, price={context.get('price',{})}")
    except Exception as e:
        failed("Full retrieval — GME", traceback.format_exc().splitlines()[-1])

    # ── 3h: Full async retrieval — non-seed ticker ────────────────────────────
    try:
        import asyncio
        from retrieval.workflow import retrieve_all
        start   = time.time()
        context = asyncio.run(retrieve_all("MSFT", "What is Microsoft doing in AI?"))
        elapsed = round(time.time() - start, 2)

        has_news = len(context.get("news", [])) > 0
        if has_news:
            passed("Full retrieval — MSFT (non-seed)", f"{len(context['news'])} news articles, {elapsed}s")
        else:
            failed("Full retrieval — MSFT (non-seed)", "No news retrieved — check Finnhub plan supports MSFT")
    except Exception as e:
        failed("Full retrieval — MSFT (non-seed)", traceback.format_exc().splitlines()[-1])


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary() -> int:
    total   = len(results)
    passing = sum(1 for _, ok, _ in results if ok)
    failing = total - passing

    print(f"\n{BOLD}{'═' * 55}{RESET}")
    print(f"{BOLD}  RESULTS: {passing}/{total} passed", end="")
    if failing:
        print(f"  {RED}({failing} failed){RESET}")
    else:
        print(f"  {GREEN}(all clear ✅){RESET}")
    print(f"{BOLD}{'═' * 55}{RESET}")

    if failing:
        print(f"\n{RED}{BOLD}Failed tests:{RESET}")
        for name, ok, detail in results:
            if not ok:
                print(f"  ❌  {name}: {detail}")

    return 0 if failing == 0 else 1


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Financial RAG backend test suite")
    parser.add_argument("--quick", action="store_true",
                        help="Run levels 1 + 2 only (no API calls)")
    args = parser.parse_args()

    print(f"\n{BOLD}Financial RAG Engine — Automated Test Suite{RESET}")
    print(f"Working directory: {os.getcwd()}")

    run_syntax_checks()
    run_import_checks()

    if not args.quick:
        run_functional_tests()
    else:
        print(f"\n{YELLOW}Skipping Level 3 (--quick mode){RESET}")

    sys.exit(print_summary())