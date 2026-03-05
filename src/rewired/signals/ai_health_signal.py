"""AI structural health signal calculator - delegates to boolean rules engine."""

from __future__ import annotations

from datetime import datetime

from rewired.data.ai_health import get_ai_health_readings
from rewired.models.signals import (
    CategorySignal,
    SignalCategory,
    SignalColor,
)
from rewired.signals.rules import evaluate_ai_health_rules


def calculate_ai_health_signal() -> CategorySignal:
    """Calculate AI health signal using deterministic boolean rules."""
    readings = get_ai_health_readings()
    now = datetime.now()

    if not readings:
        return CategorySignal(
            category=SignalCategory.AI_HEALTH,
            readings=[],
            composite_color=SignalColor.ORANGE,
            timestamp=now,
            explanation="No AI health data available - defaulting to ORANGE (defensive)",
            rule_triggered="DATA_MISSING",
        )

    color, explanation = evaluate_ai_health_rules(readings)

    return CategorySignal(
        category=SignalCategory.AI_HEALTH,
        readings=readings,
        composite_color=color,
        timestamp=now,
        explanation=explanation,
        rule_triggered=explanation.split(":")[0] if ":" in explanation else color.value,
    )
