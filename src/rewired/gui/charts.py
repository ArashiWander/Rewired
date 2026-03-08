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

# ── Financial colour helpers (module-level for reuse) ────────────────────
_HM_GREEN = (34, 197, 94)     # positive daily change
_HM_RED   = (239, 68, 68)     # negative daily change
_HM_GREY  = (100, 116, 139)   # neutral / no data


def _cell_color(avg_change: float, total_w: float, has_stocks: bool) -> str:
    """Return rgba() string: hue from PnL direction, alpha from weight."""
    if not has_stocks:
        return "rgba(100,116,139,0.06)"
    if avg_change > 0.05:
        r, g, b = _HM_GREEN
    elif avg_change < -0.05:
        r, g, b = _HM_RED
    else:
        r, g, b = _HM_GREY
    if total_w > 0:
        alpha = min(0.20 + total_w / 25, 0.92)
    else:
        alpha = 0.14 if has_stocks else 0.06
    return f"rgba({r},{g},{b},{alpha:.2f})"


def _text_color(avg_change: float, total_w: float, has_stocks: bool) -> str:
    """Dynamic contrast: light text on vivid cells, dim on light."""
    if not has_stocks:
        return "#555"
    if total_w > 12:
        return "#ffffff"
    return "#e0e0e0"


# ── 2b. Data builder (reused by live-refresh) ───────────────────────────


def _build_heatmap_cells(universe, heatmap_data: dict | None):
    """Build heatmap series data, metadata JSON and tooltip JS.

    Returns ``(js_data, meta_json_str, tooltip_js_str)``.
    Called by both initial render and the 5-second live-refresh path.
    """
    import json as _json
    from rewired.models.universe import Layer, Tier

    _cell_meta: dict[str, list[dict]] = {}
    _js_data: list[dict] = []

    for li, lyr in enumerate(Layer):
        for ti, tier_e in enumerate(Tier):
            key = (lyr.value, tier_e.value)
            stocks = heatmap_data.get(key, []) if heatmap_data else []

            # Fall back to universe list when no enriched data
            if not stocks and universe:
                raw = universe.get_by_coordinate(lyr, tier_e)
                stocks = [{"ticker": s.ticker, "name": s.name,
                           "price_usd": 0.0, "price_eur": 0.0,
                           "portfolio_value_eur": 0.0,
                           "weight_pct": 0.0, "daily_change_pct": 0.0,
                           "max_weight_pct": s.max_weight_pct} for s in raw]

            count = len(stocks)
            total_weight = sum(s.get("weight_pct", 0) for s in stocks)
            avg_chg = (
                sum(s.get("daily_change_pct", 0) for s in stocks) / count
                if count else 0.0
            )

            # Store metadata for tooltip
            cell_key = f"{ti}_{li}"
            _cell_meta[cell_key] = [
                {
                    "t": s.get("ticker", "?"),
                    "p": round(s.get("price_usd", 0), 2),
                    "v": round(s.get("portfolio_value_eur", 0), 2),
                    "c": round(s.get("daily_change_pct", 0), 2),
                    "w": round(s.get("weight_pct", 0), 1),
                }
                for s in stocks
            ]

            # ── Cell label: show ALL tickers with prices ─────────
            # Sort by portfolio weight descending so heaviest show first
            sorted_stocks = sorted(
                stocks, key=lambda s: s.get("weight_pct", 0), reverse=True,
            )

            if count == 0:
                label = "-"
            elif count <= 4:
                # Show every ticker with price + daily change
                parts: list[str] = []
                for s in sorted_stocks:
                    p = s.get("price_usd", 0)
                    chg = s.get("daily_change_pct", 0)
                    chg_s = f" {chg:+.1f}%" if p > 0 else ""
                    price_s = f" ${p:,.0f}" if p else ""
                    parts.append(f"{s['ticker']}{price_s}{chg_s}")
                label = "\n".join(parts)
            else:
                # 5+ stocks: top 3 compact + badge
                parts = []
                for s in sorted_stocks[:3]:
                    p = s.get("price_usd", 0)
                    price_s = f" ${p:,.0f}" if p else ""
                    parts.append(f"{s['ticker']}{price_s}")
                label = "\n".join(parts) + f"\n+{count - 3} more \u25b8"

            # ── Colour: PnL hue + weight intensity ───────────────
            colour = _cell_color(avg_chg, total_weight, count > 0)
            txt_col = _text_color(avg_chg, total_weight, count > 0)

            _js_data.append({
                "value": [ti, li, count],
                "label": {
                    "formatter": label,
                    "overflow": "truncate",
                    "width": 130,
                    "color": txt_col,
                    "fontSize": 10 if count > 2 else 11,
                    "lineHeight": 13 if count > 3 else (14 if count > 2 else 16),
                },
                "itemStyle": {"color": colour},
            })

    # Serialise cell metadata for the JS tooltip formatter
    _meta_json = _json.dumps(_cell_meta, separators=(",", ":"))

    _tooltip_js = (
        "function(params){"
        f"var meta={_meta_json};"
        "var d=params.data||params.value||[];"
        "var v=Array.isArray(d)?d:(d.value||[]);"
        "var key=v[0]+'_'+v[1];"
        "var items=meta[key]||[];"
        "if(!items.length)return'<span style=\"color:#888\">Empty cell</span>';"
        "var hdr='<div style=\"border-bottom:1px solid #555;padding-bottom:4px;margin-bottom:4px;'"
        "+'font-weight:bold;color:#ccc\">L'+(v[1]+1)+' / T'+(v[0]+1)+' \u2014 '"
        "+items.length+' asset'+(items.length>1?'s':'')+'</div>';"
        "return hdr+items.map(function(s){"
        "var cc=s.c>=0?'#22c55e':'#ef4444';"
        "var chg=s.p>0?' <span style=\"color:'+cc+';font-weight:600\">'+(s.c>=0?'+':'')+s.c.toFixed(2)+'%</span>':'';"
        "var pr=s.p>0?'$'+s.p.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2}):'';"
        "var vl=s.v>0?' <span style=\"color:#aaa\">(\u20ac'+s.v.toLocaleString(undefined,{maximumFractionDigits:0})+')</span>':'';"
        "var wt=s.w>0?' <span style=\"color:#888;font-size:11px\">'+s.w.toFixed(1)+'%</span>':'';"
        "return'<b>'+s.t+'</b> '+pr+vl+wt+chg;"
        "}).join('<br/>');"
        "}"
    )

    return _js_data, _meta_json, _tooltip_js


