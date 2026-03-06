"""2D Layer × Tier constraint solver with 5-phase allocation engine + hedge protocols.

Replaces the old 1D tier-based sizing.  The allocation flows through five phases:

  Phase 1 — Cash Floor: regime → minimum cash reserve.
  Phase 2 — Static Layer Budgets: L1/L2/L3/L5 hard allocations.
  Phase 3 — L4 Dynamic Residual: L4 = Total − (Cash + L1 + L2 + L3 + L5).
  Phase 4 — Intra-Layer Distribution: T1/T2/T3/T4 ratios within each layer.
  Phase 5 — Minimum Tolerance: |delta| < 0.5% → HOLD (anti-friction).
"""

from __future__ import annotations

import logging
from typing import Any

import yaml

from rewired import get_config_dir
from rewired.models.portfolio import Portfolio
from rewired.models.signals import CompositeSignal, SignalColor
from rewired.models.universe import Layer, Tier, Universe, Stock

logger = logging.getLogger(__name__)

_HEDGE_TICKER = "QQQS.L"  # Inverse Nasdaq ETF (not in universe)


def _load_portfolio_config() -> dict:
    """Load portfolio configuration."""
    config_path = get_config_dir() / "portfolio.yaml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── 5-Phase L×T Solver ───────────────────────────────────────────────────


def calculate_suggestions(
    portfolio: Portfolio,
    universe: Universe,
    signal: CompositeSignal,
) -> list[dict]:
    """Calculate position sizing suggestions via 2D L×T constraint solver.

    Returns a list of dicts with keys: ticker, action, amount_eur, reason, priority.
    """
    config = _load_portfolio_config()
    regime = signal.overall_color
    total = portfolio.total_value_eur
    constraints = config.get("constraints", {})
    min_pos = constraints.get("min_position_eur", 10)

    # Run the solver
    targets = _solve_lxt(config, universe, regime, total)

    suggestions: list[dict] = []
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
                suggestions.append({
                    "ticker": stock.ticker,
                    "action": "SELL",
                    "amount_eur": round(pos.market_value_eur, 2),
                    "reason": f"L{stock.layer.value}/T{stock.tier.value} target 0 @ {regime.value.upper()}",
                    "priority": 1,
                })
                freed_capital += pos.market_value_eur
            else:
                suggestions.append({
                    "ticker": stock.ticker,
                    "action": "SELL",
                    "amount_eur": round(abs(delta), 2),
                    "reason": f"Trim to L{stock.layer.value}/T{stock.tier.value} target @ {regime.value.upper()}",
                    "priority": 2,
                })
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
                suggestions.append({
                    "ticker": stock.ticker,
                    "action": "BUY",
                    "amount_eur": round(buy_amount, 2),
                    "reason": f"L{stock.layer.value}/T{stock.tier.value} target @ {regime.value.upper()}",
                    "priority": 3,
                })
                available_cash -= buy_amount

    # ── Hedge actions ─────────────────────────────────────────────────
    hedge_target = targets.get(_HEDGE_TICKER, 0.0)
    hedge_pos = portfolio.positions.get(_HEDGE_TICKER)
    hedge_current = hedge_pos.market_value_eur if hedge_pos else 0.0
    hedge_delta = hedge_target - hedge_current

    if hedge_delta > min_pos:
        suggestions.append({
            "ticker": _HEDGE_TICKER,
            "action": "BUY",
            "amount_eur": round(hedge_delta, 2),
            "reason": f"Hedge deployment: {regime.value.upper()} regime",
            "priority": 2,
        })
    elif hedge_delta < -min_pos:
        # Edge case: Hedge Unwind — force QQQS.L to 0 on upgrade
        suggestions.append({
            "ticker": _HEDGE_TICKER,
            "action": "SELL",
            "amount_eur": round(abs(hedge_delta), 2),
            "reason": f"Hedge unwind: regime improved to {regime.value.upper()}",
            "priority": 1,
        })

    suggestions.sort(key=lambda s: s.get("priority", 99))
    return suggestions


