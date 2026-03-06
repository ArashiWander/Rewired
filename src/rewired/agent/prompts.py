"""Centralized prompt registry for all Gemini interactions.

Every prompt template used by the agent layer lives here so they can be
audited, versioned, and tested in one place.  Templates use standard
``str.format()`` placeholders.

Naming convention: ``{DOMAIN}_{ACTION}`` in UPPER_SNAKE_CASE.
"""

from __future__ import annotations

# ── System instructions ──────────────────────────────────────────────────

SYSTEM_ANALYST = (
    "You are the Rewired Index AI analyst.  You analyze market signals and "
    "portfolio positions within the Rewired Index framework — a 5-layer "
    "investment system for the AI revolution.  The portfolio uses EUR.  Total "
    "capital is approximately 3 100 EUR on a Trading 212 simulation account.  "
    "Provide concise, actionable analysis.  Be direct about risks.  Use data, "
    "not opinions."
)

# SYSTEM_EVALUATOR removed — company evaluation decoupled to Oracle Gateway

SYSTEM_REGIME = (
    "You are a financial regime analyst.  Output ONLY valid JSON."
)

SYSTEM_CAPEX = (
    "You are an expert AI-sector capital-expenditure data extractor.  You receive "
    "actual quarterly financial data and recent SEC filings for the Big 4 hyperscalers "
    "(MSFT, GOOGL, AMZN, META).  Your ONLY job is to extract factual CAPEX numbers "
    "and verbatim management quotes.  You must NOT perform trend analysis, scoring, "
    "or subjective assessment.  Output ONLY valid JSON — no markdown, no code fences, "
    "no explanation."
)

# SYSTEM_CLASSIFIER removed — classification decoupled to Oracle Gateway

# SYSTEM_REBALANCER removed — rebalancer simplified to read universe.yaml directly


# ── CAPEX health prompt (used by data/ai_health.py) ─────────────────────

CAPEX_HEALTH = """\
{earnings_context}

Based on the quarterly financial data and SEC filings above, extract the
following CAPEX facts for each Big 4 hyperscaler (Microsoft, Alphabet/Google,
Amazon, Meta).

For EACH company you MUST provide:
- capex_absolute_bn: float — most recent quarter CapEx in billions USD (pure number)
- qoq_growth_pct: float — quarter-over-quarter CapEx growth percentage
- yoy_growth_pct: float — year-over-year CapEx growth percentage
- explicit_guidance_cut_mentioned: boolean — True ONLY if management explicitly
  stated they are reducing or cutting future AI/cloud infrastructure spending.
  "Optimizing" or "reprioritizing" does NOT count as a cut.
- exact_capex_quote: string — the most relevant verbatim quote from management
  regarding CapEx plans (max 2 sentences)

CRITICAL RULES:
- All numeric fields MUST be pure floats (e.g. 14.2, not "14.2 billion")
- If data for a company is unavailable, use 0.0 for numbers, false for booleans,
  and "data unavailable" for strings
- Do NOT perform any trend analysis, scoring, or subjective assessment
- Do NOT wrap your response in markdown code fences

Respond with ONLY this exact JSON structure:
{{
  "MSFT": {{
    "capex_absolute_bn": <float>,
    "qoq_growth_pct": <float>,
    "yoy_growth_pct": <float>,
    "explicit_guidance_cut_mentioned": <true|false>,
    "exact_capex_quote": "<verbatim quote>"
  }},
  "GOOGL": {{
    "capex_absolute_bn": <float>,
    "qoq_growth_pct": <float>,
    "yoy_growth_pct": <float>,
    "explicit_guidance_cut_mentioned": <true|false>,
    "exact_capex_quote": "<verbatim quote>"
  }},
  "AMZN": {{
    "capex_absolute_bn": <float>,
    "qoq_growth_pct": <float>,
    "yoy_growth_pct": <float>,
    "explicit_guidance_cut_mentioned": <true|false>,
    "exact_capex_quote": "<verbatim quote>"
  }},
  "META": {{
    "capex_absolute_bn": <float>,
    "qoq_growth_pct": <float>,
    "yoy_growth_pct": <float>,
    "explicit_guidance_cut_mentioned": <true|false>,
    "exact_capex_quote": "<verbatim quote>"
  }}
}}

WARNING: If your response is not valid JSON matching this exact schema, you
will be penalized and the request will be retried with your error appended.
"""""


# COMPANY_EVALUATE removed — company evaluation decoupled to Oracle Gateway


# ── Market regime assessment ─────────────────────────────────────────────

# REGIME_ASSESS removed — regime is now computed deterministically by the
# Boolean truth-table waterfall in signals/composite.py + hysteresis state
# machine in signals/engine.py.  Do NOT reintroduce LLM-based regime assessment.


