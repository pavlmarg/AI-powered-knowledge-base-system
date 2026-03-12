"""
retrieval/retriever.py
----------------------
ChromaDB semantic retrieval functions for all data layers.

Each function:
  1. Embeds the user query using the same model used during ingestion
     (text-embedding-3-small) — this ensures vector space consistency
  2. Queries the relevant ChromaDB collection with:
       - Semantic similarity search (cosine distance)
       - Metadata filter: ticker must match the requested company
  3. Returns a clean list of result dicts ready for the synthesis engine

Layer 3 change:
  retrieve_insider()     → retrieve_sec_filings()
  get_insider_collection → get_sec_collection

  The new function retrieves the most semantically relevant SEC filing
  chunks for the user's query — e.g. a question about "risk" will surface
  Risk Factor sections, while a question about "revenue" will surface MD&A.

Top-K values per layer (tuned for synthesis context window):
  News         : top 3  — articles are long, 3 is enough context
  Social       : top 5  — posts are short, more gives richer sentiment signal
  SEC Filings  : top 4  — chunks are ~1000 chars, 4 gives rich official context
  Reddit Buzz  : top 1  — one document per ticker per day by design
"""

from ingestion.embedder import embed_texts
from retrieval.chroma_client import (
    get_news_collection,
    get_social_collection,
    get_sec_collection,
    get_reddit_buzz_collection,
)

# Number of results to retrieve per layer
TOP_K_NEWS        = 3
TOP_K_SOCIAL      = 5
TOP_K_SEC         = 4  # SEC chunks are ~1000 chars — 4 gives ~4000 chars of official text
TOP_K_REDDIT_BUZZ = 1  # One doc per ticker per day — always return it if it exists


def _embed_query(query: str) -> list[float]:
    """Embed a single query string into a vector."""
    return embed_texts([query])[0]


def _format_results(results: dict) -> list[dict]:
    """
    Convert raw ChromaDB query results into a clean list of dicts.

    ChromaDB returns parallel lists (ids, documents, metadatas, distances).
    This zips them into a list of structured result objects.
    """
    formatted = []
    ids        = results.get("ids", [[]])[0]
    documents  = results.get("documents", [[]])[0]
    metadatas  = results.get("metadatas", [[]])[0]
    distances  = results.get("distances", [[]])[0]

    for i in range(len(ids)):
        formatted.append({
            "id"        : ids[i],
            "document"  : documents[i],
            "metadata"  : metadatas[i],
            "relevance" : round(1 - distances[i], 4),  # cosine: 1=identical, 0=unrelated
        })

    return formatted


def retrieve_news(ticker: str, query: str) -> list[dict]:
    """
    Retrieve the most relevant news articles for a given ticker and query.

    Args:
        ticker : Stock ticker e.g. "GME"
        query  : Natural language query e.g. "What is the latest news on GME?"

    Returns:
        List of up to TOP_K_NEWS result dicts, each containing:
          document  — the embedded text (metadata-prepended content)
          metadata  — ticker, layer, date_ts, date_str, title
          relevance — cosine similarity score (0-1)
    """
    collection   = get_news_collection()
    query_vector = _embed_query(query)

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=TOP_K_NEWS,
        where={"ticker": {"$eq": ticker}},
        include=["documents", "metadatas", "distances"],
    )

    return _format_results(results)


def retrieve_social(ticker: str, query: str) -> list[dict]:
    """
    Retrieve the most relevant social media posts for a given ticker and query.

    Args:
        ticker : Stock ticker e.g. "GME"
        query  : Natural language query e.g. "What is social sentiment on GME?"

    Returns:
        List of up to TOP_K_SOCIAL result dicts, each containing:
          document  — the embedded text (platform-prepended content)
          metadata  — ticker, layer, platform, username, engagement_score,
                      date_ts, date_str
          relevance — cosine similarity score (0-1)
    """
    collection   = get_social_collection()
    query_vector = _embed_query(query)

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=TOP_K_SOCIAL,
        where={"ticker": {"$eq": ticker}},
        include=["documents", "metadatas", "distances"],
    )

    return _format_results(results)


def retrieve_sec_filings(ticker: str, query: str) -> list[dict]:
    """
    Retrieve the most semantically relevant SEC filing chunks for a ticker.

    This replaces retrieve_insider(). Instead of returning a fixed set of
    insider trade records, this returns whichever SEC filing sections are
    most relevant to the user's query — e.g.:

      Query: "What are the risks for Tesla?"
        → Returns Risk Factor chunks from the most recent 10-K

      Query: "How is Nvidia's revenue trending?"
        → Returns MD&A chunks discussing revenue performance

      Query: "Did Apple announce anything major recently?"
        → Returns recent 8-K event filings

    The semantic search means the most relevant official company language
    is always surfaced, regardless of which section it lives in.

    Args:
        ticker : Stock ticker e.g. "TSLA"
        query  : Natural language query

    Returns:
        List of up to TOP_K_SEC result dicts, each containing:
          document  — the embedded chunk with synthetic prefix
          metadata  — ticker, layer, filing_type, filed_date, section,
                      accession_no, chunk_idx, date_ts
          relevance — cosine similarity score (0-1)
    """
    try:
        collection   = get_sec_collection()
        query_vector = _embed_query(query)

        # Count first — ChromaDB throws if n_results > actual doc count
        count_check  = collection.get(
            where={"ticker": {"$eq": ticker}},
            limit=TOP_K_SEC,
        )
        actual_count = len(count_check.get("ids", []))

        if actual_count == 0:
            return []

        results = collection.query(
            query_embeddings=[query_vector],
            n_results=min(TOP_K_SEC, actual_count),
            where={"ticker": {"$eq": ticker}},
            include=["documents", "metadatas", "distances"],
        )

        return _format_results(results)

    except Exception as e:
        print(f"[Retriever] ⚠️  SEC filings retrieval failed for {ticker}: {e}")
        return []


def retrieve_reddit_buzz(ticker: str, query: str) -> list[dict]:
    """
    Retrieve the Reddit buzz signal for a given ticker (Layer 5).

    Layer 5 stores one document per ticker per day — a quantitative
    summary of Reddit activity (rank, mentions, upvotes, momentum).

    Args:
        ticker : Stock ticker e.g. "GME"
        query  : Natural language query (used for semantic ranking)

    Returns:
        List of up to 1 result dict containing:
          document  — the Reddit buzz summary text
          metadata  — ticker, layer, rank, rank_24h_ago, mentions,
                      upvotes, date_ts, date_str
          relevance — cosine similarity score (0-1)
    """
    try:
        collection   = get_reddit_buzz_collection()
        query_vector = _embed_query(query)

        # Count first — ChromaDB throws if n_results > actual doc count
        count_check  = collection.get(
            where={"ticker": {"$eq": ticker}},
            limit=TOP_K_REDDIT_BUZZ,
        )
        actual_count = len(count_check.get("ids", []))

        if actual_count == 0:
            return []

        results = collection.query(
            query_embeddings=[query_vector],
            n_results=min(TOP_K_REDDIT_BUZZ, actual_count),
            where={"ticker": {"$eq": ticker}},
            include=["documents", "metadatas", "distances"],
        )

        return _format_results(results)

    except Exception as e:
        print(f"[Retriever] Reddit buzz retrieval failed for {ticker}: {e}")
        return []