def _solve_lxt(
    config: dict,
    universe: Universe,
    regime: SignalColor,
    total: float,
) -> dict[str, float]:
    """Run 5-phase L×T constraint solver. Returns {ticker: target_eur}.

    Also includes _HEDGE_TICKER if hedge is warranted.
    """
    layer_budgets_cfg = config.get("layer_budgets", {})
    cash_floors = config.get("cash_floors", {})
    tier_ratios = config.get("tier_ratios", {})
    constraints = config.get("constraints", {})
    max_single_pct = constraints.get("max_single_position_pct", 15.0)

    # ── Phase 1: Cash Floor ───────────────────────────────────────────
    cash_pct = cash_floors.get(regime.value, 0.05)
    cash_target = total * cash_pct
    investable = total - cash_target

    initiate_hedge = regime in (SignalColor.ORANGE, SignalColor.RED)
    crisis_liquidation = regime == SignalColor.RED

    # ── Phase 2: Static Layer Budgets ─────────────────────────────────
    raw_budgets = {}
    for layer in (Layer.L1, Layer.L2, Layer.L3, Layer.L5):
        key = f"L{layer.value}"
        pct = layer_budgets_cfg.get(key, 0.0)
        # RED veto: L5 → 0
        if crisis_liquidation and layer == Layer.L5:
            pct = 0.0
        raw_budgets[layer] = investable * pct

    static_sum = sum(raw_budgets.values())

    # ── Phase 3: L4 Dynamic Residual ──────────────────────────────────
    l4_budget = investable - static_sum
    if l4_budget < 0:
        # Deficit safeguard: proportionally reduce L1/L2/L3 to cover
        deficit = abs(l4_budget)
        if static_sum > 0:
            for layer in (Layer.L1, Layer.L2, Layer.L3):
                share = raw_budgets[layer] / static_sum
                raw_budgets[layer] = max(0.0, raw_budgets[layer] - deficit * share)
        l4_budget = 0.0

    raw_budgets[Layer.L4] = l4_budget

    # ── Phase 4: Intra-Layer Distribution ─────────────────────────────
    # Eligibility filter by regime
    eligible_tiers = _eligible_tiers(regime)

    targets: dict[str, float] = {}
    layer_surplus = 0.0

    for layer in Layer:
        budget = raw_budgets.get(layer, 0.0)
        layer_stocks = universe.get_by_layer(layer)

        if not layer_stocks or budget <= 0:
            for s in layer_stocks:
                targets[s.ticker] = 0.0
            continue

        # Distribute within layer by tier ratios
        allocated_in_layer = 0.0
        for stock in layer_stocks:
            tier_key = f"T{stock.tier.value}"
            tier_ratio = tier_ratios.get(tier_key, 0.0)

            # Ineligible tier under current regime → target = 0
            if stock.tier not in eligible_tiers:
                targets[stock.ticker] = 0.0
                continue

            # Count eligible stocks in same layer+tier cell
            cell_stocks = [
                s for s in layer_stocks
                if s.tier == stock.tier and s.tier in eligible_tiers
            ]
            n_cell = len(cell_stocks) if cell_stocks else 1

            # Per-stock allocation
            alloc = budget * (tier_ratio / n_cell)

            # Apply max_weight_pct cap
            cap = total * (stock.max_weight_pct / 100)
            if alloc > cap:
                layer_surplus += alloc - cap
                alloc = cap

            targets[stock.ticker] = round(alloc, 2)
            allocated_in_layer += alloc

        # Layer surplus: unallocated budget within layer
        if allocated_in_layer < budget:
            layer_surplus += budget - allocated_in_layer

    # Surplus cascade: layer surplus → L4 stocks, L4 surplus → cash
    if layer_surplus > 0:
        l4_stocks = [
            s for s in universe.stocks
            if s.layer == Layer.L4 and s.tier in eligible_tiers
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
            # Remaining surplus goes to cash (handled implicitly)

    # ── Hedge protocols ───────────────────────────────────────────────
    hedge_target = 0.0
    if initiate_hedge and not crisis_liquidation:
        # ORANGE: deploy 6% of portfolio into QQQS.L
        hedge_target = total * 0.06
    elif crisis_liquidation:
        # RED: no QQQS.L — full liquidation mode
        hedge_target = 0.0
    else:
        # YELLOW/GREEN: unwind hedge entirely (edge case: Hedge Unwind)
        hedge_target = 0.0

    targets[_HEDGE_TICKER] = round(hedge_target, 2)

    return targets


def _eligible_tiers(regime: SignalColor) -> set[Tier]:
    """Return set of tiers eligible for new buys under current regime.

    GREEN  → all tiers.
    YELLOW → T1/T2 (hold T3/T4 but no new buys — handled by existing positions).
    ORANGE → T1/T2 only (T3/T4 forced to 0).
    RED    → T1 only (T2 allowed to hold).
    """
    if regime == SignalColor.GREEN:
        return {Tier.T1, Tier.T2, Tier.T3, Tier.T4}
    if regime == SignalColor.YELLOW:
        return {Tier.T1, Tier.T2, Tier.T3, Tier.T4}
    if regime == SignalColor.ORANGE:
        return {Tier.T1, Tier.T2}
    # RED
    return {Tier.T1, Tier.T2}


# ── Pies Allocation (T212 Interface) ─────────────────────────────────────


def calculate_pies_allocation(
    portfolio: Portfolio,
    universe: Universe,
    signal: CompositeSignal,
) -> list[dict]:
    """Calculate target Pies allocation for Trading 212.

    Returns a list of dicts with: ticker, name, target_pct, target_eur,
    current_pct, current_eur, delta_eur, action, layer, tier, reasoning.
    """
    config = _load_portfolio_config()
    regime = signal.overall_color
    total = portfolio.total_value_eur
    constraints = config.get("constraints", {})

    # Tolerance band: 0.5% of total capital for action determination
    tolerance_eur = total * 0.005

    # Run the solver
    targets = _solve_lxt(config, universe, regime, total)

    allocations = []
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

        allocations.append({
            "ticker": stock.ticker,
            "name": stock.name,
            "target_pct": target_pct,
            "target_eur": round(target_eur, 2),
            "current_pct": current_pct,
            "current_eur": current_eur,
            "delta_eur": delta_eur,
            "action": action,
            "layer": f"L{stock.layer.value}",
            "tier": f"T{stock.tier.value}",
            "reasoning": f"L{stock.layer.value}/T{stock.tier.value} @ {regime.value.upper()}",
        })

    # QQQS.L hedge row
    hedge_target = targets.get(_HEDGE_TICKER, 0.0)
    hedge_pos = portfolio.positions.get(_HEDGE_TICKER)
    hedge_current = round(hedge_pos.market_value_eur, 2) if hedge_pos else 0.0
    hedge_pct = round((hedge_target / total * 100) if total > 0 else 0.0, 1)
    hedge_delta = round(hedge_target - hedge_current, 2)
    total_target_eur += hedge_target

    if hedge_target > 0 or hedge_current > 0:
        allocations.append({
            "ticker": _HEDGE_TICKER,
            "name": "Invesco QQQ Short (Hedge)",
            "target_pct": hedge_pct,
            "target_eur": round(hedge_target, 2),
            "current_pct": round((hedge_current / total * 100) if total > 0 else 0.0, 1),
            "current_eur": hedge_current,
            "delta_eur": hedge_delta,
            "action": "BUY" if hedge_delta > tolerance_eur else ("SELL" if hedge_delta < -tolerance_eur else "HOLD"),
            "layer": "HEDGE",
            "tier": "-",
            "reasoning": f"Hedge: {regime.value.upper()} regime",
        })

    # Cash row
    cash_pct = round(max(0.0, 100.0 - (total_target_eur / total * 100 if total > 0 else 0.0)), 1)
    cash_target_eur = round(total * cash_pct / 100, 2)
    cash_current = round(portfolio.cash_eur, 2)

    allocations.append({
        "ticker": "CASH",
        "name": "Cash Reserve",
        "target_pct": cash_pct,
        "target_eur": cash_target_eur,
        "current_pct": round(cash_current / total * 100, 1) if total > 0 else 0.0,
        "current_eur": cash_current,
        "delta_eur": round(cash_target_eur - cash_current, 2),
        "action": "HOLD",
        "layer": "-",
        "tier": "-",
        "reasoning": "Cash reserve",
    })

    return allocations
