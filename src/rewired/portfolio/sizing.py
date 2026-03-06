"""Position sizing logic with take-profit rebalancing and Pies allocation output.

Generates a complete daily trading instruction table (precise to the euro) that maps
directly to Trading 212's "Pies" feature for one-click rebalancing.
"""

from __future__ import annotations

import yaml

from rewired import get_config_dir
from rewired.models.portfolio import Portfolio
from rewired.models.signals import CompositeSignal, SignalColor
from rewired.models.universe import Universe, Stock, Tier


def _load_portfolio_config() -> dict:
    """Load portfolio configuration."""
    config_path = get_config_dir() / "portfolio.yaml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def calculate_suggestions(
    portfolio: Portfolio,
    universe: Universe,
    signal: CompositeSignal,
) -> list[dict]:
    """Calculate position sizing suggestions including take-profit rebalancing.

    Returns a list of dicts with keys: ticker, action, amount_eur, reason, priority.
    """
    config = _load_portfolio_config()
    overall_color = signal.overall_color

    tier_alloc = config["allocation_by_tier"]
    multipliers = config["signal_multipliers"]
    constraints = config["constraints"]
    tier_rules = config.get("tier_rules_by_signal", {})

    multiplier = multipliers.get(overall_color.value, 1.0)
    total_capital = portfolio.total_value_eur
    max_single_pct = constraints.get("max_single_position_pct", 15.0)
    min_pos = constraints.get("min_position_eur", 10)

    suggestions = []
    freed_capital = 0.0  # Capital freed by take-profit sells

    # ── Phase 1: Take-profit rebalancing (works in ALL signal colors) ─────
    for stock in universe.stocks:
        if stock.ticker not in portfolio.positions:
            continue
        pos = portfolio.positions[stock.ticker]
        if pos.weight_pct > stock.max_weight_pct and pos.market_value_eur > 0:
            # Position breached its cap - harvest the excess
            target_value = total_capital * (stock.max_weight_pct / 100)
            excess = pos.market_value_eur - target_value
            if excess >= min_pos:
                suggestions.append({
                    "ticker": stock.ticker,
                    "action": "SELL",
                    "amount_eur": round(excess, 2),
                    "reason": f"Take profit: {pos.weight_pct:.1f}% > {stock.max_weight_pct:.0f}% cap",
                    "priority": 1,
                })
                freed_capital += excess

    # ── Phase 2: Signal-driven exits/trims ────────────────────────────────
    color_rules = tier_rules.get(overall_color.value, {})
    for tier_key, rule in color_rules.items():
        if rule not in ("exit", "trim_50"):
            continue
        tier_enum = Tier[tier_key]
        tier_stocks = universe.get_by_tier(tier_enum)
        for stock in tier_stocks:
            if stock.ticker not in portfolio.positions:
                continue
            # Skip if already captured by take-profit
            already_suggested = any(s["ticker"] == stock.ticker for s in suggestions)
            if already_suggested:
                continue

            pos = portfolio.positions[stock.ticker]
            if rule == "exit":
                suggestions.append({
                    "ticker": stock.ticker,
                    "action": "SELL",
                    "amount_eur": round(pos.market_value_eur, 2),
                    "reason": f"Signal {overall_color.value.upper()}: exit {tier_key}",
                    "priority": 2,
                })
                freed_capital += pos.market_value_eur
            elif rule == "trim_50":
                trim_amount = pos.market_value_eur * 0.5
                suggestions.append({
                    "ticker": stock.ticker,
                    "action": "SELL",
                    "amount_eur": round(trim_amount, 2),
                    "reason": f"Signal {overall_color.value.upper()}: trim {tier_key} 50%",
                    "priority": 2,
                })
                freed_capital += trim_amount

    # ── Phase 3: Buy targets for unheld positions ─────────────────────────
    available_cash = portfolio.cash_eur + freed_capital

    for stock in universe.stocks:
        # Skip if already holding (unless we need to top up - future enhancement)
        if stock.ticker in portfolio.positions:
            continue

        tier_key = f"T{stock.tier.value}"

        # Skip if tier should exit under current signal
        rule = color_rules.get(tier_key, "hold")
        if rule == "exit":
            continue
        # Don't open NEW positions in tiers marked for trim
        if rule == "trim_50":
            continue

        tier_base = tier_alloc.get(tier_key, 0)
        tier_budget = total_capital * tier_base * multiplier

        # Equal weight within tier, capped by max_weight
        tier_stocks = universe.get_by_tier(stock.tier)
        if not tier_stocks:
            continue

        per_stock = tier_budget / len(tier_stocks)
        max_amount = total_capital * (stock.max_weight_pct / 100)
        target = min(per_stock, max_amount)

        if target < min_pos:
            continue

        if target > available_cash:
            target = available_cash
            if target < min_pos:
                continue

        suggestions.append({
            "ticker": stock.ticker,
            "action": "BUY",
            "amount_eur": round(target, 2),
            "reason": f"L{stock.layer.value}/{tier_key} target @ {overall_color.value.upper()} signal",
            "priority": 3,
        })
        available_cash -= target

    # ── Phase 4: Redistribute freed capital to underweight layers ─────────
    if freed_capital > min_pos and overall_color in (SignalColor.GREEN, SignalColor.YELLOW):
        # Prioritize L4/L5 exploration layers if they're underweight
        exploration_stocks = [s for s in universe.stocks
                             if s.layer.value >= 4 and s.ticker in portfolio.positions]
        underweight = []
        for stock in universe.stocks:
            if stock.layer.value < 4:
                continue
            if stock.ticker not in portfolio.positions:
                underweight.append(stock)
                continue
            pos = portfolio.positions[stock.ticker]
            target_pct = stock.max_weight_pct
            if pos.weight_pct < target_pct * 0.5:
                underweight.append(stock)

        for stock in underweight:
            if freed_capital < min_pos:
                break
            # Check if already has a buy suggestion
            existing = [s for s in suggestions if s["ticker"] == stock.ticker and s["action"] == "BUY"]
            if existing:
                continue

            alloc = min(freed_capital * 0.3, total_capital * (stock.max_weight_pct / 100))
            if alloc >= min_pos:
                suggestions.append({
                    "ticker": stock.ticker,
                    "action": "BUY",
                    "amount_eur": round(alloc, 2),
                    "reason": f"Redistribute profit -> L{stock.layer.value} exploration",
                    "priority": 4,
                })
                freed_capital -= alloc

    # Sort by priority
    suggestions.sort(key=lambda s: s.get("priority", 99))

    return suggestions


