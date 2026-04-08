"""2D Layer × Tier constraint solver with 5-phase allocation engine + hedge protocols.

Replaces the old 1D tier-based sizing.  The allocation flows through five phases:

  Phase 1 — Cash Floor: regime → minimum cash reserve (parked in XEON).
  Phase 2 — Static Layer Budgets: L1/L2/L3/L5 hard allocations.
  Phase 3 — L4 Dynamic Residual: L4 = Total − (Cash + Hedge + L1 + L2 + L3 + L5).
  Phase 4 — Intra-Layer Distribution: T1/T2 active, T3/T4 frozen at current.
  Phase 5 — Minimum Tolerance: |delta| < 0.5% → HOLD (anti-friction).
"""

from __future__ import annotations

import logging
from typing import Any

import yaml

from rewired import get_config_dir
from rewired.models.portfolio import PieAllocation, Portfolio, Suggestion
from rewired.models.signals import CompositeSignal, SignalColor
from rewired.models.universe import Layer, Tier, Universe, Stock

logger = logging.getLogger(__name__)

_HEDGE_TICKER = "DXS3.DE"  # Xtrackers S&P 500 Inverse Daily Swap (XETRA, EUR)
_CASH_TICKER = "XEON.DE"   # Xtrackers EUR Overnight Rate Swap (XETRA, EUR)


def _load_portfolio_config() -> dict:
    """Load and validate portfolio configuration."""
    from rewired.models.config import PortfolioConfig

    config_path = get_config_dir() / "portfolio.yaml"
    validated = PortfolioConfig.from_yaml(config_path)
    # Return as dict for backward compatibility with solver internals
    return validated.model_dump()


# ── 5-Phase L×T Solver ───────────────────────────────────────────────────


def calculate_suggestions(
    portfolio: Portfolio,
    universe: Universe,
    signal: CompositeSignal,
) -> list[Suggestion]:
    """Calculate position sizing suggestions via 2D L×T constraint solver."""
    config = _load_portfolio_config()
    regime = signal.overall_color
    total = portfolio.total_value_eur
    constraints = config.get("constraints", {})
    min_pos = constraints.get("min_position_eur", 10)

    # Build current positions map for T3/T4 freeze logic
    current_positions = {
        t: p.market_value_eur for t, p in portfolio.positions.items()
    }

    # Run the solver
    targets = _solve_lxt(config, universe, regime, total, current_positions)

    suggestions: list[Suggestion] = []
    freed_capital = 0.0

    # ── Generate sell suggestions ─────────────────────────────────────
    for stock in universe.stocks:
        target_eur = targets.get(stock.ticker, 0.0)
        pos = portfolio.positions.get(stock.ticker)
        if pos is None:
            continue
        delta = target_eur - pos.market_value_eur
        if delta < -min_pos:
            if target_eur <= 0:
                suggestions.append(Suggestion(
                    ticker=stock.ticker,
                    action="SELL",
                    amount_eur=round(pos.market_value_eur, 2),
                    reason=f"L{stock.layer.value}/T{stock.tier.value} target 0 @ {regime.value.upper()}",
                    priority=1,
                ))
                freed_capital += pos.market_value_eur
            else:
                suggestions.append(Suggestion(
                    ticker=stock.ticker,
                    action="SELL",
                    amount_eur=round(abs(delta), 2),
                    reason=f"Trim to L{stock.layer.value}/T{stock.tier.value} target @ {regime.value.upper()}",
                    priority=2,
                ))
                freed_capital += abs(delta)

    # ── Generate buy suggestions ──────────────────────────────────────
    available_cash = portfolio.cash_eur + freed_capital
    for stock in universe.stocks:
        target_eur = targets.get(stock.ticker, 0.0)
        pos = portfolio.positions.get(stock.ticker)
        current_eur = pos.market_value_eur if pos else 0.0
        delta = target_eur - current_eur
        if delta > min_pos:
            buy_amount = min(delta, available_cash)
            if buy_amount >= min_pos:
                suggestions.append(Suggestion(
                    ticker=stock.ticker,
                    action="BUY",
                    amount_eur=round(buy_amount, 2),
                    reason=f"L{stock.layer.value}/T{stock.tier.value} target @ {regime.value.upper()}",
                    priority=3,
                ))
                available_cash -= buy_amount

    # ── Hedge actions ─────────────────────────────────────────────────
    hedge_target = targets.get(_HEDGE_TICKER, 0.0)
    hedge_pos = portfolio.positions.get(_HEDGE_TICKER)
    hedge_current = hedge_pos.market_value_eur if hedge_pos else 0.0
    hedge_delta = hedge_target - hedge_current

    if hedge_delta > min_pos:
        suggestions.append(Suggestion(
            ticker=_HEDGE_TICKER,
            action="BUY",
            amount_eur=round(hedge_delta, 2),
            reason=f"Hedge deployment: {regime.value.upper()} regime",
            priority=2,
        ))
    elif hedge_delta < -min_pos:
        suggestions.append(Suggestion(
            ticker=_HEDGE_TICKER,
            action="SELL",
            amount_eur=round(abs(hedge_delta), 2),
            reason=f"Hedge unwind: regime improved to {regime.value.upper()}",
            priority=1,
        ))

    # ── XEON cash actions ─────────────────────────────────────────────
    xeon_target = targets.get(_CASH_TICKER, 0.0)
    xeon_pos = portfolio.positions.get(_CASH_TICKER)
    xeon_current = xeon_pos.market_value_eur if xeon_pos else 0.0
    xeon_delta = xeon_target - xeon_current

    if xeon_delta < -min_pos:
        # Sell XEON first to free capital for stock buys
        suggestions.append(Suggestion(
            ticker=_CASH_TICKER,
            action="SELL",
            amount_eur=round(abs(xeon_delta), 2),
            reason=f"Cash release: regime improved to {regime.value.upper()}",
            priority=1,
        ))
    elif xeon_delta > min_pos:
        # Buy XEON last — park remaining capital
        suggestions.append(Suggestion(
            ticker=_CASH_TICKER,
            action="BUY",
            amount_eur=round(xeon_delta, 2),
            reason=f"Cash parking: {regime.value.upper()} regime",
            priority=4,
        ))

    suggestions.sort(key=lambda s: s.priority)
    return suggestions


