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