def calculate_pies_allocation(
    portfolio: Portfolio,
    universe: Universe,
    signal: CompositeSignal,
) -> list[dict]:
    """Calculate target Pies allocation for Trading 212.

    Returns a list of dicts with: ticker, name, target_pct, target_eur,
    current_pct, current_eur, delta_eur, action, layer, tier, reasoning.
    This maps directly to T212 Pies — set each stock to the target percentage.
    """
    config = _load_portfolio_config()
    overall_color = signal.overall_color

    tier_alloc = config["allocation_by_tier"]
    multipliers = config["signal_multipliers"]
    tier_rules = config.get("tier_rules_by_signal", {})

    multiplier = multipliers.get(overall_color.value, 1.0)
    color_rules = tier_rules.get(overall_color.value, {})
    total_capital = portfolio.total_value_eur
    # Tolerance band: 0.5% of total capital for action determination
    tolerance_eur = total_capital * 0.005

    allocations = []
    total_pct = 0.0

    for stock in universe.stocks:
        tier_key = f"T{stock.tier.value}"
        rule = color_rules.get(tier_key, "hold")

        tier_base = tier_alloc.get(tier_key, 0)
        tier_stocks = universe.get_by_tier(stock.tier)
        n_in_tier = len(tier_stocks) if tier_stocks else 1

        # Determine target allocation
        if rule == "exit":
            target_pct = 0.0
            reasoning = f"Signal rule: EXIT all {tier_key} @ {overall_color.value.upper()}"
        elif rule == "trim_50":
            if stock.ticker in portfolio.positions:
                normal_pct = (tier_base * multiplier / n_in_tier) * 100 if tier_stocks else 0
                target_pct = min(normal_pct * 0.5, stock.max_weight_pct)
                reasoning = (
                    f"TRIM_50: ({tier_base}×{multiplier}/{n_in_tier})×100×0.5 "
                    f"= {target_pct:.1f}%, cap {stock.max_weight_pct}%"
                )
            else:
                target_pct = 0.0
                reasoning = f"TRIM_50: not held → 0%"
        else:
            if tier_stocks:
                target_pct = min(
                    (tier_base * multiplier / n_in_tier) * 100,
                    stock.max_weight_pct,
                )
                reasoning = (
                    f"HOLD: ({tier_base}×{multiplier}/{n_in_tier})×100 "
                    f"= {target_pct:.1f}%, cap {stock.max_weight_pct}%"
                )
            else:
                target_pct = 0.0
                reasoning = "No stocks in tier"

        target_pct = round(target_pct, 1)
        target_eur = round(total_capital * target_pct / 100, 2)
        total_pct += target_pct

        # Current position metrics
        pos = portfolio.positions.get(stock.ticker)
        current_eur = round(pos.market_value_eur, 2) if pos else 0.0
        current_pct = round(pos.weight_pct, 1) if pos else 0.0
        delta_eur = round(target_eur - current_eur, 2)

        # Action determination
        if delta_eur > tolerance_eur:
            action = "BUY"
        elif delta_eur < -tolerance_eur:
            action = "SELL"
        else:
            action = "HOLD"

        allocations.append({
            "ticker": stock.ticker,
            "name": stock.name,
            "target_pct": target_pct,
            "target_eur": target_eur,
            "current_pct": current_pct,
            "current_eur": current_eur,
            "delta_eur": delta_eur,
            "action": action,
            "layer": f"L{stock.layer.value}",
            "tier": f"T{stock.tier.value}",
            "reasoning": reasoning,
        })

    # Remaining goes to cash
    cash_pct = round(max(0, 100 - total_pct), 1)
    cash_current = round(portfolio.cash_eur, 2) if portfolio else 0.0
    cash_target_eur = round(total_capital * cash_pct / 100, 2)
    allocations.append({
        "ticker": "CASH",
        "name": "Cash Reserve",
        "target_pct": cash_pct,
        "target_eur": cash_target_eur,
        "current_pct": round(cash_current / total_capital * 100, 1) if total_capital > 0 else 0.0,
        "current_eur": cash_current,
        "delta_eur": round(cash_target_eur - cash_current, 2),
        "action": "HOLD",
        "layer": "-",
        "tier": "-",
        "reasoning": "Cash reserve",
    })

    return allocations
