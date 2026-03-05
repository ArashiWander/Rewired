"""Internationalisation support for the Rewired Index dashboard.

Provides a singleton language state and a ``t(key, **kwargs)`` lookup
function used by every GUI component to render text in the active language.
"""

from __future__ import annotations

from enum import Enum


class Lang(str, Enum):
    EN = "EN"
    ZH = "ZH"


class I18n:
    """Singleton holding the active language and the translation table."""

    _instance: I18n | None = None

    def __new__(cls) -> I18n:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.lang = Lang.EN
        return cls._instance

    lang: Lang

    def set_lang(self, lang: Lang) -> None:
        self.lang = lang


_i18n = I18n()


# ── Public API ───────────────────────────────────────────────────────────


def set_language(lang: Lang) -> None:
    _i18n.set_lang(lang)


def get_language() -> Lang:
    return _i18n.lang


def t(key: str, **kwargs) -> str:
    """Return the translated string for *key* in the active language.

    Supports ``str.format`` interpolation via *kwargs*.
    Falls back to English if the key is missing for the active language,
    and to the raw key if no translation exists at all.
    """
    entry = _STRINGS.get(key)
    if entry is None:
        return key.format(**kwargs) if kwargs else key
    text = entry.get(_i18n.lang, entry.get(Lang.EN, key))
    return text.format(**kwargs) if kwargs else text


# ── CJK-aware truncation helper ─────────────────────────────────────────


def smart_truncate(text: str, max_width: int) -> str:
    """Truncate *text* so its display width does not exceed *max_width*.

    CJK characters count as width 2; everything else counts as 1.
    """
    width = 0
    for i, ch in enumerate(text):
        cp = ord(ch)
        w = 2 if _is_wide(cp) else 1
        if width + w > max_width:
            return text[:i] + "\u2026"
        width += w
    return text


def _is_wide(cp: int) -> bool:
    """Return True for code-points that occupy two columns."""
    return (
        (0x1100 <= cp <= 0x115F)
        or (0x2E80 <= cp <= 0x9FFF)
        or (0xAC00 <= cp <= 0xD7AF)
        or (0xF900 <= cp <= 0xFAFF)
        or (0xFE10 <= cp <= 0xFE6F)
        or (0xFF01 <= cp <= 0xFF60)
        or (0xFFE0 <= cp <= 0xFFE6)
        or (0x20000 <= cp <= 0x2FA1F)
    )


# ── Layer / Tier name translations ──────────────────────────────────────

LAYER_NAMES_I18N = {
    Lang.EN: {1: "Physical Infra", 2: "Digital Infra", 3: "Core Intelligence", 4: "Applications", 5: "Frontier"},
    Lang.ZH: {1: "\u7269\u7406\u57fa\u7840\u8bbe\u65bd", 2: "\u6570\u5b57\u57fa\u7840\u8bbe\u65bd", 3: "\u6838\u5fc3\u667a\u80fd", 4: "\u5e94\u7528\u5c42", 5: "\u524d\u6cbf\u63a2\u7d22"},
}

TIER_NAMES_I18N = {
    Lang.EN: {1: "T1 Core", 2: "T2 Growth", 3: "T3 Thematic", 4: "T4 Speculation"},
    Lang.ZH: {1: "T1 \u6838\u5fc3", 2: "T2 \u6210\u957f", 3: "T3 \u4e3b\u9898", 4: "T4 \u6295\u673a"},
}


def layer_name(layer_value: int) -> str:
    return LAYER_NAMES_I18N.get(_i18n.lang, LAYER_NAMES_I18N[Lang.EN]).get(layer_value, f"L{layer_value}")


def tier_name(tier_value: int) -> str:
    return TIER_NAMES_I18N.get(_i18n.lang, TIER_NAMES_I18N[Lang.EN]).get(tier_value, f"T{tier_value}")


# ── Full translation table ──────────────────────────────────────────────
# Keys are stable identifiers; values map Lang → display string.
# Use {placeholder} for dynamic content filled via t(key, placeholder=val).

