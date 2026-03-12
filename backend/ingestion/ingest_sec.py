"""
ingestion/ingest_sec.py
-----------------------
Layer 3 — SEC EDGAR Filings ingestion pipeline.
Replaces the old ingest_insider.py / layer-3-insider.json approach.

What this script does:
  1. For each ticker, resolves its CIK from SEC_CIK_MAP (config.py)
  2. Calls the free SEC EDGAR submissions API to get the filing index:
       GET https://data.sec.gov/submissions/CIK{cik}.json
  3. Filters for the most recent 10-K, 10-Q and 8-K filings
  4. Fetches the actual filing document text from EDGAR Archives
  5. Extracts the most informative sections:
       - 10-K / 10-Q : Item 1A (Risk Factors) + Item 7 (MD&A)
       - 8-K          : Full body (usually short — earnings, M&A events)
  6. Chunks long sections into ~1000-token pieces (ChromaDB limit-friendly)
  7. Applies synthetic text transformation:
       "[TSLA][SEC-10K] Risk Factors: <extracted text>"
  8. Embeds and upserts into 'layer_sec' ChromaDB collection

Why this is a massive upgrade over static insider JSON:
  - 10-K Risk Factors = the company's own words about what could go wrong
  - MD&A = management's explanation of revenue trends, margins, outlook
  - 8-K = real-time material events (earnings beats/misses, M&A, CEO exits)
  The synthesis engine can now quote directly from official SEC language,
  making analysis dramatically more grounded and credible.

SEC EDGAR API:
  - Completely free, no API key required
  - Rate limit: 10 requests/second (we respect this with a small delay)
  - User-Agent header is required by SEC policy

Metadata stored per chunk:
  - ticker       : str   e.g. "TSLA"
  - layer        : str   always "sec"
  - filing_type  : str   "10-K", "10-Q", or "8-K"
  - filed_date   : str   e.g. "2025-02-05"
  - section      : str   e.g. "Risk Factors", "MD&A", "8-K Event"
  - accession_no : str   SEC accession number (unique filing ID)
  - date_ts      : int   Unix timestamp of filing date
"""

import re
import time
import uuid
import requests
from datetime import datetime, timezone

from core.config import (
    SEC_CIK_MAP,
    SEC_FILING_TYPES,
    SEC_FILINGS_PER_TYPE,
    SEED_TICKERS,
    COLLECTION_SEC,
)
from ingestion.embedder import embed_texts
from retrieval.chroma_client import get_sec_collection

# ── SEC EDGAR request headers ─────────────────────────────────────────────────
# SEC policy requires a descriptive User-Agent with contact info.
HEADERS = {
    "User-Agent": "FinancialRAGEngine research@hackathon.dev",
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov",
}

# Archive headers use a different host
ARCHIVE_HEADERS = {
    "User-Agent": "FinancialRAGEngine research@hackathon.dev",
}

# Max characters to extract per section before chunking
MAX_SECTION_CHARS = 4000

# Characters per chunk when splitting long sections
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 100


# ── Date parsing ──────────────────────────────────────────────────────────────

def _parse_date(date_str: str) -> int:
    """Convert 'YYYY-MM-DD' filing date to Unix timestamp (midnight UTC)."""
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


# ── SEC EDGAR API calls ───────────────────────────────────────────────────────

def _get_submissions(cik: str) -> dict | None:
    """
    Fetch the full submissions JSON for a company from SEC EDGAR.

    Returns the parsed JSON dict, or None on failure.
    The JSON contains metadata for ALL filings ever made by this company,
    including accession numbers needed to fetch the actual documents.
    """
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  [SEC] ⚠️  Failed to fetch submissions for CIK {cik}: {e}")
        return None


def _get_filing_document(accession_no: str, cik: str) -> str | None:
    """
    Fetch the primary text document for a given SEC filing.

    SEC filing URL structure:
      https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/{filename}

    We first fetch the filing index to find the primary document filename,
    then fetch the document itself.
    """
    cik_int     = str(int(cik))                        # Remove leading zeros
    acc_nodash  = accession_no.replace("-", "")        # e.g. 0001193125-24-012345 → 000119312524012345
    index_url   = (f"https://www.sec.gov/Archives/edgar/data/"
                   f"{cik_int}/{acc_nodash}/{accession_no}-index.htm")

    try:
        resp = requests.get(index_url, headers=ARCHIVE_HEADERS, timeout=15)
        resp.raise_for_status()

        # Find the primary document link from the index page
        # Primary docs are typically .htm or .txt files listed first
        matches = re.findall(
            r'href="(/Archives/edgar/data/[^"]+\.(?:htm|txt))"',
            resp.text,
            re.IGNORECASE,
        )
        if not matches:
            return None

        # Take the first match (primary document)
        doc_url = "https://www.sec.gov" + matches[0]
        time.sleep(0.12)  # Respect SEC rate limit: max 10 req/s

        doc_resp = requests.get(doc_url, headers=ARCHIVE_HEADERS, timeout=20)
        doc_resp.raise_for_status()
        return doc_resp.text

    except Exception as e:
        print(f"  [SEC] ⚠️  Failed to fetch document {accession_no}: {e}")
        return None