# ── Full portfolio analysis ──────────────────────────────────────────────

PORTFOLIO_ANALYSIS = """\
Analyze the current state of this Rewired Index portfolio and signals.

CURRENT SIGNALS:
{signal_data}

PORTFOLIO STATE:
{portfolio_data}

TARGET PIES ALLOCATION (what the system recommends):
{pies_data}

You MUST structure your response in exactly two sections:

## Raw Data
Output a Markdown table with these columns: Dimension | Status | Value
Rows MUST include exactly these dimensions:
- Market Environment
- Signal Alignment
- Overweight Positions
- Underweight Positions
- Top Recommendation
- Key Risk

Every cell must be concise (max 30 words).

## Interpretation
Write a concise paragraph (3-5 sentences) explaining what the data above means
in plain language.  **Bold** the key phrases and main conclusions so users can
quickly scan the takeaways.  For example: "**Signals are aligned bullish**,
suggesting the portfolio can stay fully deployed."

Do NOT output any other sections, introductions, or sign-offs.
"""


# ── Signal-only analysis ─────────────────────────────────────────────────

SIGNAL_ANALYSIS = """\
Current Rewired Index signals:

{signal_data}

You MUST output your analysis STRICTLY as a single Markdown table.
Columns: Signal | Reading | Implication | Watch This Week
Rows MUST include one row for each of: Macro, Sentiment, AI Health, and a
final Summary row.

Do NOT output any paragraph text, introductions, or conclusions outside of
this table.  Every cell must be concise (max 25 words).
"""


# ── Asset classification (used by universe onboarding) ──────────────────

# COMPANY_CLASSIFY removed — classification decoupled to Oracle Gateway


# ── Stock analysis ───────────────────────────────────────────────────────

STOCK_ANALYSIS = """\
Analyze {name} ({ticker}) within the Rewired Index framework.

Position in framework: Layer L{layer}, Tier T{tier}
Max weight: {max_weight_pct}%
Notes: {notes}

You MUST output your analysis STRICTLY as a single Markdown table.
Columns: Aspect | Assessment | Action
Rows MUST include exactly: Classification Fit, Recent Performance,
Catalysts, Risks, Tier Recommendation.

Do NOT output any paragraph text, introductions, or conclusions outside of
this table.  Every cell must be concise (max 25 words).
"""


# ── Universe rebalancer (used by agent/rebalancer.py) ────────────────────

# UNIVERSE_REBALANCE and TIER_DOWNGRADE_CHECK removed — rebalancer simplified


# ── System Spirit (read-only AI Copilot) ─────────────────────────────────

SYSTEM_SPIRIT = (
    "You are the Rewired Index System Spirit — a read-only AI Copilot "
    "embedded in a deterministic investment system.  You can SEE all signals, "
    "portfolio positions, and allocation targets, but you have ZERO authority "
    "to change any of them.  The regime signal (RED/ORANGE/YELLOW/GREEN) is "
    "computed by hardcoded boolean rules, NOT by you.  Your role is strictly "
    "to EXPLAIN what the system is doing and why, in plain language.\n\n"
    "Rules:\n"
    "- Never recommend specific buy/sell actions.  Say what the SYSTEM "
    "recommends and explain the logic behind it.\n"
    "- Never claim to control or influence the signal, sizing, or "
    "allocation.  You are an observer and narrator.\n"
    "- Refer to signal colors and rule names when explaining.\n"
    "- Be concise, direct, data-driven.  Bold key phrases.\n"
    "- Currency is EUR.  The portfolio is on Trading 212."
)

MARKET_BRIEFING = """\
Generate a concise market briefing for the Rewired Index portfolio.

CURRENT SIGNALS:
{signal_data}

PORTFOLIO STATE:
{portfolio_data}

TARGET ALLOCATION:
{pies_data}

Structure your briefing EXACTLY like this:

## Regime
One sentence: current signal color, the rule that triggered it, and whether
a veto is active.

## Portfolio Snapshot
2-3 bullet points: total value, cash %, top position, biggest drift from
target.

## What the System Is Doing
2-3 sentences explaining what the constraint solver would do next (buys,
sells, rebalance) and WHY, referencing the specific signal rules.

## Watch List
2-3 bullet points: data releases or events this week that could shift the
signal.

Do NOT add introductions, sign-offs, or disclaimers.
"""

SPIRIT_FOLLOWUP = """\
Conversation so far:
{history}

Current system state (read-only context):
- Signals: {signal_summary}
- Portfolio value: {portfolio_value} EUR | Cash: {cash_pct}%

User question:
{question}

Answer concisely.  If the question is about a signal or rule, cite the
specific rule name and threshold.  If it asks you to DO something (trade,
change signal, override), politely decline and explain you are read-only.
"""
