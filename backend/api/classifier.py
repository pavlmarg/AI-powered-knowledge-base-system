"""
api/classifier.py
-----------------
Query classifier — determines what type of query the user is asking
and which tickers are involved, using conversation history for context.

Query types:
  SINGLE   → "Should I buy GME?"              → 1 ticker
  COMPARE  → "Compare GME, NVDA and TSLA"     → 2+ tickers
  FOLLOWUP → "What about the insider activity?"→ resolves from history
  GENERAL  → "What's the riskiest stock?"     → all or no specific ticker

Also provides get_recognised_ticker() for friendly handling of companies
we know about but don't have in our knowledge base (Amazon, Microsoft, etc).
"""

from openai import OpenAI
from pydantic import BaseModel, Field
from typing import List, Optional
from core.config import OPENAI_API_KEY, KNOWN_TICKERS

_client = OpenAI(api_key=OPENAI_API_KEY)


# ── Companies we recognise but don't support ──────────────────────────────────
# Used to give a friendly redirect instead of a cold error.
RECOGNISED_BUT_UNSUPPORTED: dict[str, str] = {
    "amazon"    : "AMZN",
    "microsoft" : "MSFT",
    "google"    : "GOOGL",
    "alphabet"  : "GOOGL",
    "meta"      : "META",
    "facebook"  : "META",
    "netflix"   : "NFLX",
    "spotify"   : "SPOT",
    "uber"      : "UBER",
    "airbnb"    : "ABNB",
    "shopify"   : "SHOP",
    "salesforce": "CRM",
    "oracle"    : "ORCL",
    "intel"     : "INTC",
    "amd"       : "AMD",
    "qualcomm"  : "QCOM",
    "visa"      : "V",
    "mastercard": "MA",
    "berkshire" : "BRK",
    "johnson"   : "JNJ",
    "walmart"   : "WMT",
    "disney"    : "DIS",
    "coca cola" : "KO",
    "pepsi"     : "PEP",
    "nike"      : "NKE",
    "twitter"   : "X",
    "bitcoin"   : "BTC",
    "ethereum"  : "ETH",
    "crypto"    : "CRYPTO",
    "openai"    : "OPENAI",
}


def get_recognised_ticker(question: str) -> Optional[str]:
    """
    Check if the question mentions a recognised but unsupported company.
    Returns the ticker/name if found, None otherwise.
    Used to generate a friendly redirect message in query.py.
    """
    question_lower = question.lower()
    for name, ticker in RECOGNISED_BUT_UNSUPPORTED.items():
        if name in question_lower:
            return ticker
    return None


# ── Output schema ─────────────────────────────────────────────────────────────

class ClassifierOutput(BaseModel):
    query_type: str = Field(
        ...,
        description="One of: SINGLE, COMPARE, FOLLOWUP, GENERAL"
    )
    tickers   : List[str] = Field(
        ...,
        description=(
            "List of resolved ticker symbols e.g. ['GME', 'NVDA']. "
            "For FOLLOWUP queries, resolve references like 'the other one' "
            "or 'both of them' using the conversation history. "
            "Return empty list for GENERAL queries."
        )
    )
    reasoning : str = Field(
        ...,
        description="One sentence explaining why this classification was chosen."
    )


# ── Classifier prompt ─────────────────────────────────────────────────────────

CLASSIFIER_SYSTEM = f"""You are a query classifier for a financial intelligence system.

Your job is to:
1. Determine the query type (SINGLE, COMPARE, FOLLOWUP, GENERAL)
2. Extract or resolve all stock tickers mentioned or implied

SUPPORTED TICKERS ONLY: {', '.join(sorted(KNOWN_TICKERS))}

COMPANY NAME MAP (use this to resolve company names to tickers):
  Apple / iPhone / Tim Cook    → AAPL
  Boeing                       → BA
  GameStop / Roaring Kitty     → GME
  JPMorgan / JP Morgan         → JPM
  NextEra / NEE                → NEE
  Nvidia / Jensen Huang        → NVDA
  Pfizer                       → PFE
  Palantir / Alex Karp         → PLTR
  Tesla / Elon / Cybertruck    → TSLA
  ExxonMobil / Exxon           → XOM

QUERY TYPE RULES:
  SINGLE   → question about exactly ONE supported company
  COMPARE  → comparing TWO OR MORE supported companies
             (words like: compare, vs, versus, better, worse, which one,
              difference, rank, best, worst among listed companies)
  FOLLOWUP → references previous conversation
             (words like: the other one, both, that stock, the first one,
              their, them, it, same, as well, too, also, what about)
  GENERAL  → no specific supported company mentioned

FOLLOWUP RESOLUTION RULES:
  - "the other one"  → ticker NOT mentioned this turn but in last turn
  - "both of them"   → ALL tickers from last turn
  - "the first one"  → first ticker from last turn
  - "the second one" → second ticker from last turn
  - "them" / "they"  → ALL tickers from last turn
  - "it" / "that stock" → last single ticker discussed

CRITICAL: Only return tickers from the SUPPORTED list above.
If a company is mentioned that is NOT supported (e.g. Amazon, Microsoft,
Google, Meta), return an EMPTY tickers list — do NOT invent tickers.
"""


def classify_query(question: str, history_text: str) -> ClassifierOutput:
    """
    Classify a user question and resolve tickers using conversation history.

    Args:
        question     : The user's current question
        history_text : Formatted conversation history from session.py

    Returns:
        ClassifierOutput with query_type, tickers, and reasoning
    """
    user_message = f"""CONVERSATION HISTORY:
{history_text}

CURRENT QUESTION: "{question}"

Classify this question and extract/resolve all relevant tickers."""

    response = _client.beta.chat.completions.parse(
        model="gpt-4.1-mini",  # Fast and cheap for classification
        messages=[
            {"role": "system", "content": CLASSIFIER_SYSTEM},
            {"role": "user",   "content": user_message},
        ],
        response_format=ClassifierOutput,
        temperature=0,  # Deterministic classification
    )

    result = response.choices[0].message.parsed

    # Sanitize — only return tickers we actually support
    result.tickers = [t.upper() for t in result.tickers if t.upper() in KNOWN_TICKERS]

    print(f"[Classifier] Type: {result.query_type} | "
          f"Tickers: {result.tickers} | "
          f"Reason: {result.reasoning}")

    return result