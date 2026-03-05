"""ECharts-based visualisations for the Rewired Index dashboard.

All chart helpers return ``ui.echart`` elements so they can be placed
inside any NiceGUI layout container.  The helpers accept plain Python
data structures (dicts, lists) and build the ECharts option JSON.

NiceGUI bundles Apache ECharts — no extra dependency is needed.
"""

from __future__ import annotations

from typing import Any

from nicegui import ui

from rewired.gui.i18n import t, layer_name, tier_name

# ── colour palette (consistent with the rest of the GUI) ─────────────────

SIGNAL_HEX = {
    "green": "#22c55e",
    "yellow": "#eab308",
    "orange": "#f97316",
    "red": "#ef4444",
}

_TIER_COLORS = ["#6366f1", "#8b5cf6", "#a78bfa", "#c4b5fd"]  # indigo → violet
_LAYER_COLORS = ["#06b6d4", "#0ea5e9", "#3b82f6", "#6366f1", "#8b5cf6"]


# ── 1. Pies allocation donut ─────────────────────────────────────────────


def pies_donut_chart(allocations: list[dict], height: str = "360px") -> ui.echart:
    """Donut chart showing target allocation percentages by stock.

    Cash is shown as a greyed-out slice.
    """
    data: list[dict[str, Any]] = []
    for a in allocations:
        is_cash = a["ticker"] == "CASH"
        data.append({
            "name": a["ticker"],
            "value": round(a["target_pct"], 1),
            "itemStyle": {"color": "#555"} if is_cash else {},
        })

    option = {
        "tooltip": {"trigger": "item", "formatter": "{b}: {c}%"},
        "legend": {
            "orient": "vertical",
            "right": 10,
            "top": "center",
            "textStyle": {"color": "#ccc"},
        },
        "series": [
            {
                "type": "pie",
                "radius": ["42%", "70%"],
                "center": ["40%", "50%"],
                "avoidLabelOverlap": True,
                "itemStyle": {"borderRadius": 6, "borderColor": "#1e1e1e", "borderWidth": 2},
                "label": {"show": True, "formatter": "{b}\n{c}%", "color": "#ccc"},
                "emphasis": {
                    "label": {"show": True, "fontSize": 14, "fontWeight": "bold"},
                },
                "data": data,
            }
        ],
    }
    return ui.echart(option).classes("w-full").style(f"height:{height}")


# ── 2. LxT heatmap ──────────────────────────────────────────────────────


def lxt_heatmap(
    universe,
    portfolio=None,
    evaluations=None,
    height: str = "320px",
) -> ui.echart:
    """Layer × Tier heatmap.

    Cell colour = number of stocks in that coordinate (or composite eval score
    when *evaluations* is provided).  Tooltip shows stock tickers.
    """
    from rewired.models.universe import Layer, Tier

    layers = [f"L{l.value}" for l in Layer]
    tiers = [f"T{t.value}" for t in Tier]

    data: list[list] = []  # [tier_idx, layer_idx, value]
    tooltip_map: dict[str, str] = {}  # "tier_idx-layer_idx" -> label

    for li, lyr in enumerate(Layer):
        for ti, tier in enumerate(Tier):
            stocks = universe.get_by_coordinate(lyr, tier)
            tickers = [s.ticker for s in stocks]
            count = len(tickers)

            # If evaluation data given, use avg composite score
            value = count
            if evaluations and tickers:
                scores = []
                for tk in tickers:
                    ev = evaluations.get(tk) if evaluations else None
                    if ev:
                        scores.append(getattr(ev, "composite_score", 0))
                if scores:
                    value = round(sum(scores) / len(scores), 1)

            data.append([ti, li, value])
            label = ", ".join(tickers) if tickers else "-"
            tooltip_map[f"{ti}-{li}"] = label

    option = {
        "tooltip": {
            "position": "top",
        },
        "grid": {"top": 30, "bottom": 40, "left": 100, "right": 30},
        "xAxis": {
            "type": "category",
            "data": tiers,
            "splitArea": {"show": True},
            "axisLabel": {"color": "#ccc"},
        },
        "yAxis": {
            "type": "category",
            "data": layers,
            "splitArea": {"show": True},
            "axisLabel": {"color": "#ccc"},
        },
        "visualMap": {
            "min": 0,
            "max": max((d[2] for d in data), default=5),
            "calculable": True,
            "orient": "horizontal",
            "left": "center",
            "bottom": 0,
            "inRange": {"color": ["#1a1a2e", "#16213e", "#0f3460", "#533483", "#e94560"]},
            "textStyle": {"color": "#ccc"},
        },
        "series": [
            {
                "type": "heatmap",
                "data": data,
                "label": {"show": True, "color": "#fff"},
                "emphasis": {
                    "itemStyle": {"shadowBlur": 10, "shadowColor": "rgba(0,0,0,0.5)"},
                },
            }
        ],
    }
    return ui.echart(option).classes("w-full").style(f"height:{height}")


