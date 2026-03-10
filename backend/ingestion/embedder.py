"""
ingestion/embedder.py
---------------------
Shared utility that calls the OpenAI Embeddings API.

All three ingestion scripts use this single function so that:
  - The model name is controlled from config.py in one place
  - Batching is handled here (OpenAI allows up to 2048 texts per call)
  - Every layer gets identical, consistent embeddings
"""

from openai import OpenAI
from core.config import OPENAI_API_KEY, EMBEDDING_MODEL

_client = OpenAI(api_key=OPENAI_API_KEY)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of strings using text-embedding-3-small.
    Returns a list of 1536-dimensional float vectors, one per input text.

    Batches automatically if len(texts) > 500 to stay well within
    the OpenAI rate limit for a hackathon-tier key.
    """
    if not texts:
        return []

    all_embeddings: list[list[float]] = []
    batch_size = 500

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = _client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch,
        )
        # Response items are ordered to match input order
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)

    return all_embeddings