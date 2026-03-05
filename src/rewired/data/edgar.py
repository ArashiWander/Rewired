"""SEC EDGAR 8-K filing fetcher for earnings press releases.

Fetches recent 8-K filings from SEC EDGAR to ground the Gemini CAPEX analysis
with real earnings data instead of relying on model training data.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta
from html import unescape
from pathlib import Path

import requests

from rewired import get_data_dir

# SEC requires a descriptive User-Agent header
_USER_AGENT = "Rewired-Index/0.1 (personal project)"
_HEADERS = {"User-Agent": _USER_AGENT, "Accept-Encoding": "gzip, deflate"}

# Ticker -> CIK mapping for hyperscalers
_TICKER_CIK = {
    "MSFT": "0000789019",
    "GOOGL": "0001652044",
    "AMZN": "0001018724",
    "META": "0001326801",
}

_CACHE_HOURS = 24  # Filings don't change; cache for 24h
_MAX_CHARS_PER_FILING = 2000
_SEC_RATE_LIMIT_SECONDS = 0.15  # SEC asks for max 10 req/sec


def fetch_earnings_filings(
    tickers: list[str] | None = None,
    max_per_ticker: int = 2,
) -> str:
    """Fetch recent 8-K earnings filings from SEC EDGAR.

    Returns concatenated text of recent earnings press releases,
    suitable for injection into an LLM prompt.
    """
    if tickers is None:
        tickers = list(_TICKER_CIK.keys())

    # Check cache first
    cached = _load_cache()
    if cached is not None:
        return cached

    sections = []
    for ticker in tickers:
        cik = _TICKER_CIK.get(ticker)
        if not cik:
            continue
        try:
            text = _fetch_recent_8k(cik, ticker, max_per_ticker)
            if text:
                sections.append(f"=== {ticker} Recent 8-K Filings ===\n{text}")
        except Exception:
            sections.append(f"=== {ticker} ===\n[Filing data unavailable]")
        time.sleep(_SEC_RATE_LIMIT_SECONDS)

    result = "\n\n".join(sections) if sections else "[No SEC filings retrieved]"
    _save_cache(result)
    return result


def _fetch_recent_8k(cik: str, ticker: str, max_filings: int) -> str:
    """Fetch recent 8-K filing text for a single company."""
    # Step 1: Get recent filings list from submissions endpoint
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    resp = requests.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    dates = recent.get("filingDate", [])
    primary_docs = recent.get("primaryDocument", [])

    # Filter to 8-K filings from last 6 months
    cutoff = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
    eight_k_filings = []
    for i, form in enumerate(forms):
        if form == "8-K" and i < len(dates) and dates[i] >= cutoff:
            eight_k_filings.append({
                "accession": accessions[i].replace("-", ""),
                "date": dates[i],
                "doc": primary_docs[i] if i < len(primary_docs) else "",
            })
        if len(eight_k_filings) >= max_filings:
            break

    if not eight_k_filings:
        return ""

    # Step 2: Fetch the actual filing documents
    texts = []
    for filing in eight_k_filings:
        time.sleep(_SEC_RATE_LIMIT_SECONDS)
        try:
            doc_url = (
                f"https://www.sec.gov/Archives/edgar/data/"
                f"{cik.lstrip('0')}/{filing['accession']}/{filing['doc']}"
            )
            doc_resp = requests.get(doc_url, headers=_HEADERS, timeout=15)
            doc_resp.raise_for_status()
            raw_text = _strip_html(doc_resp.text)
            # Truncate to keep prompt manageable
            if len(raw_text) > _MAX_CHARS_PER_FILING:
                raw_text = raw_text[:_MAX_CHARS_PER_FILING] + "... [truncated]"
            texts.append(f"[{filing['date']}]\n{raw_text}")
        except Exception:
            continue

    return "\n---\n".join(texts)


def _strip_html(html: str) -> str:
    """Strip HTML tags and clean up text from SEC filings."""
    # Remove script/style blocks
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode HTML entities
    text = unescape(text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Remove common SEC boilerplate markers
    text = re.sub(r"UNITED STATES SECURITIES AND EXCHANGE COMMISSION.*?FORM 8-K", "", text, flags=re.DOTALL)
    return text.strip()


# ── Cache ────────────────────────────────────────────────────────────────────


def _cache_path() -> Path:
    return get_data_dir() / "edgar_cache.json"


def _load_cache() -> str | None:
    """Load cached EDGAR text if still fresh."""
    path = _cache_path()
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            cache = json.load(f)
        cached_at = datetime.fromisoformat(cache["timestamp"])
        if datetime.now() - cached_at < timedelta(hours=_CACHE_HOURS):
            return cache["text"]
    except (json.JSONDecodeError, KeyError, ValueError, OSError):
        pass
    return None


def _save_cache(text: str) -> None:
    """Save EDGAR text to cache."""
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"timestamp": datetime.now().isoformat(), "text": text}, f)
