"""Sentiment signal calculator - delegates to boolean rules engine."""

from __future__ import annotations

from datetime import datetime

from rewired.data.sentiment import get_sentiment_readings
from rewired.models.signals import (
    CategorySignal,
    SignalCategory,
    SignalColor,
)
from rewired.signals.rules import evaluate_sentiment_rules


def calculate_sentiment_signal() -> CategorySignal:
    """Calculate sentiment signal using deterministic boolean rules."""
    readings = get_sentiment_readings()
    now = datetime.now()

    if not readings:
        return CategorySignal(
            category=SignalCategory.SENTIMENT,
            readings=[],
            composite_color=SignalColor.ORANGE,
            timestamp=now,
            explanation="No sentiment data available - defaulting to ORANGE (defensive)",
            rule_triggered="DATA_MISSING",
        )

    color, explanation = evaluate_sentiment_rules(readings)

    return CategorySignal(
        category=SignalCategory.SENTIMENT,
        readings=readings,
        composite_color=color,
        timestamp=now,
        explanation=explanation,
        rule_triggered=explanation.split(":")[0] if ":" in explanation else color.value,
    )
