"""Signal models: SignalColor, SignalReading, CategorySignal, CompositeSignal."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class SignalColor(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    ORANGE = "orange"
    RED = "red"


# Numeric scores for weighted averaging (higher = better)
# Blueprint convention: RED=1pt, ORANGE=2pts, YELLOW=3pts, GREEN=4pts
SIGNAL_SCORES: dict[SignalColor, float] = {
    SignalColor.GREEN: 4.0,
    SignalColor.YELLOW: 3.0,
    SignalColor.ORANGE: 2.0,
    SignalColor.RED: 1.0,
}


def score_to_color(score: float) -> SignalColor:
    """Convert a numeric score back to a signal color.

    Higher scores = better conditions (blueprint convention):
      >=3.5 GREEN | >=2.5 YELLOW | >=1.5 ORANGE | <1.5 RED
    """
    if score >= 3.5:
        return SignalColor.GREEN
    if score >= 2.5:
        return SignalColor.YELLOW
    if score >= 1.5:
        return SignalColor.ORANGE
    return SignalColor.RED


class CircuitBreakerError(Exception):
    """Raised when critical data is missing and the pipeline must halt."""

    def __init__(self, category: str, missing_metrics: list[str], message: str = ""):
        self.category = category
        self.missing_metrics = missing_metrics
        super().__init__(message or f"Circuit breaker: {category} missing {missing_metrics}")


class DataQuality(BaseModel):
    """Tracks data freshness and availability for a single metric."""
    metric_name: str
    status: str  # "ok" | "missing" | "stale" | "error"
    last_fetched: datetime | None = None
    error_detail: str = ""


class SignalCategory(str, Enum):
    MACRO = "macro"
    SENTIMENT = "sentiment"
    AI_HEALTH = "ai_health"


class SignalReading(BaseModel):
    """A single signal metric reading."""
    name: str
    value: float
    color: SignalColor
    timestamp: datetime
    source: str
    detail: str = ""
    metadata: dict[str, Any] = {}


class CategorySignal(BaseModel):
    """Composite signal for one category."""
    category: SignalCategory
    readings: list[SignalReading]
    composite_color: SignalColor
    timestamp: datetime
    explanation: str
    data_quality: list[DataQuality] = []
    rule_triggered: str = ""


class CompositeSignal(BaseModel):
    """The overall traffic light across all three categories."""
    categories: dict[SignalCategory, CategorySignal]
    overall_color: SignalColor
    timestamp: datetime
    summary: str
    veto_active: bool = False
    composite_transparency: dict = {}


# ── Signal color ordering (for hysteresis comparisons) ───────────────────

_COLOR_RANK: dict[SignalColor, int] = {
    SignalColor.RED: 0,
    SignalColor.ORANGE: 1,
    SignalColor.YELLOW: 2,
    SignalColor.GREEN: 3,
}


def color_is_better(a: SignalColor, b: SignalColor) -> bool:
    """Return True if *a* is strictly better (less defensive) than *b*."""
    return _COLOR_RANK[a] > _COLOR_RANK[b]


def color_is_worse(a: SignalColor, b: SignalColor) -> bool:
    """Return True if *a* is strictly worse (more defensive) than *b*."""
    return _COLOR_RANK[a] < _COLOR_RANK[b]


# ── LLM CAPEX extraction (strict Pydantic confinement) ──────────────────

from pydantic import Field  # noqa: E402 (grouped import)


class CompanyCapexData(BaseModel):
    """Strict schema for per-company CAPEX data extracted by LLM."""
    capex_absolute_bn: float = Field(
        ..., description="Absolute CapEx in billions USD. Must be a pure float.",
    )
    qoq_growth_pct: float = Field(
        ..., description="Quarter over Quarter growth percentage. E.g., 5.4",
    )
    yoy_growth_pct: float = Field(
        ..., description="Year over Year growth percentage. E.g., 22.1",
    )
    explicit_guidance_cut_mentioned: bool = Field(
        ...,
        description=(
            "True ONLY if management explicitly stated future infrastructure "
            "spend reduction. False if they are just 'optimizing'."
        ),
    )
    exact_capex_quote: str = Field(
        ..., description="Verbatim management quote regarding CapEx. Max 2 sentences.",
    )


class AIHealthExtraction(BaseModel):
    """Validated Gemini response for Big-4 CAPEX extraction."""
    MSFT: CompanyCapexData
    GOOGL: CompanyCapexData
    AMZN: CompanyCapexData
    META: CompanyCapexData


# ── Regime state persistence (hysteresis) ────────────────────────────────

from datetime import date as _date  # noqa: E402


class RegimeState(BaseModel):
    """Persisted in data/regime_state.json for 3-day hysteresis."""
    current_regime: SignalColor = SignalColor.YELLOW
    pending_upgrade: SignalColor | None = None
    consecutive_days: int = 0
    last_updated: _date = _date(1970, 1, 1)
