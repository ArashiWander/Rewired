"""Per-company Gemini evaluator agent.

Takes a stock from the universe, gathers FMP fundamental data, and sends it
through Gemini with a structured JSON prompt to produce a ``CompanyEvaluation``.

This module follows the project's **Cold Determinism** philosophy:
- temperature=0, JSON mode, retry with penalty prompt
- all prompts come from ``agent/prompts.py``
- missing data degrades gracefully (never crashes)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from rewired.agent.gemini import generate, is_configured
from rewired.agent.prompts import COMPANY_EVALUATE, SYSTEM_EVALUATOR
from rewired.models.evaluation import CompanyEvaluation, EvaluationBatch
from rewired.models.universe import (
    LAYER_NAMES,
    TIER_NAMES,
    Stock,
    Universe,
    load_universe,
)

logger = logging.getLogger(__name__)


# ── single-stock evaluation ──────────────────────────────────────────────


def evaluate_stock(stock: Stock) -> CompanyEvaluation:
    """Evaluate a single stock using FMP data + Gemini.

    Returns a fully-populated ``CompanyEvaluation``.  On Gemini failure or
    missing data, returns a conservative default rather than raising.
    """
    if not is_configured():
        return _default_evaluation(stock, reason="Gemini not configured")

    financial_data = _gather_financials(stock.ticker)
    earnings_data = _gather_earnings(stock.ticker)
    metrics_data = _gather_metrics(stock.ticker)

    data_quality = _assess_data_quality(financial_data, earnings_data, metrics_data)

    prompt = COMPANY_EVALUATE.format(
        ticker=stock.ticker,
        name=stock.name,
        layer=stock.layer.value,
        layer_name=LAYER_NAMES.get(stock.layer, ""),
        tier=stock.tier.value,
        tier_name=TIER_NAMES.get(stock.tier, ""),
        notes=stock.notes,
        financial_data=financial_data or "[No financial data available]",
        earnings_data=earnings_data or "[No earnings data available]",
        metrics_data=metrics_data or "[No metrics available]",
    )

    raw = generate(
        prompt,
        system_instruction=SYSTEM_EVALUATOR,
        json_output=True,
        max_retries=2,
    )

    return _parse_evaluation(raw, stock, data_quality)


def evaluate_stock_by_ticker(ticker: str) -> CompanyEvaluation:
    """Convenience: resolve ticker from universe, then evaluate."""
    uni = load_universe()
    stock = uni.get_stock(ticker.upper())
    if stock is None:
        return CompanyEvaluation(
            ticker=ticker.upper(),
            fundamental_score=5.0,
            ai_relevance_score=5.0,
            moat_score=5.0,
            management_score=5.0,
            composite_score=5.0,
            reasoning=f"{ticker} is not in the Rewired Index universe.",
            data_quality="minimal",
        )
    return evaluate_stock(stock)


# ── batch evaluation ─────────────────────────────────────────────────────


def evaluate_universe(
    universe: Universe | None = None,
    tickers: list[str] | None = None,
) -> EvaluationBatch:
    """Evaluate all stocks (or a subset) in the universe.

    Parameters
    ----------
    universe:
        Pre-loaded universe.  Loaded from config if ``None``.
    tickers:
        If given, only evaluate these tickers.  Otherwise evaluate all.

    Returns
    -------
    An ``EvaluationBatch`` with successful evaluations and any errors.
    """
    if universe is None:
        universe = load_universe()

    stocks = universe.stocks
    if tickers:
        upper = {t.upper() for t in tickers}
        stocks = [s for s in stocks if s.ticker.upper() in upper]

    batch = EvaluationBatch(timestamp=datetime.now())
    for stock in stocks:
        try:
            ev = evaluate_stock(stock)
            batch.evaluations.append(ev)
        except Exception as exc:
            logger.warning("Evaluation failed for %s: %s", stock.ticker, exc)
            batch.errors[stock.ticker] = str(exc)

    return batch


# ── data gathering (FMP) ─────────────────────────────────────────────────


def _gather_financials(ticker: str) -> str:
    """Gather income + cash-flow summaries from FMP as text."""
    try:
        from rewired.data.fmp import get_income_statement, get_cash_flow

        income = get_income_statement(ticker, period="quarter", limit=4)
        cf = get_cash_flow(ticker, period="quarter", limit=4)

        if not income and not cf:
            return ""

        lines: list[str] = []
        if income:
            lines.append("INCOME (last 4 quarters):")
            for stmt in income[:4]:
                lines.append(
                    f"  {stmt.get('date', '?')}: "
                    f"Rev={_fmt_num(stmt.get('revenue'))} "
                    f"GP={_fmt_num(stmt.get('grossProfit'))} "
                    f"OpInc={_fmt_num(stmt.get('operatingIncome'))} "
                    f"NI={_fmt_num(stmt.get('netIncome'))}"
                )
        if cf:
            lines.append("CASH FLOW (last 4 quarters):")
            for stmt in cf[:4]:
                lines.append(
                    f"  {stmt.get('date', '?')}: "
                    f"OpCF={_fmt_num(stmt.get('operatingCashFlow'))} "
                    f"CAPEX={_fmt_num(stmt.get('capitalExpenditure'))} "
                    f"FCF={_fmt_num(stmt.get('freeCashFlow'))}"
                )
        return "\n".join(lines)
    except Exception:
        return ""


def _gather_earnings(ticker: str) -> str:
    """Gather earnings surprise data from FMP as text."""
    try:
        from rewired.data.fmp import get_earnings_surprises

        surprises = get_earnings_surprises(ticker)
        if not surprises:
            return ""

        lines = ["EARNINGS SURPRISES (recent):"]
        for s in surprises[:4]:
            actual = s.get("actualEarningResult", "?")
            est = s.get("estimatedEarning", "?")
            date = s.get("date", "?")
            lines.append(f"  {date}: Actual={actual} Est={est}")
        return "\n".join(lines)
    except Exception:
        return ""


def _gather_metrics(ticker: str) -> str:
    """Gather key metrics / ratios from FMP as text."""
    try:
        from rewired.data.fmp import get_key_metrics, get_financial_ratios

        metrics = get_key_metrics(ticker, period="quarter", limit=2)
        ratios = get_financial_ratios(ticker, period="quarter", limit=2)

        if not metrics and not ratios:
            return ""

        lines: list[str] = []
        if metrics:
            m = metrics[0]  # most recent
            lines.append(
                f"PE={m.get('peRatio', '?')} "
                f"PB={m.get('pbRatio', '?')} "
                f"EV/EBITDA={m.get('enterpriseValueOverEBITDA', '?')} "
                f"FCF-yield={m.get('freeCashFlowYield', '?')} "
                f"ROE={m.get('roe', '?')} "
                f"ROIC={m.get('roic', '?')}"
            )
        if ratios:
            r = ratios[0]
            lines.append(
                f"Gross-Margin={r.get('grossProfitMargin', '?')} "
                f"Op-Margin={r.get('operatingProfitMargin', '?')} "
                f"Net-Margin={r.get('netProfitMargin', '?')} "
                f"Debt/Equity={r.get('debtEquityRatio', '?')}"
            )
        return "\n".join(lines)
    except Exception:
        return ""


def _fmt_num(val: Any) -> str:
    """Format a number for prompt readability (e.g. 1.23B, 456.7M)."""
    if val is None:
        return "N/A"
    try:
        n = float(val)
    except (TypeError, ValueError):
        return str(val)
    if abs(n) >= 1e12:
        return f"{n / 1e12:.2f}T"
    if abs(n) >= 1e9:
        return f"{n / 1e9:.2f}B"
    if abs(n) >= 1e6:
        return f"{n / 1e6:.1f}M"
    return f"{n:,.0f}"


def _assess_data_quality(
    financial_data: str,
    earnings_data: str,
    metrics_data: str,
) -> str:
    """Return 'full', 'partial', or 'minimal' based on data availability."""
    available = sum(1 for d in (financial_data, earnings_data, metrics_data) if d)
    if available >= 3:
        return "full"
    if available >= 1:
        return "partial"
    return "minimal"


# ── response parsing ─────────────────────────────────────────────────────


def _parse_evaluation(
    raw: str,
    stock: Stock,
    data_quality: str,
) -> CompanyEvaluation:
    """Parse Gemini JSON into a CompanyEvaluation, with fallback."""
    try:
        text = raw.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        if text.startswith("json"):
            text = text[4:].strip()

        data = json.loads(text)

        # Clamp scores to valid range
        def _score(key: str, default: float = 5.0) -> float:
            v = data.get(key, default)
            try:
                return max(1.0, min(10.0, float(v)))
            except (TypeError, ValueError):
                return default

        return CompanyEvaluation(
            ticker=stock.ticker,
            fundamental_score=_score("fundamental_score"),
            ai_relevance_score=_score("ai_relevance_score"),
            moat_score=_score("moat_score"),
            management_score=_score("management_score"),
            composite_score=_score("composite_score"),
            tier_appropriate=bool(data.get("tier_appropriate", True)),
            suggested_tier_change=data.get("suggested_tier_change"),
            biggest_risk=str(data.get("biggest_risk", ""))[:300],
            biggest_catalyst=str(data.get("biggest_catalyst", ""))[:300],
            conviction_level=_clamp_conviction(data.get("conviction_level", "medium")),
            reasoning=str(data.get("reasoning", ""))[:500],
            earnings_trend=_clamp_trend(data.get("earnings_trend", "stable")),
            data_quality=data_quality,
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        logger.warning("Failed to parse evaluation for %s: %s", stock.ticker, exc)
        return _default_evaluation(stock, reason=f"Parse error: {exc}", data_quality=data_quality)


def _default_evaluation(
    stock: Stock,
    reason: str = "",
    data_quality: str = "minimal",
) -> CompanyEvaluation:
    """Return a conservative neutral evaluation."""
    return CompanyEvaluation(
        ticker=stock.ticker,
        fundamental_score=5.0,
        ai_relevance_score=5.0,
        moat_score=5.0,
        management_score=5.0,
        composite_score=5.0,
        conviction_level="low",
        reasoning=reason or "Default evaluation — insufficient data or Gemini unavailable.",
        data_quality=data_quality,
    )


def _clamp_conviction(value: Any) -> str:
    v = str(value).lower().strip()
    if v in ("high", "medium", "low"):
        return v
    return "medium"


def _clamp_trend(value: Any) -> str:
    v = str(value).lower().strip()
    if v in ("improving", "stable", "deteriorating"):
        return v
    return "stable"