def build_heatmap_update(universe, heatmap_data: dict | None) -> str:
    """Build a JS object literal for ``:setOption(...)`` live refresh.

    NiceGUI evaluates args for colon-prefixed chart methods as raw
    JavaScript source, so this function returns a JS object literal string
    rather than a Python dict.
    """
    import json as _json

    _js_data, _meta_json, _tooltip_js = _build_heatmap_cells(
        universe, heatmap_data,
    )
    return (
        "{"
        f"series:[{{data:{_json.dumps(_js_data, separators=(',', ':'))}}}],"
        f"tooltip:{{formatter:({_tooltip_js})}}"
        "}"
    )


# ── 2c. Interactive LxT heatmap (unified single-pane-of-glass) ──────────


def interactive_lxt_heatmap(
    universe,
    heatmap_data: dict | None = None,
    height: str = "520px",
) -> ui.echart:
    """Layer × Tier heatmap with live price/value data inside cells.

    *heatmap_data* is a dict keyed by ``(layer_int, tier_int)`` → list of
    enriched stock dicts (from ``state.get_heatmap_data()``).  When
    provided, cell opacity encodes combined portfolio weight and labels
    show tickers with prices.  Falls back to stock-count display when
    data is unavailable.

    Tooltip shows **all** tickers with price, value, and daily change.
    Returns ``ui.echart`` so callers can bind ``.on("click", handler)``.
    """
    from rewired.models.universe import Layer, Tier

    layers = [f"L{l.value}" for l in Layer]
    tiers = [f"T{t.value}" for t in Tier]

    _js_data, _meta_json, _tooltip_js = _build_heatmap_cells(
        universe, heatmap_data,
    )

    option = {
        "tooltip": {
            "position": "top",
            "backgroundColor": "rgba(15,15,25,0.96)",
            "borderColor": "rgba(255,255,255,0.15)",
            "borderWidth": 1,
            "textStyle": {"color": "#eee", "fontSize": 12},
            "extraCssText": "border-radius:8px;box-shadow:0 4px 20px rgba(0,0,0,0.5);max-width:380px;",
        },
        "grid": {"top": 10, "bottom": 10, "left": 60, "right": 20},
        "xAxis": {
            "type": "category",
            "data": tiers,
            "position": "top",
            "splitArea": {"show": True, "areaStyle": {"color": ["rgba(255,255,255,0.02)", "rgba(0,0,0,0)"]}},
            "axisLabel": {"color": "#aaa", "fontSize": 14, "fontWeight": "bold"},
            "axisTick": {"show": False},
            "axisLine": {"lineStyle": {"color": "#333"}},
        },
        "yAxis": {
            "type": "category",
            "data": layers,
            "inverse": True,
            "splitArea": {"show": True, "areaStyle": {"color": ["rgba(255,255,255,0.02)", "rgba(0,0,0,0)"]}},
            "axisLabel": {"color": "#aaa", "fontSize": 14, "fontWeight": "bold"},
            "axisTick": {"show": False},
            "axisLine": {"lineStyle": {"color": "#333"}},
        },
        "series": [
            {
                "type": "heatmap",
                "data": _js_data,
                "label": {
                    "show": True,
                    "color": "#e0e0e0",
                    "fontSize": 11,
                    "lineHeight": 16,
                    "overflow": "truncate",
                    "width": 130,
                },
                "itemStyle": {
                    "borderColor": "rgba(255,255,255,0.10)",
                    "borderWidth": 1,
                    "borderRadius": 6,
                },
                "emphasis": {
                    "itemStyle": {
                        "shadowBlur": 16,
                        "shadowColor": "rgba(255,255,255,0.35)",
                        "borderColor": "#fbbf24",
                        "borderWidth": 2,
                    },
                },
            }
        ],
    }

    el = ui.echart(option).classes("w-full").style(f"height:{height}")

    # Inject JS tooltip formatter after chart mount.
    # NiceGUI treats colon-prefixed run_chart_method calls as raw JS source,
    # so the argument itself must be a JS object literal string, not a Python dict.
    el.on(
        "init",
        lambda _: el.run_chart_method(
            ":setOption",
            f"{{tooltip: {{formatter: ({_tooltip_js})}}}}",
        ),
    )

    return el


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