def _solve_lxt(
    config: dict,
    universe: Universe,
    regime: SignalColor,
    total: float,
    current_positions: dict[str, float] | None = None,
) -> dict[str, float]:
    """Run 5-phase L×T constraint solver. Returns {ticker: target_eur}.

    Also includes _HEDGE_TICKER and _CASH_TICKER allocations.
    When *current_positions* is provided, frozen tiers (T3/T4 under
    YELLOW/ORANGE/RED) are locked at their current market value instead
    of being liquidated.
    """
    if current_positions is None:
        current_positions = {}

    layer_budgets_cfg = config.get("layer_budgets", {})
    cash_floors = config.get("cash_floors", {})
    tier_ratios = config.get("tier_ratios", {})
    constraints = config.get("constraints", {})
    max_single_pct = constraints.get("max_single_position_pct", 15.0)

    # ── Hedge allocation (before cash floor, deducted from investable) ─
    hedge_pct = _hedge_pct(regime)
    hedge_target = total * hedge_pct

    # ── Phase 1: Cash Floor (parked in XEON) ──────────────────────────
    cash_pct = cash_floors.get(regime.value, 0.05)
    cash_target = total * cash_pct
    investable = total - cash_target - hedge_target

    # ── Freeze T3/T4: lock at current value, subtract from investable ─
    frozen_tiers = _frozen_tiers(regime)
    frozen_total = 0.0
    frozen_values: dict[str, float] = {}  # ticker → locked value
    for stock in universe.stocks:
        if stock.tier in frozen_tiers:
            held = current_positions.get(stock.ticker, 0.0)
            frozen_values[stock.ticker] = held
            frozen_total += held

    # Clamp: frozen positions can't exceed investable
    if frozen_total > investable:
        if frozen_total > 0:
            scale = investable / frozen_total
            for t in frozen_values:
                frozen_values[t] = round(frozen_values[t] * scale, 2)
            frozen_total = investable

    active_investable = max(0.0, investable - frozen_total)

    # ── Phase 2: Static Layer Budgets (from active_investable) ────────
    eligible_tiers = _eligible_tiers(regime)
    raw_budgets = {}
    for layer in (Layer.L1, Layer.L2, Layer.L3, Layer.L5):
        key = f"L{layer.value}"
        pct = layer_budgets_cfg.get(key, 0.0)
        raw_budgets[layer] = active_investable * pct

    static_sum = sum(raw_budgets.values())

    # ── Phase 3: L4 Dynamic Residual ──────────────────────────────────
    l4_budget = active_investable - static_sum
    if l4_budget < 0:
        deficit = abs(l4_budget)
        if static_sum > 0:
            for layer in (Layer.L1, Layer.L2, Layer.L3):
                share = raw_budgets[layer] / static_sum
                raw_budgets[layer] = max(0.0, raw_budgets[layer] - deficit * share)
        l4_budget = 0.0

    raw_budgets[Layer.L4] = l4_budget

    # ── Phase 4: Intra-Layer Distribution ─────────────────────────────
    targets: dict[str, float] = {}
    layer_surplus = 0.0

    for layer in Layer:
        budget = raw_budgets.get(layer, 0.0)
        layer_stocks = universe.get_by_layer(layer)

        if not layer_stocks:
            continue

        # Assign frozen stocks first
        for stock in layer_stocks:
            if stock.ticker in frozen_values:
                targets[stock.ticker] = round(frozen_values[stock.ticker], 2)

        active_layer_stocks = [
            s for s in layer_stocks if s.ticker not in frozen_values
        ]

        if not active_layer_stocks or budget <= 0:
            for s in active_layer_stocks:
                targets[s.ticker] = 0.0
            continue

        allocated_in_layer = 0.0
        for stock in active_layer_stocks:
            tier_key = f"T{stock.tier.value}"
            tier_ratio = tier_ratios.get(tier_key, 0.0)

            if stock.tier not in eligible_tiers:
                targets[stock.ticker] = 0.0
                continue

            cell_stocks = [
                s for s in active_layer_stocks
                if s.tier == stock.tier and s.tier in eligible_tiers
            ]
            n_cell = len(cell_stocks) if cell_stocks else 1

            alloc = budget * (tier_ratio / n_cell)

            cap = total * (stock.max_weight_pct / 100)
            if alloc > cap:
                layer_surplus += alloc - cap
                alloc = cap

            targets[stock.ticker] = round(alloc, 2)
            allocated_in_layer += alloc

        if allocated_in_layer < budget:
            layer_surplus += budget - allocated_in_layer

    # Surplus cascade: layer surplus → eligible L4 stocks
    if layer_surplus > 0:
        l4_stocks = [
            s for s in universe.stocks
            if s.layer == Layer.L4
            and s.tier in eligible_tiers
            and s.ticker not in frozen_values
        ]
        if l4_stocks:
            per_l4 = layer_surplus / len(l4_stocks)
            for s in l4_stocks:
                cap = total * (s.max_weight_pct / 100)
                current = targets.get(s.ticker, 0.0)
                room = max(0.0, cap - current)
                add = min(per_l4, room)
                targets[s.ticker] = round(current + add, 2)
                layer_surplus -= add

    # ── Instrument targets ────────────────────────────────────────────
    targets[_HEDGE_TICKER] = round(hedge_target, 2)
    targets[_CASH_TICKER] = round(cash_target, 2)

    return targets


