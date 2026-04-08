"""Pydantic validation models for YAML configuration files.

These models validate config on load and fail fast on typos or missing
keys rather than silently producing wrong allocations at runtime.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, model_validator


# ── Portfolio Config ────────────────────────────────────────────────────────


class PortfolioConstraints(BaseModel):
    max_single_position_pct: float = 15.0
    min_position_eur: float = 10.0
    max_positions: int = 15
    rebalance_threshold_pct: float = 5.0


class PortfolioConfig(BaseModel):
    """Validated schema for config/portfolio.yaml."""

    total_capital_eur: float = 0.0
    layer_budgets: dict[str, float]
    cash_floors: dict[str, float]
    tier_ratios: dict[str, float]
    constraints: PortfolioConstraints = PortfolioConstraints()

    @model_validator(mode="after")
    def _validate_keys(self) -> "PortfolioConfig":
        # Layer budgets must have valid layer keys
        valid_layers = {"L1", "L2", "L3", "L4", "L5"}
        bad_layers = set(self.layer_budgets) - valid_layers
        if bad_layers:
            raise ValueError(f"Invalid layer budget keys: {bad_layers}. Valid: {valid_layers}")

        # Cash floors must map to valid signal colors
        valid_colors = {"green", "yellow", "orange", "red"}
        bad_colors = set(self.cash_floors) - valid_colors
        if bad_colors:
            raise ValueError(f"Invalid cash floor keys: {bad_colors}. Valid: {valid_colors}")

        # All signal colors must be present
        missing_colors = valid_colors - set(self.cash_floors)
        if missing_colors:
            raise ValueError(f"Missing cash floor entries: {missing_colors}")

        # Tier ratios must have valid tier keys
        valid_tiers = {"T1", "T2", "T3", "T4"}
        bad_tiers = set(self.tier_ratios) - valid_tiers
        if bad_tiers:
            raise ValueError(f"Invalid tier ratio keys: {bad_tiers}. Valid: {valid_tiers}")

        # Tier ratios should sum to <= 1.0
        total = sum(self.tier_ratios.values())
        if total > 1.0 + 1e-9:
            raise ValueError(f"Tier ratios sum to {total:.3f}, must be <= 1.0")

        # Cash floors must be monotonically escalating
        expected_order = ["green", "yellow", "orange", "red"]
        values = [self.cash_floors.get(c, 0.0) for c in expected_order]
        for i in range(len(values) - 1):
            if values[i] > values[i + 1]:
                raise ValueError(
                    f"Cash floors must be monotonically escalating: "
                    f"{expected_order[i]}={values[i]} > {expected_order[i+1]}={values[i+1]}"
                )

        return self

    @classmethod
    def from_yaml(cls, path: Path) -> "PortfolioConfig":
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        return cls.model_validate(raw)


# ── Signal Rules Config ─────────────────────────────────────────────────────


class MacroRules(BaseModel):
    red: dict[str, Any] = {}
    orange: dict[str, Any] = {}
    yellow: dict[str, Any] = {}
    green: dict[str, Any] = {}


class SentimentRules(BaseModel):
    red: dict[str, Any] = {}
    orange: dict[str, Any] = {}
    yellow: dict[str, Any] = {}
    green: dict[str, Any] = {}


class AIHealthRules(BaseModel):
    red: dict[str, Any] = {}
    orange: dict[str, Any] = {}
    yellow: dict[str, Any] = {}
    green: dict[str, Any] = {}


class MacroConfig(BaseModel):
    data_sources: dict[str, Any] = {}
    rules: MacroRules = MacroRules()


class SentimentConfig(BaseModel):
    data_sources: dict[str, Any] = {}
    rules: SentimentRules = SentimentRules()


class AIHealthConfig(BaseModel):
    data_sources: dict[str, Any] = {}
    rules: AIHealthRules = AIHealthRules()


class SignalRulesConfig(BaseModel):
    """Validated schema for config/signals.yaml."""

    weights: dict[str, float]
    macro: MacroConfig = MacroConfig()
    sentiment: SentimentConfig = SentimentConfig()
    ai_health: AIHealthConfig = AIHealthConfig()

    @model_validator(mode="after")
    def _validate_weights(self) -> "SignalRulesConfig":
        valid_categories = {"macro", "sentiment", "ai_health"}
        bad_cats = set(self.weights) - valid_categories
        if bad_cats:
            raise ValueError(f"Invalid weight categories: {bad_cats}. Valid: {valid_categories}")

        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Signal weights must sum to 1.0, got {total:.3f}")

        return self

    @classmethod
    def from_yaml(cls, path: Path) -> "SignalRulesConfig":
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        return cls.model_validate(raw)


# ── Convenience loader ──────────────────────────────────────────────────────


def load_and_validate_portfolio(config_dir: Path) -> PortfolioConfig:
    """Load and validate portfolio.yaml, raising on any schema error."""
    return PortfolioConfig.from_yaml(config_dir / "portfolio.yaml")


def load_and_validate_signals(config_dir: Path) -> SignalRulesConfig:
    """Load and validate signals.yaml, raising on any schema error."""
    return SignalRulesConfig.from_yaml(config_dir / "signals.yaml")