# ── 3. Signal history timeline ───────────────────────────────────────────


def signal_history_chart(history: list[dict], height: str = "280px") -> ui.echart:
    """Line chart tracking composite signal colour changes over time.

    X-axis = timestamps, Y-axis = signal colour mapped to numeric (4/3/2/1).
    """
    color_to_num = {"green": 4, "yellow": 3, "orange": 2, "red": 1}

    x_data: list[str] = []
    y_data: list[int] = []

    for entry in history:
        ts = entry.get("timestamp", "")
        to_color = entry.get("to_color", "yellow")
        x_data.append(ts)
        y_data.append(color_to_num.get(to_color, 2))

    if not x_data:
        x_data = ["(no data)"]
        y_data = [2]

    option = {
        "tooltip": {
            "trigger": "axis",
        },
        "grid": {"top": 20, "bottom": 40, "left": 60, "right": 20},
        "xAxis": {
            "type": "category",
            "data": x_data,
            "axisLabel": {"color": "#999", "rotate": 30},
        },
        "yAxis": {
            "type": "value",
            "min": 0.5,
            "max": 4.5,
            "interval": 1,
            "axisLabel": {
                "color": "#999",
                "formatter": "{value}",
            },
            "splitLine": {"lineStyle": {"color": "#333"}},
        },
        "series": [
            {
                "type": "line",
                "data": y_data,
                "smooth": True,
                "lineStyle": {"width": 3},
                "areaStyle": {"opacity": 0.15},
                "itemStyle": {"color": "#6366f1"},
                "markLine": {
                    "silent": True,
                    "lineStyle": {"type": "dashed"},
                    "data": [
                        {"yAxis": 3.5, "lineStyle": {"color": "#22c55e"}, "label": {"formatter": "GREEN", "color": "#22c55e"}},
                        {"yAxis": 2.5, "lineStyle": {"color": "#eab308"}, "label": {"formatter": "YELLOW", "color": "#eab308"}},
                        {"yAxis": 1.5, "lineStyle": {"color": "#f97316"}, "label": {"formatter": "ORANGE", "color": "#f97316"}},
                    ],
                },
            }
        ],
    }
    return ui.echart(option).classes("w-full").style(f"height:{height}")


# ── 4. Company evaluation radar ──────────────────────────────────────────


def evaluation_radar_chart(
    evaluation,
    height: str = "320px",
) -> ui.echart:
    """Radar chart showing a single ``CompanyEvaluation``'s sub-scores.

    Five axes: Fundamental, AI-Relevance, Moat, Management, (Composite).
    """
    indicators = [
        {"name": "Fundamental", "max": 10},
        {"name": "AI-Relevance", "max": 10},
        {"name": "Moat", "max": 10},
        {"name": "Management", "max": 10},
        {"name": "Composite", "max": 10},
    ]
    values = [
        evaluation.fundamental_score,
        evaluation.ai_relevance_score,
        evaluation.moat_score,
        evaluation.management_score,
        evaluation.composite_score,
    ]

    option = {
        "tooltip": {},
        "radar": {
            "indicator": indicators,
            "shape": "polygon",
            "axisName": {"color": "#ccc"},
            "splitArea": {"areaStyle": {"color": ["rgba(99,102,241,0.05)", "rgba(99,102,241,0.1)"]}},
            "splitLine": {"lineStyle": {"color": "#444"}},
        },
        "series": [
            {
                "type": "radar",
                "data": [
                    {
                        "value": values,
                        "name": evaluation.ticker,
                        "areaStyle": {"opacity": 0.25},
                        "lineStyle": {"width": 2},
                        "itemStyle": {"color": "#6366f1"},
                    }
                ],
            }
        ],
    }
    return ui.echart(option).classes("w-full").style(f"height:{height}")


