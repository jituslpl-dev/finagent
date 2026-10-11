"""SQL, lexical RAG and financial API adapters with as-of provenance."""

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Protocol

import httpx
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from finagent.retry import ToolUnavailable, TransientError
from finagent.schemas import Evidence


def evidence(kind: str, symbol: str, available: str, source: str, payload: dict) -> Evidence:
    canonical = json.dumps([kind, symbol, available, source, payload], sort_keys=True)
    return Evidence(
        id=hashlib.sha256(canonical.encode()).hexdigest()[:20],
        kind=kind,
        symbol=symbol,
        available_on=available,
        source=source,
        payload=payload,
    )


class ResearchTool(Protocol):
    def retrieve(self, symbol: str, as_of: date, question: str) -> list[Evidence]: ...


class SqlTool:
    """Only a parameterized allowlisted query; no arbitrary model-written SQL."""

    def __init__(self, database: Path):
        self.database = database.resolve()

    def retrieve(self, symbol: str, as_of: date, question: str = "") -> list[Evidence]:
        with closing(sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True)) as conn:
            conn.execute("PRAGMA query_only=ON")
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM fundamentals WHERE symbol=? AND available_on<=? ORDER BY period DESC LIMIT 2",
                (symbol, as_of.isoformat()),
            ).fetchall()
        return [
            evidence(
                "sql",
                symbol,
                r["available_on"],
                f"sqlite:fundamentals/{symbol}/{r['period']}",
                dict(r),
            )
            for r in rows
        ]


class DocumentTool:
    """Deterministic TF-IDF RAG: symbol/date filter precedes index construction."""

    def __init__(self, documents: Path):
        self.documents = json.loads(documents.read_text(encoding="utf-8"))

    def retrieve(self, symbol: str, as_of: date, question: str) -> list[Evidence]:
        eligible = [
            d
            for d in self.documents
            if d["symbol"] == symbol and date.fromisoformat(d["available_on"]) <= as_of
        ]
        if not eligible:
            return []
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
        matrix = vectorizer.fit_transform([d["text"] for d in eligible])
        scores = cosine_similarity(vectorizer.transform([question]), matrix)[0]
        order = sorted(range(len(eligible)), key=lambda i: (-scores[i], eligible[i]["id"]))
        return [
            evidence(
                "documents",
                symbol,
                eligible[i]["available_on"],
                eligible[i]["source"],
                {
                    "text": eligible[i]["text"],
                    "document_id": eligible[i]["id"],
                    "score": float(scores[i]),
                },
            )
            for i in order[:2]
            if scores[i] > 0
        ]


class FixtureMarketTool:
    def __init__(self, path: Path):
        self.quotes = json.loads(path.read_text(encoding="utf-8"))

    def retrieve(self, symbol: str, as_of: date, question: str = "") -> list[Evidence]:
        quote = self.quotes.get(symbol)
        if quote is None or date.fromisoformat(quote["date"]) > as_of:
            return []
        return [
            evidence(
                "market",
                symbol,
                quote["date"],
                "fictional:daily-close",
                {**quote, "currency": "USD"},
            )
        ]


class AlphaVantageTool:
    """Daily close adapter. Throttling and server failures are retryable."""

    def __init__(self, api_key: str, client: httpx.Client | None = None):
        if not api_key:
            raise ValueError("ALPHA_VANTAGE_API_KEY is required")
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=20)
        self._owned = client is None

    def close(self):
        if self._owned:
            self.client.close()

    def retrieve(self, symbol: str, as_of: date, question: str = "") -> list[Evidence]:
        try:
            response = self.client.get(
                "https://www.alphavantage.co/query",
                params={
                    "function": "TIME_SERIES_DAILY",
                    "symbol": symbol,
                    "apikey": self.api_key,
                    "outputsize": "compact",
                },
            )
        except httpx.TransportError as exc:
            raise TransientError("financial provider transport failure") from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise TransientError("financial provider temporarily unavailable")
        if not response.is_success:
            raise ToolUnavailable("financial provider rejected request")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ToolUnavailable("financial provider returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ToolUnavailable("financial provider returned invalid object")
        if "Note" in payload or "Information" in payload:
            raise TransientError("financial provider quota or entitlement message")
        series = payload.get("Time Series (Daily)")
        if not isinstance(series, dict):
            raise ToolUnavailable("financial provider returned no daily series")
        try:
            eligible = sorted((d for d in series if date.fromisoformat(d) <= as_of), reverse=True)
        except (ValueError, TypeError) as exc:
            raise ToolUnavailable("financial provider returned invalid dates") from exc
        if not eligible:
            return []
        selected = eligible[0]
        import math

        try:
            price = float(series[selected]["4. close"])
            if not math.isfinite(price) or price <= 0:
                raise ValueError("invalid close")
        except (ValueError, KeyError, TypeError) as exc:
            raise ToolUnavailable("financial provider returned invalid close") from exc
        return [
            evidence(
                "market",
                symbol,
                selected,
                "https://www.alphavantage.co/query:TIME_SERIES_DAILY",
                {
                    "date": selected,
                    "close": price,
                    "adjusted": False,
                    "currency": "provider quote currency (unspecified)",
                    "historical_revision_possible": True,
                },
            )
        ]