# ── Section extraction ────────────────────────────────────────────────────────

def _clean_html(text: str) -> str:
    """Strip HTML tags and normalise whitespace from SEC filing text."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;",  "&", text)
    text = re.sub(r"&lt;",   "<", text)
    text = re.sub(r"&gt;",   ">", text)
    text = re.sub(r"\s+",    " ", text)
    return text.strip()


def _extract_section(text: str, filing_type: str) -> dict:
    """
    Extract the most informative sections from a filing document.

    For 10-K / 10-Q:
      - Item 1A: Risk Factors  — what management says could go wrong
      - Item 7:  MD&A          — management's discussion of financial results

    For 8-K:
      - Full body text         — usually short, describes the material event

    Returns a dict of {section_name: extracted_text}.
    """
    clean = _clean_html(text)
    sections = {}

    if filing_type in ("10-K", "10-Q"):
        # Risk Factors: look for "Item 1A" heading
        risk_match = re.search(
            r"(?i)item\s+1a[\.\s]+risk\s+factors(.{200," + str(MAX_SECTION_CHARS) + r"}?)(?=item\s+1b|item\s+2|\Z)",
            clean,
        )
        if risk_match:
            sections["Risk Factors"] = risk_match.group(1).strip()[:MAX_SECTION_CHARS]

        # MD&A: look for "Item 7" heading
        mda_match = re.search(
            r"(?i)item\s+7[\.\s]+management.{0,50}discussion(.{200," + str(MAX_SECTION_CHARS) + r"}?)(?=item\s+7a|item\s+8|\Z)",
            clean,
        )
        if mda_match:
            sections["MD&A"] = mda_match.group(1).strip()[:MAX_SECTION_CHARS]

        # Fallback: if neither section found, take a chunk of the full text
        if not sections:
            sections["Filing Text"] = clean[:MAX_SECTION_CHARS]

    else:  # 8-K
        # 8-Ks are typically short — take the meaningful body
        sections["8-K Event"] = clean[:MAX_SECTION_CHARS]

    return sections


def _chunk_text(text: str) -> list[str]:
    """
    Split a long text into overlapping chunks for embedding.

    Overlap ensures context is not lost at chunk boundaries —
    a sentence spanning two chunks is partially captured in both.
    """
    if len(text) <= CHUNK_SIZE:
        return [text]

    chunks = []
    start  = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end])
        start += CHUNK_SIZE - CHUNK_OVERLAP

    return chunks


# ── Filing index parsing ──────────────────────────────────────────────────────

def _get_recent_filings(submissions: dict, filing_type: str, max_count: int) -> list[dict]:
    """
    Extract the most recent N filings of a given type from the submissions JSON.

    The submissions JSON contains parallel arrays under 'filings.recent':
      form[]          — filing type e.g. "10-K"
      accessionNumber[] — unique filing ID
      filingDate[]    — date string "YYYY-MM-DD"

    Returns a list of dicts with accession_no and filed_date.
    """
    try:
        recent  = submissions["filings"]["recent"]
        forms   = recent["form"]
        accnums = recent["accessionNumber"]
        dates   = recent["filingDate"]
    except (KeyError, TypeError):
        return []

    results = []
    for form, acc, date in zip(forms, accnums, dates):
        if form == filing_type:
            results.append({"accession_no": acc, "filed_date": date})
            if len(results) >= max_count:
                break

    return results


# ── Dynamic CIK lookup ───────────────────────────────────────────────────────

def _lookup_cik_dynamic(ticker: str) -> str | None:
    """
    Dynamically resolve a CIK for any ticker not in SEC_CIK_MAP.

    SEC provides a full ticker→CIK map at:
      https://www.sec.gov/files/company_tickers.json

    Returns a zero-padded 10-digit CIK string, or None if not found.
    This allows the system to handle ANY publicly traded company,
    not just the 10 seed tickers.
    """
    url = "https://www.sec.gov/files/company_tickers.json"
    try:
        resp = requests.get(url, headers=ARCHIVE_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        # JSON format: {"0": {"cik_str": 320193, "ticker": "AAPL", ...}, ...}
        for entry in data.values():
            if entry.get("ticker", "").upper() == ticker.upper():
                cik_int = entry["cik_str"]
                padded  = str(cik_int).zfill(10)
                print(f"  [SEC] 🔍 Dynamic CIK lookup: {ticker} → {padded}")
                return padded
        print(f"  [SEC] ⚠️  Ticker {ticker} not found in SEC company_tickers.json")
        return None
    except Exception as e:
        print(f"  [SEC] ⚠️  Dynamic CIK lookup failed for {ticker}: {e}")
        return None


# ── Main ingestion function ───────────────────────────────────────────────────

def ingest_sec_for_ticker(ticker: str) -> int:
    """
    Fetch and ingest SEC filings for a single ticker.

    Pipeline:
      1. Resolve CIK from config
      2. Fetch submissions index from SEC EDGAR
      3. For each filing type (10-K, 10-Q, 8-K):
         a. Find the most recent N filings
         b. Fetch the filing document text
         c. Extract key sections (Risk Factors, MD&A, 8-K body)
         d. Chunk each section
         e. Build embed text with synthetic transformation
         f. Upsert into ChromaDB
    Returns the total number of chunks ingested.
    """
    # Try the hardcoded map first (fast, no API call).
    # Fall back to dynamic SEC lookup for any ticker outside SEED_TICKERS
    # e.g. MSFT, AMZN, GOOGL — any publicly traded company works.
    cik = SEC_CIK_MAP.get(ticker) or _lookup_cik_dynamic(ticker)
    if not cik:
        print(f"  [SEC] ⚠️  Could not resolve CIK for {ticker} — skipping")
        return 0

    print(f"  [SEC] Fetching submissions for {ticker} (CIK: {cik})...")
    submissions = _get_submissions(cik)
    if not submissions:
        return 0

    collection = get_sec_collection()
    total_chunks = 0

    for filing_type in SEC_FILING_TYPES:
        filings = _get_recent_filings(submissions, filing_type, SEC_FILINGS_PER_TYPE)
        print(f"  [SEC] {ticker} — {filing_type}: found {len(filings)} recent filing(s)")

        for filing in filings:
            acc_no     = filing["accession_no"]
            filed_date = filing["filed_date"]

            time.sleep(0.12)  # Respect SEC 10 req/s rate limit
            doc_text = _get_filing_document(acc_no, cik)

            if not doc_text:
                print(f"  [SEC] ⚠️  Could not fetch document {acc_no}")
                continue

            sections = _extract_section(doc_text, filing_type)
            date_ts  = _parse_date(filed_date)

            for section_name, section_text in sections.items():
                chunks = _chunk_text(section_text)

                texts:     list[str]  = []
                metadatas: list[dict] = []
                ids:       list[str]  = []

                for chunk_idx, chunk in enumerate(chunks):
                    # Synthetic text transformation — rich semantic prefix
                    embed_text = (
                        f"[{ticker}][SEC-{filing_type}] {section_name} "
                        f"(filed {filed_date}): {chunk}"
                    )

                    texts.append(embed_text)
                    metadatas.append({
                        "ticker":       ticker,
                        "layer":        "sec",
                        "filing_type":  filing_type,
                        "filed_date":   filed_date,
                        "section":      section_name,
                        "accession_no": acc_no,
                        "chunk_idx":    chunk_idx,
                        "date_ts":      date_ts,
                    })
                    # Deterministic ID — prevents duplicates on re-ingestion
                    ids.append(str(uuid.uuid5(
                        uuid.NAMESPACE_DNS,
                        f"{ticker}-{acc_no}-{section_name}-{chunk_idx}"
                    )))

                if texts:
                    embeddings = embed_texts(texts)
                    collection.upsert(
                        ids=ids,
                        embeddings=embeddings,
                        documents=texts,
                        metadatas=metadatas,
                    )
                    total_chunks += len(texts)
                    print(f"  [SEC] ✅ {ticker} {filing_type} '{section_name}' "
                          f"— {len(texts)} chunk(s) ingested")

    return total_chunks


def ingest_sec_if_stale(ticker: str) -> int:
    """
    Ingest SEC filings for a ticker only if the cache is stale or empty.

    Checks the most recent document date in the SEC collection for this ticker.
    If no documents exist, or the newest is older than SEC_CACHE_TTL_DAYS,
    triggers a fresh ingestion.

    Returns the number of new chunks ingested (0 if cache was still fresh).
    """
    from core.config import SEC_CACHE_TTL_DAYS
    from datetime import datetime, timezone, timedelta

    collection = get_sec_collection()

    try:
        existing = collection.get(
            where={"ticker": {"$eq": ticker}},
            limit=1,
            include=["metadatas"],
        )
        if existing["ids"]:
            # Check age of the newest cached filing
            newest_ts = max(
                m.get("date_ts", 0)
                for m in existing["metadatas"]
            )
            age_days = (datetime.now(timezone.utc).timestamp() - newest_ts) / 86400
            if age_days < SEC_CACHE_TTL_DAYS:
                print(f"  [SEC] {ticker} cache fresh ({age_days:.0f}d old) — skipping")
                return 0
    except Exception:
        pass  # Collection empty or error → proceed with ingestion

    return ingest_sec_for_ticker(ticker)


def ingest_sec() -> int:
    """
    Ingest SEC filings for all SEED_TICKERS.
    Called by run_ingestion.py on startup / re-ingest.
    Returns total chunks ingested across all tickers.
    """
    print(f"\n[SEC] Starting ingestion for {len(SEED_TICKERS)} seed tickers...")
    total = 0
    for ticker in sorted(SEED_TICKERS):
        count = ingest_sec_for_ticker(ticker)
        total += count
        print(f"  [SEC] {ticker}: {count} chunks")
    print(f"[SEC] Total SEC chunks ingested: {total}")
    return total
