"""P5.3: Config validation tests — verify production configs and reject bad ones."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rewired import get_config_dir
from rewired.models.config import (
    PortfolioConfig,
    SignalRulesConfig,
    load_and_validate_portfolio,
    load_and_validate_signals,
)


class TestProductionConfigs:
    """Verify the actual YAML config files in config/ are valid."""

    def test_portfolio_yaml_is_valid(self):
        config = load_and_validate_portfolio(get_config_dir())
        assert config.cash_floors["green"] > 0
        assert config.cash_floors["red"] > config.cash_floors["green"]
        assert sum(config.tier_ratios.values()) <= 1.0

    def test_signals_yaml_is_valid(self):
        config = load_and_validate_signals(get_config_dir())
        assert abs(sum(config.weights.values()) - 1.0) < 0.01
        assert config.weights["ai_health"] >= config.weights["macro"]


class TestPortfolioConfigValidation:
    """Test that malformed portfolio configs are rejected."""

    def test_invalid_layer_key_rejected(self):
        with pytest.raises(ValidationError):
            PortfolioConfig(
                layer_budgets={"L1": 0.2, "L99": 0.1},
                cash_floors={"green": 0.05, "yellow": 0.07, "orange": 0.10, "red": 0.18},
                tier_ratios={"T1": 0.5, "T2": 0.3},
            )

    def test_missing_cash_floor_color_rejected(self):
        with pytest.raises(ValidationError):
            PortfolioConfig(
                layer_budgets={"L1": 0.2},
                cash_floors={"green": 0.05, "yellow": 0.07},  # missing orange, red
                tier_ratios={"T1": 0.5},
            )

    def test_non_monotonic_cash_floors_rejected(self):
        with pytest.raises(ValidationError):
            PortfolioConfig(
                layer_budgets={"L1": 0.2},
                cash_floors={"green": 0.20, "yellow": 0.07, "orange": 0.10, "red": 0.18},
                tier_ratios={"T1": 0.5},
            )

    def test_tier_ratios_exceeding_1_rejected(self):
        with pytest.raises(ValidationError):
            PortfolioConfig(
                layer_budgets={"L1": 0.2},
                cash_floors={"green": 0.05, "yellow": 0.07, "orange": 0.10, "red": 0.18},
                tier_ratios={"T1": 0.6, "T2": 0.5},  # sum > 1.0
            )


class TestSignalRulesConfigValidation:
    """Test that malformed signal configs are rejected."""

    def test_weights_not_summing_to_1_rejected(self):
        with pytest.raises(ValidationError):
            SignalRulesConfig(
                weights={"macro": 0.5, "sentiment": 0.5, "ai_health": 0.5},
            )

    def test_invalid_weight_category_rejected(self):
        with pytest.raises(ValidationError):
            SignalRulesConfig(
                weights={"macro": 0.3, "sentiment": 0.2, "moon_phase": 0.5},
            )
