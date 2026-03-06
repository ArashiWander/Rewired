"""Autonomous universe rebalancer — Directive 1.

Runs a full evaluation scan, identifies tier mismatches, verifies each
proposed change via a secondary Gemini check, and applies confirmed
reclassifications to ``universe.yaml``.

**Cold Determinism guardrails**:
- Never auto-promote to T1 (logged as needs_human_approval).
- Only one tier step per cycle (T2→T3, not T2→T4).
- 30-day cooldown per stock after a tier change.
- Maximum 2 applied changes per cycle.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from rewired.agent.gemini import generate, is_configured
from rewired.agent.prompts import (
    SYSTEM_REBALANCER,
    TIER_DOWNGRADE_CHECK,
    UNIVERSE_REBALANCE,
)
from rewired.models.evaluation import CompanyEvaluation, EvaluationBatch
from rewired.models.universe import (
    Layer,
    Tier,
    Stock,
    Universe,
    load_universe,
    save_universe,
    LAYER_NAMES,
    TIER_NAMES,
)

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────

_COOLDOWN_DAYS = 30
_MAX_CHANGES_PER_CYCLE = 2


# ── Public API ───────────────────────────────────────────────────────────


def rebalance_universe(
    batch: EvaluationBatch | None = None,
    *,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Run the full rebalance cycle.

    1. Evaluate the universe (or accept a pre-existing batch).
    2. Extract tier mismatches.
    3. Ask Gemini for a rebalance plan via UNIVERSE_REBALANCE prompt.
    4. Verify each proposed downgrade via TIER_DOWNGRADE_CHECK.
    5. Apply confirmed changes to universe.yaml (respecting guardrails).

    Returns a list of change dicts for logging / notification.
    """
    if not is_configured():
        logger.warning("Gemini not configured — skipping rebalance.")
        return []

    # Step 1: get evaluation batch
    if batch is None:
        from rewired.agent.evaluator import evaluate_universe
        batch = evaluate_universe()

    mismatches = batch.tier_mismatches()
    if not mismatches:
        logger.info("No tier mismatches found — universe is aligned.")
        return []

    logger.info("Found %d tier mismatch(es), requesting rebalance plan.", len(mismatches))

    # Step 2: build context for the rebalance prompt
    universe = load_universe()
    mismatches_text = _format_mismatches(mismatches, universe)
    universe_text = _format_universe(universe)

    # Step 3: ask Gemini for plan
    plan = _get_rebalance_plan(mismatches_text, universe_text)
    if not plan:
        logger.warning("Rebalance plan was empty or unparseable.")
        return []

    # Step 4: verify each proposed change + apply guardrails
    applied: list[dict[str, Any]] = []
    now = datetime.now()

    for change in plan:
        ticker = change.get("ticker", "")
        action = change.get("action", "monitor_only")
        proposed_tier_str = change.get("proposed_tier", "")
        confidence = float(change.get("confidence", 0))

        stock = universe.get_stock(ticker)
        if stock is None:
            logger.warning("Rebalance plan references unknown ticker: %s", ticker)
            continue

        # Guardrail: cooldown check
        if stock.last_tier_change:
            days_since = (now - stock.last_tier_change).days
            if days_since < _COOLDOWN_DAYS:
                logger.info(
                    "Skipping %s — last tier change %d days ago (cooldown: %d).",
                    ticker, days_since, _COOLDOWN_DAYS,
                )
                change["action"] = "cooldown_blocked"
                applied.append(change)
                continue

        # Guardrail: never auto-promote to T1
        if proposed_tier_str == "T1" and stock.tier != Tier.T1:
            logger.info("%s: T1 promotion requires human approval.", ticker)
            change["action"] = "needs_human_approval"
            applied.append(change)
            continue

        # Guardrail: only one tier step
        if proposed_tier_str in Tier.__members__:
            proposed_tier = Tier[proposed_tier_str]
            step = abs(proposed_tier.value - stock.tier.value)
            if step > 1:
                logger.info(
                    "%s: Proposed change T%d→T%d exceeds 1-step limit, clamping.",
                    ticker, stock.tier.value, proposed_tier.value,
                )
                direction = 1 if proposed_tier.value > stock.tier.value else -1
                proposed_tier = Tier(stock.tier.value + direction)
                change["proposed_tier"] = f"T{proposed_tier.value}"

        # Guardrail: max changes per cycle
        applied_count = sum(1 for c in applied if c.get("action") == "applied")
        if applied_count >= _MAX_CHANGES_PER_CYCLE:
            logger.info("Max changes reached (%d). Deferring %s.", _MAX_CHANGES_PER_CYCLE, ticker)
            change["action"] = "deferred_max_changes"
            applied.append(change)
            continue

        # Only proceed if action is "apply" and confidence is sufficient
        if action not in ("apply",):
            applied.append(change)
            continue

        # Step 4b: secondary verification for downgrades
        ev = batch.get(ticker)
        if ev and proposed_tier_str in Tier.__members__:
            proposed_tier = Tier[proposed_tier_str]
            if proposed_tier.value > stock.tier.value:  # downgrade = higher tier number
                verified = _verify_downgrade(stock, proposed_tier, ev)
                if not verified:
                    change["action"] = "verification_rejected"
                    applied.append(change)
                    continue

        # Apply the change
        if proposed_tier_str in Tier.__members__ and not dry_run:
            proposed_tier = Tier[proposed_tier_str]
            old_tier = stock.tier
            stock.tier = proposed_tier
            stock.last_tier_change = now
            note_prefix = f"Auto-rebalanced T{old_tier.value}->T{proposed_tier.value} on {now.strftime('%Y-%m-%d')}"
            if stock.notes:
                stock.notes = f"{note_prefix}. {stock.notes}"
            else:
                stock.notes = note_prefix
            change["action"] = "applied"
            logger.info("Applied: %s T%d → T%d", ticker, old_tier.value, proposed_tier.value)

        applied.append(change)

    # Step 5: persist
    if not dry_run and any(c.get("action") == "applied" for c in applied):
        save_universe(universe)
        _try_invalidate_gui_cache()
        logger.info("Universe saved with %d change(s).", sum(1 for c in applied if c["action"] == "applied"))

    return applied


