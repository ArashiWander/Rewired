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

SYSTEM_EVALUATOR = (
    "You are a strict fundamental equity evaluator.  You receive structured "
    "financial data and must produce a deterministic JSON assessment.  Never "
    "invent data.  If a field is unknowable from the inputs, set it to null.  "
    "Output ONLY valid JSON — no markdown, no explanation."
)

SYSTEM_REGIME = (
    "You are a financial regime analyst.  Output ONLY valid JSON."
)

SYSTEM_CAPEX = (
    "You are an expert AI-sector capital-expenditure analyst.  Evaluate the "
    "CAPEX trends of the Big 4 hyperscalers (MSFT, GOOGL, AMZN, META) to "
    "determine the health of the AI infrastructure build-out.  Focus on "
    "quarter-over-quarter trends, management commentary, and whether any "
    "company is signalling a CAPEX cut.  Output ONLY valid JSON."
)


# ── CAPEX health prompt (used by data/ai_health.py) ─────────────────────

CAPEX_HEALTH = """\
{earnings_context}

Based on the latest available earnings data and public statements above,
evaluate the AI infrastructure CAPEX cycle for each Big 4 hyperscaler
(Microsoft, Alphabet/Google, Amazon, Meta).

Score the overall AI CAPEX health on a 1-4 scale:
- 4 = GREEN: All CAPEX accelerating, strong AI spending commitments
- 3 = YELLOW: CAPEX stable/plateau, no cuts signaled
- 2 = ORANGE: CAPEX growth decelerating, cautious management tone
- 1 = RED: Any Big 4 signaling or executing CAPEX CUT (VETO trigger)

CRITICAL: If ANY of the Big 4 is cutting AI/cloud CAPEX, the score MUST be 1 (RED).
This overrides everything else.

Respond with ONLY valid JSON (no markdown, no code fences):
{{
  "score": <1-4>,
  "trend": "<accelerating|stable|decelerating|contracting>",
  "veto_triggered": <true|false>,
  "key_management_quote": "<most relevant direct quote about CAPEX plans>",
  "reasoning": "<2-3 sentences explaining the assessment>",
  "company_details": {{
    "MSFT": "<1-2 sentence CAPEX assessment>",
    "GOOGL": "<1-2 sentence CAPEX assessment>",
    "AMZN": "<1-2 sentence CAPEX assessment>",
    "META": "<1-2 sentence CAPEX assessment>"
  }}
}}
"""


# ── Per-company evaluation (used by agent/evaluator.py) ──────────────────

COMPANY_EVALUATE = """\
Evaluate {ticker} ({name}) as a potential holding in the Rewired Index AI
investment framework.

COMPANY POSITION:
- Layer: L{layer} ({layer_name})
- Tier : T{tier} ({tier_name})
- Notes: {notes}

FINANCIAL DATA (FMP):
{financial_data}

RECENT EARNINGS:
{earnings_data}

KEY METRICS:
{metrics_data}

INSTRUCTIONS:
1. Assess the company's fundamentals relative to its LxT position.
2. Evaluate management quality, competitive moat, and AI relevance.
3. Determine if the current tier classification is appropriate.
4. Identify the single biggest risk and single biggest catalyst.

Respond with ONLY valid JSON:
{{
  "ticker": "{ticker}",
  "fundamental_score": <1-10>,
  "ai_relevance_score": <1-10>,
  "moat_score": <1-10>,
  "management_score": <1-10>,
  "composite_score": <1.0-10.0>,
  "tier_appropriate": <true|false>,
  "suggested_tier_change": "<null|T1|T2|T3|T4>",
  "biggest_risk": "<one sentence>",
  "biggest_catalyst": "<one sentence>",
  "conviction_level": "<high|medium|low>",
  "reasoning": "<3-4 sentences summarizing the assessment>",
  "earnings_trend": "<improving|stable|deteriorating>"
}}
"""


# ── Market regime assessment ─────────────────────────────────────────────

REGIME_ASSESS = """\
Given the following Rewired Index data, produce a market regime assessment.

CURRENT SIGNALS:
{signal_data}

PORTFOLIO STATE:
{portfolio_data}

TARGET PIES ALLOCATION:
{pies_data}

Assess the overall market regime by considering ALL signals together — macro
conditions, sentiment, and AI structural health.  Consider cross-signal
divergences (e.g. strong AI health but weak macro could signal a narrowing
rally).

Respond with ONLY valid JSON:
{{
  "regime": "<risk_on|neutral|risk_off|crisis>",
  "confidence": <0.0-1.0>,
  "reasoning": "<2-3 sentences explaining the regime and cross-signal dynamics>",
  "actionable_insight": "<one specific, concrete action for this 3 100 EUR T212 portfolio>",
  "key_risk": "<the single most important risk to monitor this week>",
  "regime_shift_probability": <0.0-1.0 probability of regime change in next 2 weeks>
}}

REGIME DEFINITIONS:
- risk_on : Broad strength across signals, favorable for full allocation
- neutral : Mixed signals, maintain current positions, limit new entries
- risk_off: Deteriorating conditions, defensive positioning warranted
- crisis  : Multiple RED signals, capital preservation mode
"""


# ── Full portfolio analysis ──────────────────────────────────────────────

PORTFOLIO_ANALYSIS = """\
Analyze the current state of this Rewired Index portfolio and signals.

CURRENT SIGNALS:
{signal_data}

PORTFOLIO STATE:
{portfolio_data}

TARGET PIES ALLOCATION (what the system recommends):
{pies_data}

Provide:
1. A brief assessment of the current market environment (2-3 sentences)
2. Whether the portfolio allocation aligns with the current signal color
3. Gap analysis: which positions are overweight/underweight vs Pies targets
4. Top 2-3 specific, actionable recommendations
5. One key risk to watch this week

Keep it concise — this is a quick daily briefing, not a research report.
"""


# ── Signal-only analysis ─────────────────────────────────────────────────

SIGNAL_ANALYSIS = """\
Current Rewired Index signals:

{signal_data}

In 3-5 sentences, explain what these signals mean for AI sector investment
positioning right now.  What is the most important thing to watch this week?
"""


# ── Stock analysis ───────────────────────────────────────────────────────

STOCK_ANALYSIS = """\
Analyze {name} ({ticker}) within the Rewired Index framework.

Position in framework: Layer L{layer}, Tier T{tier}
Max weight: {max_weight_pct}%
Notes: {notes}

Does this stock's current position and recent performance justify its
L{layer}/T{tier} classification?  Should we consider changing its tier?
Any specific catalysts or risks to note?  Keep it to 4-6 sentences.
"""
