"""AI structural health signal calculator."""

from __future__ import annotations

from datetime import datetime

from rewired.data.ai_health import get_ai_health_readings
from rewired.models.signals import (
    CategorySignal,
    SignalCategory,
    SignalColor,
    SIGNAL_SCORES,
    score_to_color,
)


def calculate_ai_health_signal() -> CategorySignal:
    """Calculate composite AI health signal."""
    readings = get_ai_health_readings()
    now = datetime.now()

    if not readings:
        return CategorySignal(
            category=SignalCategory.AI_HEALTH,
            readings=[],
            composite_color=SignalColor.YELLOW,
            timestamp=now,
            explanation="No AI health data available",
        )

    weighted_score = sum(SIGNAL_SCORES[r.color] for r in readings) / len(readings)
    composite = score_to_color(weighted_score)

    worst = max(readings, key=lambda r: SIGNAL_SCORES[r.color])
    explanation = worst.detail

    return CategorySignal(
        category=SignalCategory.AI_HEALTH,
        readings=readings,
        composite_color=composite,
        timestamp=now,
        explanation=explanation,
    )