# ── 5. Batch evaluation bar chart ────────────────────────────────────────


def evaluation_bar_chart(
    evaluations: list,
    height: str = "320px",
) -> ui.echart:
    """Horizontal bar chart ranking stocks by composite evaluation score."""
    # Sort ascending (bottom-to-top in horizontal bar)
    sorted_evals = sorted(evaluations, key=lambda e: e.composite_score)

    tickers = [e.ticker for e in sorted_evals]
    scores = [round(e.composite_score, 1) for e in sorted_evals]

    # Colour bars by score
    colors: list[str] = []
    for s in scores:
        if s >= 7.5:
            colors.append("#22c55e")
        elif s >= 5.0:
            colors.append("#eab308")
        elif s >= 3.0:
            colors.append("#f97316")
        else:
            colors.append("#ef4444")

    option = {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "grid": {"top": 10, "bottom": 30, "left": 70, "right": 30},
        "xAxis": {
            "type": "value",
            "min": 0,
            "max": 10,
            "axisLabel": {"color": "#999"},
            "splitLine": {"lineStyle": {"color": "#333"}},
        },
        "yAxis": {
            "type": "category",
            "data": tickers,
            "axisLabel": {"color": "#ccc"},
        },
        "series": [
            {
                "type": "bar",
                "data": [
                    {"value": s, "itemStyle": {"color": c}}
                    for s, c in zip(scores, colors)
                ],
                "barWidth": "60%",
                "label": {"show": True, "position": "right", "color": "#ccc", "formatter": "{c}"},
            }
        ],
    }
    return ui.echart(option).classes("w-full").style(f"height:{height}")


# ── 6. Portfolio weight treemap ──────────────────────────────────────────


def portfolio_weight_treemap(portfolio, height: str = "300px") -> ui.echart:
    """Treemap showing portfolio positions by weight.

    Colour indicates P&L: green = profit, red = loss.
    """
    if not portfolio or not portfolio.positions:
        return ui.echart({"title": {"text": "No positions", "textStyle": {"color": "#666"}}}).classes("w-full").style(f"height:{height}")

    data: list[dict[str, Any]] = []
    for ticker, pos in portfolio.positions.items():
        pnl_pct = (pos.unrealized_pnl_eur / (pos.market_value_eur - pos.unrealized_pnl_eur) * 100) if (pos.market_value_eur - pos.unrealized_pnl_eur) > 0 else 0
        color = _pnl_color(pnl_pct)
        data.append({
            "name": f"{ticker}\n{pos.weight_pct:.1f}%",
            "value": round(pos.market_value_eur, 2),
            "itemStyle": {"color": color},
        })

    option = {
        "tooltip": {"formatter": "{b}<br/>Value: {c} EUR"},
        "series": [
            {
                "type": "treemap",
                "data": data,
                "roam": False,
                "breadcrumb": {"show": False},
                "label": {"show": True, "color": "#fff", "fontSize": 12},
                "itemStyle": {"borderColor": "#1e1e1e", "borderWidth": 2, "gapWidth": 2},
            }
        ],
    }
    return ui.echart(option).classes("w-full").style(f"height:{height}")


def _pnl_color(pnl_pct: float) -> str:
    """Map P&L percentage to a gradient colour."""
    if pnl_pct > 10:
        return "#16a34a"
    if pnl_pct > 0:
        return "#22c55e"
    if pnl_pct > -5:
        return "#f97316"
    return "#ef4444"