_STRINGS: dict[str, dict[Lang, str]] = {
    # ── Header / App ─────────────────────────────────────────────────
    "app.title": {
        Lang.EN: "REWIRED INDEX",
        Lang.ZH: "REWIRED \u6307\u6570",
    },
    "app.browser_title": {
        Lang.EN: "Rewired Index",
        Lang.ZH: "Rewired \u6307\u6570",
    },
    "app.refresh": {
        Lang.EN: "Refresh",
        Lang.ZH: "\u5237\u65b0",
    },
    "app.refreshing": {
        Lang.EN: "Refreshing...",
        Lang.ZH: "\u5237\u65b0\u4e2d\u2026",
    },
    "app.updated": {
        Lang.EN: "Updated: {time}",
        Lang.ZH: "\u5df2\u66f4\u65b0: {time}",
    },
    # Tab names
    "tab.actions": {
        Lang.EN: "Actions",
        Lang.ZH: "\u64cd\u4f5c",
    },
    "tab.signals": {
        Lang.EN: "Signals",
        Lang.ZH: "\u4fe1\u53f7",
    },
    "tab.portfolio": {
        Lang.EN: "Portfolio",
        Lang.ZH: "\u6295\u8d44\u7ec4\u5408",
    },
    "tab.analysis": {
        Lang.EN: "Analysis",
        Lang.ZH: "AI \u5206\u6790",
    },
    "tab.monitor": {
        Lang.EN: "Monitor",
        Lang.ZH: "\u76d1\u63a7",
    },

    # ── Header signal / status ───────────────────────────────────────
    "header.no_data": {
        Lang.EN: "NO DATA",
        Lang.ZH: "\u65e0\u6570\u636e",
    },
    "header.all_data_fresh": {
        Lang.EN: "All data fresh",
        Lang.ZH: "\u6570\u636e\u5df2\u662f\u6700\u65b0",
    },
    "status.pending": {
        Lang.EN: "pending",
        Lang.ZH: "\u7b49\u5f85\u4e2d",
    },
    "status.ok": {
        Lang.EN: "ok",
        Lang.ZH: "\u6b63\u5e38",
    },
    "status.stale": {
        Lang.EN: "stale ({age})",
        Lang.ZH: "\u8fc7\u671f ({age})",
    },
    "status.failed": {
        Lang.EN: "failed",
        Lang.ZH: "\u5931\u8d25",
    },

    # ── Tab 1: Actions ───────────────────────────────────────────────
    "actions.how_title": {
        Lang.EN: "How Decisions Are Calculated",
        Lang.ZH: "\u51b3\u7b56\u8ba1\u7b97\u65b9\u6cd5",
    },
    "actions.how_body": {
        Lang.EN: (
            "- Composite signal = weighted average of category colors (macro 30%, sentiment 30%, AI health 40%).\n"
            "- Safety override: if any category is **RED**, composite cannot be better than **ORANGE**.\n"
            "- Portfolio actions are produced in order by a 4-phase engine: "
            "**Take Profit \u2192 Signal Exit/Trim \u2192 New Buy \u2192 Redistribute**.\n"
            "- The **Reason** column in each action row tells the exact rule that triggered it."
        ),
        Lang.ZH: (
            "- \u7efc\u5408\u4fe1\u53f7 = \u5404\u7c7b\u522b\u989c\u8272\u7684\u52a0\u6743\u5e73\u5747\uff08\u5b8f\u89c2 30%\u3001\u60c5\u7eea 30%\u3001AI \u5065\u5eb7 40%\uff09\u3002\n"
            "- \u5b89\u5168\u8986\u76d6\uff1a\u5982\u679c\u4efb\u4f55\u7c7b\u522b\u4e3a **\u7ea2\u8272**\uff0c\u7efc\u5408\u4fe1\u53f7\u4e0d\u4f1a\u4f18\u4e8e **\u6a59\u8272**\u3002\n"
            "- \u6295\u8d44\u7ec4\u5408\u64cd\u4f5c\u6309 4 \u9636\u6bb5\u5f15\u64ce\u987a\u5e8f\u6267\u884c\uff1a"
            "**\u6b62\u76c8 \u2192 \u4fe1\u53f7\u9000\u51fa/\u51cf\u4ed3 \u2192 \u65b0\u4e70\u5165 \u2192 \u91cd\u65b0\u5206\u914d**\u3002\n"
            "- \u6bcf\u884c\u64cd\u4f5c\u7684 **\u539f\u56e0** \u5217\u663e\u793a\u89e6\u53d1\u8be5\u64cd\u4f5c\u7684\u786e\u5207\u89c4\u5219\u3002"
        ),
    },
    "actions.composite_label": {
        Lang.EN: "Current composite signal:",
        Lang.ZH: "\u5f53\u524d\u7efc\u5408\u4fe1\u53f7\uff1a",
    },
    "actions.playbook_title": {
        Lang.EN: "What To Do In This Tab",
        Lang.ZH: "\u672c\u9875\u64cd\u4f5c\u6307\u5357",
    },
    "actions.playbook_nodata": {
        Lang.EN: (
            "1. Click **Refresh** in the header.\n"
            "2. Wait for signal and portfolio data to load.\n"
            "3. Return to this tab to review actions."
        ),
        Lang.ZH: (
            "1. \u70b9\u51fb\u9876\u90e8\u7684 **\u5237\u65b0** \u6309\u94ae\u3002\n"
            "2. \u7b49\u5f85\u4fe1\u53f7\u548c\u6295\u8d44\u7ec4\u5408\u6570\u636e\u52a0\u8f7d\u3002\n"
            "3. \u8fd4\u56de\u672c\u9875\u67e5\u770b\u64cd\u4f5c\u5efa\u8bae\u3002"
        ),
    },
    "actions.guidance_green": {
        Lang.EN: "Risk posture is constructive. Execute priority order from top to bottom and deploy per targets.",
        Lang.ZH: "\u98ce\u9669\u59ff\u6001\u79ef\u6781\u3002\u6309\u4f18\u5148\u7ea7\u4ece\u4e0a\u5230\u4e0b\u6267\u884c\uff0c\u6309\u76ee\u6807\u914d\u7f6e\u90e8\u7f72\u3002",
    },
    "actions.guidance_yellow": {
        Lang.EN: "Moderate caution. Favor quality adds; avoid aggressive expansion in weaker tiers.",
        Lang.ZH: "\u9002\u5ea6\u8c28\u614e\u3002\u4f18\u5148\u52a0\u4ed3\u4f18\u8d28\u6807\u7684\uff0c\u907f\u514d\u5728\u8f83\u5f31\u5c42\u7ea7\u6fc0\u8fdb\u6269\u5f20\u3002",
    },
    "actions.guidance_orange": {
        Lang.EN: "Defensive mode. Prioritize trims/exits first, then reassess any buys.",
        Lang.ZH: "\u9632\u5fa1\u6a21\u5f0f\u3002\u4f18\u5148\u6267\u884c\u51cf\u4ed3/\u9000\u51fa\uff0c\u7136\u540e\u91cd\u65b0\u8bc4\u4f30\u4efb\u4f55\u4e70\u5165\u3002",
    },
    "actions.guidance_red": {
        Lang.EN: "Capital protection mode. Execute exits/trims first; defer discretionary buying.",
        Lang.ZH: "\u8d44\u672c\u4fdd\u62a4\u6a21\u5f0f\u3002\u5148\u6267\u884c\u9000\u51fa/\u51cf\u4ed3\uff0c\u63a8\u8fdf\u81ea\u4e3b\u4e70\u5165\u3002",
    },
    "actions.signal_posture": {
        Lang.EN: "**Signal posture:** {color} - {guidance}",
        Lang.ZH: "**\u4fe1\u53f7\u59ff\u6001\uff1a** {color} - {guidance}",
    },
    "actions.execution_order": {
        Lang.EN: "**Execution order:** follow the table by phase priority (1 to 4).",
        Lang.ZH: "**\u6267\u884c\u987a\u5e8f\uff1a** \u6309\u9636\u6bb5\u4f18\u5148\u7ea7\uff081 \u5230 4\uff09\u6267\u884c\u8868\u683c\u64cd\u4f5c\u3002",
    },
    "actions.after_trading": {
        Lang.EN: "**After trading:** record fills on the **Portfolio** tab, then click **Refresh**.",
        Lang.ZH: "**\u4ea4\u6613\u540e\uff1a** \u5728 **\u6295\u8d44\u7ec4\u5408** \u9875\u8bb0\u5f55\u6210\u4ea4\uff0c\u7136\u540e\u70b9\u51fb **\u5237\u65b0**\u3002",
    },
    "actions.no_actions": {
        Lang.EN: "No immediate actions are required right now.",
        Lang.ZH: "\u5f53\u524d\u65e0\u9700\u6267\u884c\u4efb\u4f55\u64cd\u4f5c\u3002",
    },
    "actions.queue": {
        Lang.EN: "Action queue: {total} total ({sell} SELL, {buy} BUY).",
        Lang.ZH: "\u64cd\u4f5c\u961f\u5217\uff1a\u5171 {total} \u9879\uff08{sell} \u5356\u51fa\uff0c{buy} \u4e70\u5165\uff09\u3002",
    },

    # ── Pies allocation ──────────────────────────────────────────────
    "pies.title": {
        Lang.EN: "Trading 212 Pies Allocation",
        Lang.ZH: "Trading 212 Pies \u914d\u7f6e",
    },
    "pies.signal": {
        Lang.EN: "Signal: {color}",
        Lang.ZH: "\u4fe1\u53f7\uff1a{color}",
    },
    "pies.allocated": {
        Lang.EN: "Allocated: {pct}%",
        Lang.ZH: "\u5df2\u5206\u914d\uff1a{pct}%",
    },
    "pies.cash_reserve": {
        Lang.EN: "Cash reserve: {pct}%",
        Lang.ZH: "\u73b0\u91d1\u50a8\u5907\uff1a{pct}%",
    },

    # ── Suggestions ──────────────────────────────────────────────────
    "suggest.title": {
        Lang.EN: "Suggested Actions",
        Lang.ZH: "\u5efa\u8bae\u64cd\u4f5c",
    },
    "suggest.balanced": {
        Lang.EN: "No actions needed - portfolio is balanced.",
        Lang.ZH: "\u65e0\u9700\u64cd\u4f5c \u2014 \u6295\u8d44\u7ec4\u5408\u5df2\u5e73\u8861\u3002",
    },
    "suggest.phase_tp": {
        Lang.EN: "Take Profit",
        Lang.ZH: "\u6b62\u76c8",
    },
    "suggest.phase_exit": {
        Lang.EN: "Signal Exit",
        Lang.ZH: "\u4fe1\u53f7\u9000\u51fa",
    },
    "suggest.phase_buy": {
        Lang.EN: "New Buy",
        Lang.ZH: "\u65b0\u4e70\u5165",
    },
    "suggest.phase_redist": {
        Lang.EN: "Redistribute",
        Lang.ZH: "\u91cd\u65b0\u5206\u914d",
    },

    # ── Signal Board ─────────────────────────────────────────────────
    "signal.board_title": {
        Lang.EN: "Signal Board",
        Lang.ZH: "\u4fe1\u53f7\u770b\u677f",
    },
    "signal.composite": {
        Lang.EN: "COMPOSITE",
        Lang.ZH: "\u7efc\u5408",
    },
    "signal.explain_title": {
        Lang.EN: "How To Read Signal Conclusions",
        Lang.ZH: "\u5982\u4f55\u89e3\u8bfb\u4fe1\u53f7\u7ed3\u8bba",
    },
    "signal.explain_body": {
        Lang.EN: (
            "- Each category is scored from color: GREEN=1, YELLOW=2, ORANGE=3, RED=4.\n"
            "- Composite is mapped from weighted score: <=1.5 GREEN, <=2.5 YELLOW, <=3.5 ORANGE, >3.5 RED.\n"
            "- Category weights: macro 30%, sentiment 30%, AI health 40%.\n"
            "- Use the drill-down below to see metric-level evidence and data source per category."
        ),
        Lang.ZH: (
            "- \u6bcf\u4e2a\u7c7b\u522b\u6309\u989c\u8272\u8bc4\u5206\uff1a\u7eff\u8272=1\u3001\u9ec4\u8272=2\u3001\u6a59\u8272=3\u3001\u7ea2\u8272=4\u3002\n"
            "- \u7efc\u5408\u4fe1\u53f7\u7531\u52a0\u6743\u5206\u6570\u6620\u5c04\uff1a\u22641.5 \u7eff\u8272\u3001\u22642.5 \u9ec4\u8272\u3001\u22643.5 \u6a59\u8272\u3001>3.5 \u7ea2\u8272\u3002\n"
            "- \u7c7b\u522b\u6743\u91cd\uff1a\u5b8f\u89c2 30%\u3001\u60c5\u7eea 30%\u3001AI \u5065\u5eb7 40%\u3002\n"
            "- \u5c55\u5f00\u4e0b\u65b9\u8be6\u60c5\u67e5\u770b\u6bcf\u4e2a\u7c7b\u522b\u7684\u6307\u6807\u7ea7\u8bc1\u636e\u548c\u6570\u636e\u6765\u6e90\u3002"
        ),
    },
    "signal.current_summary": {
        Lang.EN: "Current summary: {summary}",
        Lang.ZH: "\u5f53\u524d\u6458\u8981\uff1a{summary}",
    },
    "signal.no_readings": {
        Lang.EN: "No readings available.",
        Lang.ZH: "\u65e0\u53ef\u7528\u8bfb\u6570\u3002",
    },
    "signal.history_title": {
        Lang.EN: "Signal History",
        Lang.ZH: "\u4fe1\u53f7\u5386\u53f2",
    },
    "signal.no_history": {
        Lang.EN: "No signal changes recorded yet.",
        Lang.ZH: "\u5c1a\u672a\u8bb0\u5f55\u4fe1\u53f7\u53d8\u5316\u3002",
    },

    # ── Table headers (shared) ───────────────────────────────────────
    "th.ticker": {
        Lang.EN: "Ticker",
        Lang.ZH: "\u4ee3\u7801",
    },
    "th.name": {
        Lang.EN: "Name",
        Lang.ZH: "\u540d\u79f0",
    },
    "th.layer": {
        Lang.EN: "Layer",
        Lang.ZH: "\u5c42\u7ea7",
    },
    "th.tier": {
        Lang.EN: "Tier",
        Lang.ZH: "\u5206\u7ea7",
    },
    "th.target_pct": {
        Lang.EN: "Target %",
        Lang.ZH: "\u76ee\u6807 %",
    },
    "th.target_eur": {
        Lang.EN: "Target EUR",
        Lang.ZH: "\u76ee\u6807 EUR",
    },
    "th.action": {
        Lang.EN: "Action",
        Lang.ZH: "\u64cd\u4f5c",
    },
    "th.amount_eur": {
        Lang.EN: "Amount (EUR)",
        Lang.ZH: "\u91d1\u989d (EUR)",
    },
    "th.phase": {
        Lang.EN: "Phase",
        Lang.ZH: "\u9636\u6bb5",
    },
    "th.reason": {
        Lang.EN: "Reason",
        Lang.ZH: "\u539f\u56e0",
    },
    "th.indicator": {
        Lang.EN: "Indicator",
        Lang.ZH: "\u6307\u6807",
    },
    "th.value": {
        Lang.EN: "Value",
        Lang.ZH: "\u503c",
    },
    "th.signal": {
        Lang.EN: "Signal",
        Lang.ZH: "\u4fe1\u53f7",
    },
    "th.detail": {
        Lang.EN: "Detail",
        Lang.ZH: "\u8be6\u60c5",
    },
    "th.source": {
        Lang.EN: "Source",
        Lang.ZH: "\u6765\u6e90",
    },
    "th.time": {
        Lang.EN: "Time",
        Lang.ZH: "\u65f6\u95f4",
    },
    "th.from": {
        Lang.EN: "From",
        Lang.ZH: "\u4ece",
    },
    "th.to": {
        Lang.EN: "To",
        Lang.ZH: "\u81f3",
    },
    "th.summary": {
        Lang.EN: "Summary",
        Lang.ZH: "\u6458\u8981",
    },
    "th.shares": {
        Lang.EN: "Shares",
        Lang.ZH: "\u80a1\u6570",
    },
    "th.avg_cost": {
        Lang.EN: "Avg Cost",
        Lang.ZH: "\u5747\u4ef7",
    },
    "th.current": {
        Lang.EN: "Current",
        Lang.ZH: "\u73b0\u4ef7",
    },
    "th.value_eur": {
        Lang.EN: "Value (EUR)",
        Lang.ZH: "\u5e02\u503c (EUR)",
    },
    "th.pnl_eur": {
        Lang.EN: "P&L (EUR)",
        Lang.ZH: "\u76c8\u4e8f (EUR)",
    },
    "th.weight_pct": {
        Lang.EN: "Weight %",
        Lang.ZH: "\u6743\u91cd %",
    },
    "th.date": {
        Lang.EN: "Date",
        Lang.ZH: "\u65e5\u671f",
    },
    "th.price_eur": {
        Lang.EN: "Price (EUR)",
        Lang.ZH: "\u4ef7\u683c (EUR)",
    },
    "th.total_eur": {
        Lang.EN: "Total (EUR)",
        Lang.ZH: "\u603b\u8ba1 (EUR)",
    },
    "th.notes": {
        Lang.EN: "Notes",
        Lang.ZH: "\u5907\u6ce8",
    },
    "th.max_weight": {
        Lang.EN: "Max Weight %",
        Lang.ZH: "\u6700\u5927\u6743\u91cd %",
    },

    # ── Portfolio ────────────────────────────────────────────────────
    "portfolio.title": {
        Lang.EN: "Portfolio",
        Lang.ZH: "\u6295\u8d44\u7ec4\u5408",
    },
    "portfolio.no_positions": {
        Lang.EN: "No positions yet.",
        Lang.ZH: "\u6682\u65e0\u6301\u4ed3\u3002",
    },
    "portfolio.cash": {
        Lang.EN: "Cash: {val} EUR",
        Lang.ZH: "\u73b0\u91d1\uff1a{val} EUR",
    },
    "portfolio.invested": {
        Lang.EN: "Invested: {val} EUR",
        Lang.ZH: "\u5df2\u6295\u8d44\uff1a{val} EUR",
    },
    "portfolio.total": {
        Lang.EN: "Total: {val} EUR",
        Lang.ZH: "\u603b\u8ba1\uff1a{val} EUR",
    },

    # ── Universe matrix ──────────────────────────────────────────────
    "universe.title": {
        Lang.EN: "LxT Universe Matrix",
        Lang.ZH: "LxT \u80a1\u7968\u77e9\u9635",
    },

    # ── Trade form ───────────────────────────────────────────────────
    "trade.title": {
        Lang.EN: "Record a Trade",
        Lang.ZH: "\u8bb0\u5f55\u4ea4\u6613",
    },
    "trade.intro": {
        Lang.EN: (
            "Enter the details of a trade you have **already executed** on Trading 212. "
            "This updates your local portfolio state so signals and sizing stay accurate."
        ),
        Lang.ZH: (
            "\u8f93\u5165\u60a8\u5df2\u5728 Trading 212 \u4e0a **\u6267\u884c\u5b8c\u6bd5** \u7684\u4ea4\u6613\u8be6\u60c5\u3002"
            "\u8fd9\u5c06\u66f4\u65b0\u672c\u5730\u6295\u8d44\u7ec4\u5408\u72b6\u6001\uff0c\u4ee5\u4fdd\u6301\u4fe1\u53f7\u548c\u4ed3\u4f4d\u7ba1\u7406\u7684\u51c6\u786e\u6027\u3002"
        ),
    },
    "trade.ticker_label": {
        Lang.EN: "Ticker",
        Lang.ZH: "\u80a1\u7968\u4ee3\u7801",
    },
    "trade.ticker_placeholder": {
        Lang.EN: "e.g. NVDA",
        Lang.ZH: "\u4f8b\u5982 NVDA",
    },
    "trade.shares_label": {
        Lang.EN: "Shares",
        Lang.ZH: "\u80a1\u6570",
    },
    "trade.price_label": {
        Lang.EN: "Price per share (EUR)",
        Lang.ZH: "\u6bcf\u80a1\u4ef7\u683c (EUR)",
    },
    "trade.notes_label": {
        Lang.EN: "Notes (optional)",
        Lang.ZH: "\u5907\u6ce8\uff08\u53ef\u9009\uff09",
    },
    "trade.notes_placeholder": {
        Lang.EN: "e.g. Initial position",
        Lang.ZH: "\u4f8b\u5982 \u521d\u59cb\u5efa\u4ed3",
    },
    "trade.submit": {
        Lang.EN: "Submit Trade",
        Lang.ZH: "\u63d0\u4ea4\u4ea4\u6613",
    },
    "trade.err_ticker_required": {
        Lang.EN: "Ticker is required.",
        Lang.ZH: "\u80a1\u7968\u4ee3\u7801\u4e0d\u80fd\u4e3a\u7a7a\u3002",
    },
    "trade.err_ticker_format": {
        Lang.EN: "Ticker must be 1-10 letters/digits (e.g. NVDA, TSM).",
        Lang.ZH: "\u4ee3\u7801\u5fc5\u987b\u4e3a 1-10 \u4e2a\u5b57\u6bcd/\u6570\u5b57\uff08\u4f8b\u5982 NVDA\u3001TSM\uff09\u3002",
    },
    "trade.err_positive": {
        Lang.EN: "Shares and price must be positive.",
        Lang.ZH: "\u80a1\u6570\u548c\u4ef7\u683c\u5fc5\u987b\u4e3a\u6b63\u6570\u3002",
    },
    "trade.err_price_limit": {
        Lang.EN: "Price per share seems too high (max 100,000 EUR). Check for typos.",
        Lang.ZH: "\u6bcf\u80a1\u4ef7\u683c\u8fc7\u9ad8\uff08\u6700\u9ad8 100,000 EUR\uff09\uff0c\u8bf7\u68c0\u67e5\u662f\u5426\u8f93\u5165\u6709\u8bef\u3002",
    },
    "trade.err_sell_no_position": {
        Lang.EN: "Cannot SELL {ticker}: no position held.",
        Lang.ZH: "\u65e0\u6cd5\u5356\u51fa {ticker}\uff1a\u672a\u6301\u6709\u8be5\u80a1\u7968\u3002",
    },
    "trade.err_sell_too_many": {
        Lang.EN: "Cannot SELL {shares} shares of {ticker}: only {held} held.",
        Lang.ZH: "\u65e0\u6cd5\u5356\u51fa {ticker} \u7684 {shares} \u80a1\uff1a\u4ec5\u6301\u6709 {held} \u80a1\u3002",
    },
    "trade.err_notes_long": {
        Lang.EN: "Notes must be 200 characters or fewer.",
        Lang.ZH: "\u5907\u6ce8\u4e0d\u80fd\u8d85\u8fc7 200 \u4e2a\u5b57\u7b26\u3002",
    },
    "trade.recording": {
        Lang.EN: "Recording...",
        Lang.ZH: "\u8bb0\u5f55\u4e2d\u2026",
    },
    "trade.recorded": {
        Lang.EN: "Recorded: {action} {shares} x {ticker} @ {price} EUR",
        Lang.ZH: "\u5df2\u8bb0\u5f55\uff1a{action} {shares} x {ticker} @ {price} EUR",
    },
    "trade.error": {
        Lang.EN: "Error: {err}",
        Lang.ZH: "\u9519\u8bef\uff1a{err}",
    },
    "trade.confirm_title": {
        Lang.EN: "Confirm Trade",
        Lang.ZH: "\u786e\u8ba4\u4ea4\u6613",
    },
    "trade.confirm_body": {
        Lang.EN: "{action} {shares} shares of {ticker} at {price} EUR per share.\nTotal: {total} EUR",
        Lang.ZH: "{action} {ticker} {shares} \u80a1\uff0c\u6bcf\u80a1 {price} EUR\u3002\n\u603b\u8ba1\uff1a{total} EUR",
    },
    "trade.confirm_ok": {
        Lang.EN: "Confirm",
        Lang.ZH: "\u786e\u8ba4",
    },
    "trade.confirm_cancel": {
        Lang.EN: "Cancel",
        Lang.ZH: "\u53d6\u6d88",
    },
    # New-ticker fields
    "trade.new_ticker_note": {
        Lang.EN: "This ticker is not in the universe. Assign Layer, Tier, and Name to add it.",
        Lang.ZH: "\u8be5\u4ee3\u7801\u4e0d\u5728\u80a1\u7968\u6c60\u4e2d\u3002\u8bf7\u5206\u914d\u5c42\u7ea7\u3001\u5206\u7ea7\u548c\u540d\u79f0\u4ee5\u6dfb\u52a0\u3002",
    },
    "trade.stock_name_label": {
        Lang.EN: "Stock Name",
        Lang.ZH: "\u80a1\u7968\u540d\u79f0",
    },
    "trade.stock_name_placeholder": {
        Lang.EN: "e.g. Oracle",
        Lang.ZH: "\u4f8b\u5982 Oracle",
    },
    "trade.max_weight_label": {
        Lang.EN: "Max Weight %",
        Lang.ZH: "\u6700\u5927\u6743\u91cd %",
    },
    "trade.err_name_required": {
        Lang.EN: "Stock name is required for new tickers.",
        Lang.ZH: "\u65b0\u80a1\u7968\u5fc5\u987b\u586b\u5199\u540d\u79f0\u3002",
    },
    "trade.added_to_universe": {
        Lang.EN: "Added {ticker} to universe as L{layer}/T{tier}.",
        Lang.ZH: "\u5df2\u5c06 {ticker} \u6dfb\u52a0\u5230\u80a1\u7968\u6c60\uff0c\u5206\u7c7b\u4e3a L{layer}/T{tier}\u3002",
    },

    # ── Transaction history ──────────────────────────────────────────
    "txn.title": {
        Lang.EN: "Transaction History",
        Lang.ZH: "\u4ea4\u6613\u5386\u53f2",
    },
    "txn.empty": {
        Lang.EN: "No transactions recorded yet.",
        Lang.ZH: "\u5c1a\u672a\u8bb0\u5f55\u4ea4\u6613\u3002",
    },

    # ── AI Analysis ──────────────────────────────────────────────────
    "analysis.title": {
        Lang.EN: "AI Analyst",
        Lang.ZH: "AI \u5206\u6790\u5e08",
    },
    "analysis.intro": {
        Lang.EN: (
            "- **Run Analysis**: narrative review of current portfolio + signals.\n"
            "- **Regime Assessment**: market regime, confidence, key risk, and actionable insight.\n"
            "- Use this tab after checking **Actions** and **Signals** to validate decisions."
        ),
        Lang.ZH: (
            "- **\u8fd0\u884c\u5206\u6790**\uff1a\u5bf9\u5f53\u524d\u6295\u8d44\u7ec4\u5408\u548c\u4fe1\u53f7\u7684\u53d9\u8ff0\u6027\u5ba1\u67e5\u3002\n"
            "- **\u5e02\u573a\u8bc4\u4f30**\uff1a\u5e02\u573a\u4f53\u5236\u3001\u4fe1\u5fc3\u5ea6\u3001\u5173\u952e\u98ce\u9669\u548c\u53ef\u64cd\u4f5c\u5efa\u8bae\u3002\n"
            "- \u5728\u67e5\u770b **\u64cd\u4f5c** \u548c **\u4fe1\u53f7** \u9875\u540e\u4f7f\u7528\u672c\u9875\u9a8c\u8bc1\u51b3\u7b56\u3002"
        ),
    },
    "analysis.placeholder": {
        Lang.EN: "Click a button below to run Gemini analysis.",
        Lang.ZH: "\u70b9\u51fb\u4e0b\u65b9\u6309\u94ae\u8fd0\u884c Gemini \u5206\u6790\u3002",
    },
    "analysis.running": {
        Lang.EN: "*Running Gemini analysis...*",
        Lang.ZH: "*\u6b63\u5728\u8fd0\u884c Gemini \u5206\u6790\u2026*",
    },
    "analysis.running_regime": {
        Lang.EN: "*Running regime assessment...*",
        Lang.ZH: "*\u6b63\u5728\u8fd0\u884c\u5e02\u573a\u8bc4\u4f30\u2026*",
    },
    "analysis.error": {
        Lang.EN: "**Error:** {err}",
        Lang.ZH: "**\u9519\u8bef\uff1a** {err}",
    },
    "analysis.regime_label": {
        Lang.EN: "**Regime:**",
        Lang.ZH: "**\u5e02\u573a\u4f53\u5236\uff1a**",
    },
    "analysis.action_label": {
        Lang.EN: "**Action:**",
        Lang.ZH: "**\u64cd\u4f5c\u5efa\u8bae\uff1a**",
    },
    "analysis.risk_label": {
        Lang.EN: "**Key Risk:**",
        Lang.ZH: "**\u5173\u952e\u98ce\u9669\uff1a**",
    },
    "analysis.shift_prob": {
        Lang.EN: "*Regime shift probability (2wk):*",
        Lang.ZH: "*\u4f53\u5236\u8f6c\u53d8\u6982\u7387\uff082\u5468\uff09\uff1a*",
    },
    "analysis.btn_analysis": {
        Lang.EN: "Run Analysis",
        Lang.ZH: "\u8fd0\u884c\u5206\u6790",
    },
    "analysis.btn_regime": {
        Lang.EN: "Regime Assessment",
        Lang.ZH: "\u5e02\u573a\u8bc4\u4f30",
    },

    # ── Monitor ──────────────────────────────────────────────────────
    "monitor.title": {
        Lang.EN: "Signal Monitor",
        Lang.ZH: "\u4fe1\u53f7\u76d1\u63a7\u5668",
    },
    "monitor.intro": {
        Lang.EN: (
            "Runs periodic signal checks in the background, equivalent to `rewired monitor`. "
            "Signal changes will trigger Telegram alerts if configured."
        ),
        Lang.ZH: (
            "\u5728\u540e\u53f0\u5b9a\u671f\u8fd0\u884c\u4fe1\u53f7\u68c0\u67e5\uff0c\u7b49\u540c\u4e8e `rewired monitor`\u3002"
            "\u4fe1\u53f7\u53d8\u5316\u5c06\u89e6\u53d1 Telegram \u63d0\u9192\uff08\u5982\u5df2\u914d\u7f6e\uff09\u3002"
        ),
    },
    "monitor.stopped": {
        Lang.EN: "Stopped",
        Lang.ZH: "\u5df2\u505c\u6b62",
    },
    "monitor.running": {
        Lang.EN: "Running",
        Lang.ZH: "\u8fd0\u884c\u4e2d",
    },
    "monitor.schedule": {
        Lang.EN: (
            "- Signal check: **every 4 hours**\n"
            "- Portfolio summary: **daily at 18:30**\n"
            "- Weekly summary: **Monday 08:00**"
        ),
        Lang.ZH: (
            "- \u4fe1\u53f7\u68c0\u67e5\uff1a**\u6bcf 4 \u5c0f\u65f6**\n"
            "- \u6295\u8d44\u7ec4\u5408\u6458\u8981\uff1a**\u6bcf\u5929 18:30**\n"
            "- \u5468\u62a5\u6458\u8981\uff1a**\u5468\u4e00 08:00**"
        ),
    },
    "monitor.last_check": {
        Lang.EN: "Last check: {time}",
        Lang.ZH: "\u4e0a\u6b21\u68c0\u67e5\uff1a{time}",
    },
    "monitor.check_start": {
        Lang.EN: "[{time}] Check #{n} starting...",
        Lang.ZH: "[{time}] \u68c0\u67e5 #{n} \u5f00\u59cb\u2026",
    },
    "monitor.check_done": {
        Lang.EN: "[{time}] Check #{n} complete.",
        Lang.ZH: "[{time}] \u68c0\u67e5 #{n} \u5b8c\u6210\u3002",
    },
    "monitor.error": {
        Lang.EN: "[ERROR] {err}",
        Lang.ZH: "[\u9519\u8bef] {err}",
    },
    "monitor.started": {
        Lang.EN: "Monitor started.",
        Lang.ZH: "\u76d1\u63a7\u5df2\u542f\u52a8\u3002",
    },
    "monitor.stopped_log": {
        Lang.EN: "Monitor stopped.",
        Lang.ZH: "\u76d1\u63a7\u5df2\u505c\u6b62\u3002",
    },
    "monitor.btn_start": {
        Lang.EN: "Start Monitor",
        Lang.ZH: "\u542f\u52a8\u76d1\u63a7",
    },
    "monitor.btn_stop": {
        Lang.EN: "Stop Monitor",
        Lang.ZH: "\u505c\u6b62\u76d1\u63a7",
    },
    "monitor.btn_once": {
        Lang.EN: "Run Once Now",
        Lang.ZH: "\u7acb\u5373\u8fd0\u884c\u4e00\u6b21",
    },

    # ── Export ────────────────────────────────────────────────────────
    "export.title": {
        Lang.EN: "Export Data",
        Lang.ZH: "\u5bfc\u51fa\u6570\u636e",
    },
    "export.intro": {
        Lang.EN: "Download current state as JSON files for backup or external analysis.",
        Lang.ZH: "\u4e0b\u8f7d\u5f53\u524d\u72b6\u6001\u7684 JSON \u6587\u4ef6\uff0c\u7528\u4e8e\u5907\u4efd\u6216\u5916\u90e8\u5206\u6790\u3002",
    },
    "export.preparing_portfolio": {
        Lang.EN: "Preparing portfolio export...",
        Lang.ZH: "\u51c6\u5907\u5bfc\u51fa\u6295\u8d44\u7ec4\u5408\u2026",
    },
    "export.no_portfolio": {
        Lang.EN: "No portfolio data available.",
        Lang.ZH: "\u65e0\u6295\u8d44\u7ec4\u5408\u6570\u636e\u3002",
    },
    "export.portfolio_done": {
        Lang.EN: "Portfolio exported.",
        Lang.ZH: "\u6295\u8d44\u7ec4\u5408\u5df2\u5bfc\u51fa\u3002",
    },
    "export.failed": {
        Lang.EN: "Export failed: {err}",
        Lang.ZH: "\u5bfc\u51fa\u5931\u8d25\uff1a{err}",
    },
    "export.preparing_pies": {
        Lang.EN: "Preparing pies export...",
        Lang.ZH: "\u51c6\u5907\u5bfc\u51fa Pies \u914d\u7f6e\u2026",
    },
    "export.no_pies": {
        Lang.EN: "No pies data available.",
        Lang.ZH: "\u65e0 Pies \u6570\u636e\u3002",
    },
    "export.pies_done": {
        Lang.EN: "Pies allocation exported.",
        Lang.ZH: "Pies \u914d\u7f6e\u5df2\u5bfc\u51fa\u3002",
    },
    "export.preparing_csv": {
        Lang.EN: "Preparing CSV export...",
        Lang.ZH: "\u51c6\u5907\u5bfc\u51fa CSV\u2026",
    },
    "export.csv_done": {
        Lang.EN: "Pies CSV exported.",
        Lang.ZH: "Pies CSV \u5df2\u5bfc\u51fa\u3002",
    },
    "export.btn_portfolio": {
        Lang.EN: "Portfolio JSON",
        Lang.ZH: "\u6295\u8d44\u7ec4\u5408 JSON",
    },
    "export.btn_pies": {
        Lang.EN: "Pies JSON",
        Lang.ZH: "Pies JSON",
    },
    "export.btn_csv": {
        Lang.EN: "Pies CSV",
        Lang.ZH: "Pies CSV",
    },

    # ── Error / empty states (app.py) ────────────────────────────────
    "app.pies_unavailable": {
        Lang.EN: "Pies data unavailable.",
        Lang.ZH: "Pies \u6570\u636e\u4e0d\u53ef\u7528\u3002",
    },
    "app.pies_error": {
        Lang.EN: "Error loading Pies data.",
        Lang.ZH: "\u52a0\u8f7d Pies \u6570\u636e\u51fa\u9519\u3002",
    },
    "app.suggest_error": {
        Lang.EN: "Error loading suggestions.",
        Lang.ZH: "\u52a0\u8f7d\u5efa\u8bae\u51fa\u9519\u3002",
    },
    "app.signal_unavailable": {
        Lang.EN: "Signal data unavailable. Click Refresh to load.",
        Lang.ZH: "\u4fe1\u53f7\u6570\u636e\u4e0d\u53ef\u7528\u3002\u70b9\u51fb\u5237\u65b0\u4ee5\u52a0\u8f7d\u3002",
    },
    "app.signal_unavailable_short": {
        Lang.EN: "Signal data unavailable.",
        Lang.ZH: "\u4fe1\u53f7\u6570\u636e\u4e0d\u53ef\u7528\u3002",
    },

    # ── Universe management ──────────────────────────────────────────
    "unimgmt.title": {
        Lang.EN: "Universe Management",
        Lang.ZH: "\u80a1\u7968\u6c60\u7ba1\u7406",
    },
    "unimgmt.intro": {
        Lang.EN: "Add, edit, or remove stocks from the investment universe.",
        Lang.ZH: "\u6dfb\u52a0\u3001\u7f16\u8f91\u6216\u5220\u9664\u80a1\u7968\u6c60\u4e2d\u7684\u80a1\u7968\u3002",
    },
    "unimgmt.btn_edit": {
        Lang.EN: "Edit",
        Lang.ZH: "\u7f16\u8f91",
    },
    "unimgmt.btn_remove": {
        Lang.EN: "Remove",
        Lang.ZH: "\u5220\u9664",
    },
    "unimgmt.btn_save": {
        Lang.EN: "Save",
        Lang.ZH: "\u4fdd\u5b58",
    },
    "unimgmt.confirm_remove": {
        Lang.EN: "Remove {ticker} from the universe?",
        Lang.ZH: "\u786e\u8ba4\u4ece\u80a1\u7968\u6c60\u4e2d\u5220\u9664 {ticker}\uff1f",
    },
    "unimgmt.held_warning": {
        Lang.EN: "Cannot remove {ticker}: position is currently held. Sell first.",
        Lang.ZH: "\u65e0\u6cd5\u5220\u9664 {ticker}\uff1a\u5f53\u524d\u6301\u6709\u8be5\u80a1\u7968\uff0c\u8bf7\u5148\u5356\u51fa\u3002",
    },
    "unimgmt.removed": {
        Lang.EN: "Removed {ticker} from universe.",
        Lang.ZH: "\u5df2\u4ece\u80a1\u7968\u6c60\u5220\u9664 {ticker}\u3002",
    },
    "unimgmt.saved": {
        Lang.EN: "Saved changes for {ticker}.",
        Lang.ZH: "\u5df2\u4fdd\u5b58 {ticker} \u7684\u66f4\u6539\u3002",
    },
}
