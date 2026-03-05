"""Models for per-company fundamental evaluation (Phase 2).

These complement the signals models — while signals are macro-level boolean
decisions, evaluations are per-stock fundamental assessments produced by the
Gemini evaluator agent.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CompanyEvaluation(BaseModel):
    """Structured output from the per-company Gemini evaluation."""

    ticker: str
    fundamental_score: float = Field(ge=1, le=10, description="Overall fundamental quality 1-10")
    ai_relevance_score: float = Field(ge=1, le=10, description="How central is this company to the AI build-out 1-10")
    moat_score: float = Field(ge=1, le=10, description="Competitive moat durability 1-10")
    management_score: float = Field(ge=1, le=10, description="Management quality & capital allocation 1-10")
    composite_score: float = Field(ge=1.0, le=10.0, description="Weighted average of all sub-scores")

    tier_appropriate: bool = True
    suggested_tier_change: str | None = None  # None = keep current, else "T1"-"T4"

    biggest_risk: str = ""
    biggest_catalyst: str = ""
    conviction_level: str = "medium"  # "high" | "medium" | "low"
    reasoning: str = ""
    earnings_trend: str = "stable"  # "improving" | "stable" | "deteriorating"

    timestamp: datetime = Field(default_factory=datetime.now)
    model_used: str = ""  # which Gemini model produced this
    data_quality: str = "full"  # "full" | "partial" | "minimal"
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationBatch(BaseModel):
    """A batch of evaluations (e.g. full universe scan)."""

    evaluations: list[CompanyEvaluation] = []
    timestamp: datetime = Field(default_factory=datetime.now)
    signal_color_at_time: str = ""  # global signal when scan ran
    errors: dict[str, str] = Field(default_factory=dict)  # ticker -> error message

    @property
    def successful(self) -> list[CompanyEvaluation]:
        return self.evaluations

    @property
    def success_rate(self) -> float:
        total = len(self.evaluations) + len(self.errors)
        return len(self.evaluations) / total if total > 0 else 0.0

    def get(self, ticker: str) -> CompanyEvaluation | None:
        for e in self.evaluations:
            if e.ticker.upper() == ticker.upper():
                return e
        return None

    def top_n(self, n: int = 5, key: str = "composite_score") -> list[CompanyEvaluation]:
        """Return top N evaluations sorted by a given score field (descending)."""
        return sorted(
            self.evaluations,
            key=lambda e: getattr(e, key, 0),
            reverse=True,
        )[:n]

    def tier_mismatches(self) -> list[CompanyEvaluation]:
        """Return evaluations where the AI suggests a tier change."""
        return [e for e in self.evaluations if not e.tier_appropriate]
