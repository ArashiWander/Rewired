"""Sentiment signal calculator."""

from __future__ import annotations

from datetime import datetime

from rewired.data.sentiment import get_sentiment_readings
from rewired.models.signals import (
    CategorySignal,
    SignalCategory,
    SignalColor,
    SIGNAL_SCORES,
    score_to_color,
)


def calculate_sentiment_signal() -> CategorySignal:
    """Calculate composite sentiment signal."""
    readings = get_sentiment_readings()
    now = datetime.now()

    if not readings:
        return CategorySignal(
            category=SignalCategory.SENTIMENT,
            readings=[],
            composite_color=SignalColor.YELLOW,
            timestamp=now,
            explanation="No sentiment data available",
        )

    weighted_score = sum(SIGNAL_SCORES[r.color] for r in readings) / len(readings)
    composite = score_to_color(weighted_score)

    worst = max(readings, key=lambda r: SIGNAL_SCORES[r.color])
    explanation = worst.detail

    return CategorySignal(
        category=SignalCategory.SENTIMENT,
        readings=readings,
        composite_color=composite,
        timestamp=now,
        explanation=explanation,
    )
