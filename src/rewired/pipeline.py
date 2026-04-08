"""Full DAG pipeline orchestration for the Rewired Index.

Formalises the end-to-end execution flow:

1. **Data fetch** — parallel: FMP + FRED + yfinance + Gemini CAPEX
2. **Signal evaluation** — sequential: rules engine → composite
3. **Company evaluation** — parallel per ticker (optional)
4. **Sizing** — sequential: execution matrix → position targets
5. **Output** — parallel: console + GUI + Telegram + broker

Each stage tracks :class:`DataQuality` status.  Any critical failure
triggers the circuit breaker (defaults to ORANGE).
"""

from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

from rich.console import Console

console = Console(force_terminal=True)
logger = logging.getLogger(__name__)


# ── Stage result ─────────────────────────────────────────────────────────


def _stage(
    name: str,
    fn,
    *args,
    critical: bool = False,
    **kwargs,
) -> dict[str, Any]:
    """Run a single pipeline stage and capture timing + errors.

    Returns a dict with keys: name, status, duration, result, detail.
    """
    t0 = time.time()
    try:
        result = fn(*args, **kwargs)
        return {
            "name": name,
            "status": "ok",
            "duration": time.time() - t0,
            "result": result,
            "detail": "",
        }
    except Exception as e:
        return {
            "name": name,
            "status": "error",
            "duration": time.time() - t0,
            "result": None,
            "detail": str(e),
            "critical": critical,
        }


# ── Parallel helper ──────────────────────────────────────────────────────


def _parallel_stages(
    stages: list[tuple[str, Any, bool]],
    timeout: float = 60.0,
) -> list[dict]:
    """Run stages in parallel threads with per-stage timeout.

    *stages* is a list of ``(name, callable, critical)`` tuples.
    *timeout* is the max seconds each stage may run before being marked as error.
    Returns list of stage result dicts.
    """
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(len(stages), 6)) as pool:
        futures = {}
        for name, fn, critical in stages:
            fut = pool.submit(_stage, name, fn, critical=critical)
            futures[fut] = (name, critical)

        for fut in as_completed(futures, timeout=timeout + 5):
            name, critical = futures[fut]
            try:
                results.append(fut.result(timeout=timeout))
            except TimeoutError:
                results.append({
                    "name": name,
                    "status": "error",
                    "duration": timeout,
                    "result": None,
                    "detail": f"Timed out after {timeout:.0f}s",
                    "critical": critical,
                })
            except Exception as e:
                results.append({
                    "name": name,
                    "status": "error",
                    "duration": 0.0,
                    "result": None,
                    "detail": str(e),
                    "critical": critical,
                })

    return results


# ── Full pipeline ────────────────────────────────────────────────────────