def _hedge_pct(regime: SignalColor) -> float:
    """Return hedge allocation percentage by regime.

    GREEN/YELLOW → 0% (no hedge).
    ORANGE       → 6% (tactical hedge).
    RED          → 10% (crisis hedge escalation).
    """
    if regime == SignalColor.ORANGE:
        return 0.06
    if regime == SignalColor.RED:
        return 0.10
    return 0.0


def _frozen_tiers(regime: SignalColor) -> set[Tier]:
    """Return tiers frozen at current value (no new buys, no forced sells).

    GREEN  → nothing frozen.
    YELLOW → T3/T4 frozen (pause new positions).
    ORANGE → T3/T4 frozen (monotonic escalation).
    RED    → T3/T4 frozen (crisis pause).
    """
    if regime == SignalColor.GREEN:
        return set()
    return {Tier.T3, Tier.T4}


def _eligible_tiers(regime: SignalColor) -> set[Tier]:
    """Return tiers eligible for new allocation (not frozen).

    GREEN  → all tiers.
    YELLOW → T1/T2 only (T3/T4 frozen at current value).
    ORANGE → T1/T2 only.
    RED    → T1/T2 only.
    """
    if regime == SignalColor.GREEN:
        return {Tier.T1, Tier.T2, Tier.T3, Tier.T4}
    return {Tier.T1, Tier.T2}


# ── Pies Allocation (T212 Interface) ─────────────────────────────────────


