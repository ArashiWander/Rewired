"""Signal models: SignalColor, SignalReading, CategorySignal, CompositeSignal."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class SignalColor(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    ORANGE = "orange"
    RED = "red"


# Numeric scores for weighted averaging
SIGNAL_SCORES = {
    SignalColor.GREEN: 1.0,
    SignalColor.YELLOW: 2.0,
    SignalColor.ORANGE: 3.0,
    SignalColor.RED: 4.0,
}


def score_to_color(score: float) -> SignalColor:
    """Convert a numeric score back to a signal color."""
    if score <= 1.5:
        return SignalColor.GREEN
    if score <= 2.5:
        return SignalColor.YELLOW
    if score <= 3.5:
        return SignalColor.ORANGE
    return SignalColor.RED


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


class CategorySignal(BaseModel):
    """Composite signal for one category."""
    category: SignalCategory
    readings: list[SignalReading]
    composite_color: SignalColor
    timestamp: datetime
    explanation: str


class CompositeSignal(BaseModel):
    """The overall traffic light across all three categories."""
    categories: dict[SignalCategory, CategorySignal]
    overall_color: SignalColor
    timestamp: datetime
    summary: str