def run_pipeline(
    *,
    dry_run: bool = True,
    send_notifications: bool = True,
) -> list[dict]:
    """Execute the full Rewired Index pipeline DAG.

    Parameters
    ----------
    dry_run : bool
        If True, log proposed trades but do not send to broker.
    send_notifications : bool
        If True, dispatch Telegram notifications on signal change.

    Returns
    -------
    list of stage result dicts for summary display.
    """
    # Generate a unique run ID for log correlation
    run_id = uuid.uuid4().hex[:12]
    from rewired.logging_config import set_run_id

    set_run_id(run_id)
    logger.info("Pipeline started (run_id=%s, dry_run=%s)", run_id, dry_run)

    all_stages: list[dict] = []

    # ── Stage 1: Data Fetch (parallel) ───────────────────────────────
    console.print("[bold]Stage 1:[/bold] Data fetch (parallel)")

    def _fetch_macro():
        from rewired.data.macro import get_macro_readings
        return get_macro_readings()

    def _fetch_sentiment():
        from rewired.data.sentiment import get_sentiment_readings
        return get_sentiment_readings()

    def _fetch_ai_health():
        from rewired.data.ai_health import get_ai_health_readings
        return get_ai_health_readings()

    def _fetch_universe():
        from rewired.models.universe import load_universe
        return load_universe()

    def _fetch_portfolio():
        from rewired.data.broker import get_portfolio
        return get_portfolio()

    fetch_stages = [
        ("Fetch macro (FRED/yfinance)", _fetch_macro, True),
        ("Fetch sentiment (VIX)", _fetch_sentiment, True),
        ("Fetch AI health (Gemini CAPEX)", _fetch_ai_health, True),
        ("Load universe", _fetch_universe, True),
        ("Load portfolio (T212)", _fetch_portfolio, True),
    ]

    fetch_results = _parallel_stages(fetch_stages)
    all_stages.extend(fetch_results)

    # Check for critical failures
    critical_failures = [s for s in fetch_results if s.get("critical") and s["status"] == "error"]
    if critical_failures:
        console.print(f"[red]Circuit breaker: {len(critical_failures)} critical fetch(es) failed[/red]")
        for f in critical_failures:
            console.print(f"  [red]✗[/red] {f['name']}: {f['detail']}")

        # If ALL critical stages failed, abort — pipeline output would be meaningless
        if len(critical_failures) == len(fetch_stages):
            logger.error("All critical fetch stages failed — aborting pipeline")
            console.print("[red bold]All data fetches failed. Pipeline aborted.[/red bold]")
            _write_audit_entry(
                run_id=run_id, signal=None, suggestions_count=0,
                stages=all_stages, total_duration=sum(s["duration"] for s in all_stages),
                dry_run=dry_run,
            )
            return all_stages

    # Extract results by name
    data_map: dict[str, Any] = {}
    for r in fetch_results:
        data_map[r["name"]] = r.get("result")

    universe = data_map.get("Load universe")
    portfolio = data_map.get("Load portfolio (T212)")

    # ── Stage 2: Signal Evaluation (sequential) ──────────────────────
    console.print("[bold]Stage 2:[/bold] Signal evaluation")

    def _compute_signals():
        from rewired.signals.engine import compute_signals
        return compute_signals()

    sig_stage = _stage("Compute signals", _compute_signals, critical=True)
    all_stages.append(sig_stage)

    signal = sig_stage.get("result")
    if signal:
        color = signal.overall_color.value
        console.print(f"  Composite signal: [bold]{color.upper()}[/bold]")
        if signal.veto_active:
            console.print("  [red bold]AI HEALTH VETO ACTIVE[/red bold]")
    else:
        console.print("  [red]Signal computation failed[/red]")

    # ── Stage 3: Company evaluation (removed — decoupled to Oracle Gateway) ─
    all_stages.append({
        "name": "Company evaluation",
        "status": "skipped",
        "duration": 0,
        "detail": "Decoupled to Oracle JSON Gateway",
    })

    # ── Stage 4: Sizing (sequential) ─────────────────────────────────
    suggestions = []
    if signal and portfolio and universe:
        console.print("[bold]Stage 4:[/bold] Position sizing")

        def _compute_sizing():
            from rewired.portfolio.sizing import calculate_suggestions
            return calculate_suggestions(portfolio, universe, signal)

        sizing_stage = _stage("Compute sizing", _compute_sizing)
        all_stages.append(sizing_stage)
        suggestions = sizing_stage.get("result") or []

        sells = [s for s in suggestions if s.action == "SELL"]
        buys = [s for s in suggestions if s.action == "BUY"]
        console.print(f"  Generated {len(suggestions)} actions ({len(sells)} sells, {len(buys)} buys)")
    else:
        all_stages.append({
            "name": "Position sizing",
            "status": "skipped" if not signal else "error",
            "duration": 0,
            "detail": "Missing signal, portfolio, or universe",
        })

    # ── Stage 5: Output (parallel) ───────────────────────────────────
    console.print("[bold]Stage 5:[/bold] Output")

    def _output_console():
        from rewired.notifications.console import print_signals, print_pipeline_summary
        if signal:
            print_signals(signal)
        print_pipeline_summary(all_stages)

    def _output_telegram():
        if not send_notifications or not signal:
            return
        from rewired.notifications.dispatcher import dispatch_signal_change
        # Only dispatch if there was a color change (handled inside dispatcher)
        dispatch_signal_change("", signal.overall_color.value, signal.summary)

    def _output_broker():
        if not suggestions:
            return "No trades to execute"

        from rewired.broker.interface import OrderRequest, OrderSide

        orders = []
        for s in suggestions:
            orders.append(OrderRequest(
                ticker=s.ticker,
                side=OrderSide.BUY if s.action == "BUY" else OrderSide.SELL,
                amount_eur=s.amount_eur,
                reason=s.reason,
                priority=s.priority,
            ))

        if dry_run:
            from rewired.notifications.console import print_execution_plan
            print_execution_plan(orders, signal, dry_run=True)
            return f"Dry run: {len(orders)} trades logged"

        # Live execution
        try:
            from rewired.broker.ibkr import IBKRBroker
            brk = IBKRBroker()
            brk.connect()
            results = brk.execute_batch(orders)
            brk.disconnect()

            from rewired.notifications.console import print_execution_results
            print_execution_results(results)

            filled = sum(1 for r in results if r.status.value == "filled")
            return f"{filled}/{len(results)} orders filled"
        except ImportError:
            from rewired.notifications.console import print_execution_plan
            print_execution_plan(orders, signal, dry_run=True)
            return "ib_insync not installed, showed dry-run plan"

    output_stages = [
        ("Console output", _output_console, False),
        ("Telegram notification", _output_telegram, False),
        ("Broker execution", _output_broker, False),
    ]

    output_results = _parallel_stages(output_stages)
    all_stages.extend(output_results)

    # ── Summary ──────────────────────────────────────────────────────
    total_time = sum(s["duration"] for s in all_stages)
    ok_count = sum(1 for s in all_stages if s["status"] == "ok")
    err_count = sum(1 for s in all_stages if s["status"] == "error")
    skip_count = sum(1 for s in all_stages if s["status"] == "skipped")

    console.print(
        f"\n[bold]Pipeline complete:[/bold] {ok_count} ok, {err_count} errors, "
        f"{skip_count} skipped in {total_time:.1f}s"
    )

    # ── Audit log (append JSON-line) ─────────────────────────────────
    _write_audit_entry(
        run_id=run_id,
        signal=signal,
        suggestions_count=len(suggestions),
        stages=all_stages,
        total_duration=total_time,
        dry_run=dry_run,
    )

    return all_stages


def _write_audit_entry(
    *,
    run_id: str,
    signal: Any,
    suggestions_count: int,
    stages: list[dict],
    total_duration: float,
    dry_run: bool,
) -> None:
    """Append a single JSON-line to data/audit_log.jsonl."""
    import json

    from rewired import get_data_dir

    entry = {
        "run_id": run_id,
        "ts": datetime.now().isoformat(),
        "signal_color": signal.overall_color.value if signal else None,
        "veto_active": signal.veto_active if signal else False,
        "stages": [
            {
                "name": s.get("name", ""),
                "status": s.get("status", ""),
                "duration": round(s.get("duration", 0.0), 3),
                "detail": s.get("detail", ""),
            }
            for s in stages
        ],
        "suggestions_count": suggestions_count,
        "dry_run": dry_run,
        "total_duration_s": round(total_duration, 2),
    }

    audit_path = get_data_dir() / "audit_log.jsonl"
    try:
        with open(audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.error("Failed to write audit log: %s", exc)