def calculate_pies_allocation(
    portfolio: Portfolio,
    universe: Universe,
    signal: CompositeSignal,
) -> list[PieAllocation]:
    """Calculate target Pies allocation for Trading 212."""
    config = _load_portfolio_config()
    regime = signal.overall_color
    total = portfolio.total_value_eur
    constraints = config.get("constraints", {})

    # Tolerance band: 0.5% of total capital for action determination
    tolerance_eur = total * 0.005

    # Build current positions map for T3/T4 freeze logic
    current_positions = {
        t: p.market_value_eur for t, p in portfolio.positions.items()
    }

    # Run the solver
    targets = _solve_lxt(config, universe, regime, total, current_positions)

    allocations: list[PieAllocation] = []
    total_target_eur = 0.0

    for stock in universe.stocks:
        target_eur = targets.get(stock.ticker, 0.0)
        target_pct = round((target_eur / total * 100) if total > 0 else 0.0, 1)
        total_target_eur += target_eur

        pos = portfolio.positions.get(stock.ticker)
        current_eur = round(pos.market_value_eur, 2) if pos else 0.0
        current_pct = round(pos.weight_pct, 1) if pos else 0.0
        delta_eur = round(target_eur - current_eur, 2)

        # Phase 5: Minimum tolerance filter
        if abs(delta_eur) > tolerance_eur:
            action = "BUY" if delta_eur > 0 else "SELL"
        else:
            action = "HOLD"

        allocations.append(PieAllocation(
            ticker=stock.ticker,
            name=stock.name,
            target_pct=target_pct,
            target_eur=round(target_eur, 2),
            current_pct=current_pct,
            current_eur=current_eur,
            delta_eur=delta_eur,
            action=action,
            layer=f"L{stock.layer.value}",
            tier=f"T{stock.tier.value}",
            reasoning=f"L{stock.layer.value}/T{stock.tier.value} @ {regime.value.upper()}",
        ))

    # Hedge row (DXS3.DE)
    hedge_target = targets.get(_HEDGE_TICKER, 0.0)
    hedge_pos = portfolio.positions.get(_HEDGE_TICKER)
    hedge_current = round(hedge_pos.market_value_eur, 2) if hedge_pos else 0.0
    h_pct = round((hedge_target / total * 100) if total > 0 else 0.0, 1)
    hedge_delta = round(hedge_target - hedge_current, 2)
    total_target_eur += hedge_target

    if hedge_target > 0 or hedge_current > 0:
        allocations.append(PieAllocation(
            ticker=_HEDGE_TICKER,
            name="Xtrackers S&P 500 Inverse Daily (Hedge)",
            target_pct=h_pct,
            target_eur=round(hedge_target, 2),
            current_pct=round((hedge_current / total * 100) if total > 0 else 0.0, 1),
            current_eur=hedge_current,
            delta_eur=hedge_delta,
            action="BUY" if hedge_delta > tolerance_eur else ("SELL" if hedge_delta < -tolerance_eur else "HOLD"),
            layer="HEDGE",
            tier="-",
            reasoning=f"Hedge: {regime.value.upper()} regime",
        ))

    # Cash row (XEON.DE)
    xeon_target = targets.get(_CASH_TICKER, 0.0)
    xeon_pos = portfolio.positions.get(_CASH_TICKER)
    xeon_current = round(xeon_pos.market_value_eur, 2) if xeon_pos else 0.0
    x_pct = round((xeon_target / total * 100) if total > 0 else 0.0, 1)
    xeon_delta = round(xeon_target - xeon_current, 2)
    total_target_eur += xeon_target

    allocations.append(PieAllocation(
        ticker=_CASH_TICKER,
        name="Xtrackers EUR Overnight Rate (Cash)",
        target_pct=x_pct,
        target_eur=round(xeon_target, 2),
        current_pct=round((xeon_current / total * 100) if total > 0 else 0.0, 1),
        current_eur=xeon_current,
        delta_eur=xeon_delta,
        action="BUY" if xeon_delta > tolerance_eur else ("SELL" if xeon_delta < -tolerance_eur else "HOLD"),
        layer="CASH",
        tier="-",
        reasoning=f"Cash: {regime.value.upper()} regime",
    ))

    # Residual broker cash row (informational — should converge to 0)
    residual_pct = round(max(0.0, 100.0 - (total_target_eur / total * 100 if total > 0 else 0.0)), 1)
    residual_eur = round(total * residual_pct / 100, 2)
    cash_current = round(portfolio.cash_eur, 2)

    if residual_pct > 0.1 or cash_current > 0:
        allocations.append(PieAllocation(
            ticker="CASH",
            name="Broker Cash (Residual)",
            target_pct=residual_pct,
            target_eur=residual_eur,
            current_pct=round(cash_current / total * 100, 1) if total > 0 else 0.0,
            current_eur=cash_current,
            delta_eur=round(residual_eur - cash_current, 2),
            action="HOLD",
            layer="-",
            tier="-",
            reasoning="Residual broker cash",
        ))

    return allocations