# ── Internal helpers ─────────────────────────────────────────────────────


def _format_mismatches(mismatches: list[CompanyEvaluation], universe: Universe) -> str:
    """Format mismatches for the prompt."""
    lines = []
    for ev in mismatches:
        stock = universe.get_stock(ev.ticker)
        current_tier = f"T{stock.tier.value}" if stock else "?"
        lines.append(
            f"- {ev.ticker}: Current={current_tier}, Suggested={ev.suggested_tier_change}, "
            f"Composite={ev.composite_score:.1f}/10, Conviction={ev.conviction_level}, "
            f"Trend={ev.earnings_trend}, Risk={ev.biggest_risk[:60]}"
        )
    return "\n".join(lines)


def _format_universe(universe: Universe) -> str:
    """Format the universe for context."""
    lines = []
    for s in universe.stocks:
        lines.append(
            f"- {s.ticker} ({s.name}): L{s.layer.value}/T{s.tier.value}, "
            f"max_weight={s.max_weight_pct}%"
        )
    return "\n".join(lines)


def _get_rebalance_plan(mismatches_text: str, universe_text: str) -> list[dict]:
    """Ask Gemini for a rebalance plan and parse the JSON response."""
    prompt = UNIVERSE_REBALANCE.format(
        mismatches=mismatches_text,
        universe_state=universe_text,
    )

    raw = generate(
        prompt,
        system_instruction=SYSTEM_REBALANCER,
        json_output=True,
        max_retries=2,
    )

    try:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        if text.startswith("json"):
            text = text[4:].strip()

        data = json.loads(text)
        changes = data.get("changes", [])
        summary = data.get("summary", "")
        if summary:
            logger.info("Rebalance plan summary: %s", summary)
        return changes
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("Failed to parse rebalance plan: %s", exc)
        return []


def _verify_downgrade(
    stock: Stock,
    proposed_tier: Tier,
    ev: CompanyEvaluation,
) -> bool:
    """Run the secondary TIER_DOWNGRADE_CHECK prompt."""
    prompt = TIER_DOWNGRADE_CHECK.format(
        ticker=stock.ticker,
        name=stock.name,
        current_tier=stock.tier.value,
        proposed_tier=proposed_tier.value,
        composite_score=f"{ev.composite_score:.1f}",
        fundamental_score=f"{ev.fundamental_score:.1f}",
        ai_relevance_score=f"{ev.ai_relevance_score:.1f}",
        moat_score=f"{ev.moat_score:.1f}",
        conviction_level=ev.conviction_level,
        earnings_trend=ev.earnings_trend,
        reasoning=ev.reasoning[:300],
    )

    raw = generate(
        prompt,
        system_instruction=SYSTEM_REBALANCER,
        json_output=True,
    )

    try:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        if text.startswith("json"):
            text = text[4:].strip()

        data = json.loads(text)
        proceed = bool(data.get("proceed", False))
        reason = data.get("reason", "")
        logger.info(
            "Downgrade check for %s T%d→T%d: %s — %s",
            stock.ticker, stock.tier.value, proposed_tier.value,
            "PROCEED" if proceed else "REJECTED", reason[:120],
        )
        return proceed
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("Failed to parse downgrade check for %s: %s", stock.ticker, exc)
        return False  # Conservative: don't downgrade if we can't verify


def _try_invalidate_gui_cache() -> None:
    """Attempt to invalidate the GUI state cache after universe mutation."""
    try:
        from rewired.gui.state import invalidate_universe
        invalidate_universe()
    except ImportError:
        pass  # GUI not installed or not running
    except Exception as exc:
        logger.debug("Could not invalidate GUI cache: %s", exc)
