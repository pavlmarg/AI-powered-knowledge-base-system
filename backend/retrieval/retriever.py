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

Why metadata filtering matters:
  Without the ticker filter, a query about GME might return TSLA documents
  that happen to be semantically similar (e.g. both about short squeezes).
  The filter guarantees we only retrieve documents about the exact company
  the user is asking about — this is what makes contradiction detection reliable.

Top-K values per layer (tuned for synthesis context window):
  News         : top 3  — articles are long, 3 is enough context
  Social       : top 5  — posts are short, more gives richer sentiment signal
  Insider      : top 3  — 50 records total, 3 covers the most relevant trades
  Reddit Buzz  : top 1  — one document per ticker per day by design
"""

from ingestion.embedder import embed_texts
from retrieval.chroma_client import (
    get_news_collection,
    get_social_collection,
    get_insider_collection,
    get_reddit_buzz_collection,
)

# Number of results to retrieve per layer
TOP_K_NEWS        = 3
TOP_K_SOCIAL      = 5
TOP_K_INSIDER     = 3
TOP_K_REDDIT_BUZZ = 1   # One doc per ticker per day — always return it if it exists


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


def retrieve_insider(ticker: str, query: str) -> list[dict]:
    """
    Retrieve the most relevant insider trading records for a given ticker.

    Args:
        ticker : Stock ticker e.g. "GME"
        query  : Natural language query e.g. "Have GME insiders been selling?"

    Returns:
        List of up to TOP_K_INSIDER result dicts, each containing:
          document  — the synthetic text transformation of the trade
          metadata  — ticker, layer, executive_role, action, shares_volume,
                      date_ts, date_str
          relevance — cosine similarity score (0-1)
    """
    collection   = get_insider_collection()
    query_vector = _embed_query(query)

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=TOP_K_INSIDER,
        where={"ticker": {"$eq": ticker}},
        include=["documents", "metadatas", "distances"],
    )

    return _format_results(results)


def retrieve_reddit_buzz(ticker: str, query: str) -> list[dict]:
    """
    Retrieve the Reddit buzz signal for a given ticker (Layer 5).

    Layer 5 stores one document per ticker per day — a quantitative
    summary of Reddit activity (rank, mentions, upvotes, momentum).

    Uses a count-first pattern to avoid the ChromaDB crash that occurs
    when n_results exceeds the number of documents matching the filter.
    Returns an empty list (never raises) if no data exists.

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
        print(f"[Retriever] ⚠️  Reddit buzz retrieval failed for {ticker}: {e}")
        return []


if __name__ == "__main__":
    # Quick test — run with: python -m retrieval.retriever
    TEST_TICKER = "GME"
    TEST_QUERY  = "What is happening with GameStop stock?"

    print(f"\nTesting retrieval for {TEST_TICKER}...")
    print(f"News       : {len(retrieve_news(TEST_TICKER, TEST_QUERY))} results")
    print(f"Social     : {len(retrieve_social(TEST_TICKER, TEST_QUERY))} results")
    print(f"Insider    : {len(retrieve_insider(TEST_TICKER, TEST_QUERY))} results")
    print(f"RedditBuzz : {len(retrieve_reddit_buzz(TEST_TICKER, TEST_QUERY))} results")