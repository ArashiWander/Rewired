"""Macro signal calculator - delegates to boolean rules engine."""

from __future__ import annotations

from datetime import datetime

from rewired.data.macro import get_macro_readings
from rewired.models.signals import (
    CategorySignal,
    SignalCategory,
    SignalColor,
)
from rewired.signals.rules import evaluate_macro_rules


def calculate_macro_signal() -> CategorySignal:
    """Calculate macro signal using deterministic boolean rules."""
    readings = get_macro_readings()
    now = datetime.now()

    if not readings:
        return CategorySignal(
            category=SignalCategory.MACRO,
            readings=[],
            composite_color=SignalColor.ORANGE,
            timestamp=now,
            explanation="No macro data available - defaulting to ORANGE (defensive)",
            rule_triggered="DATA_MISSING",
        )

    color, explanation = evaluate_macro_rules(readings)

    return CategorySignal(
        category=SignalCategory.MACRO,
        readings=readings,
        composite_color=color,
        timestamp=now,
        explanation=explanation,
        rule_triggered=explanation.split(":")[0] if ":" in explanation else color.value,
    )
