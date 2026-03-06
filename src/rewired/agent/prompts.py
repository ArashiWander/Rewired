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

SYSTEM_CLASSIFIER = (
    "You are an investment universe classifier for the Rewired Index — a "
    "5-layer AI-era investment framework.  Given a company profile you must "
    "assign it to exactly one Layer (L1-L5) and one Tier (T1-T4).  "
    "Output ONLY valid JSON — no markdown, no explanation."
)

SYSTEM_REBALANCER = (
    "You are the Rewired Index autonomous universe rebalancer.  You review "
    "tier-mismatch evaluations and decide which reclassifications should be "
    "applied.  You must follow Cold Determinism rules: never auto-promote to "
    "T1 (require human approval), only downgrade by one tier at a time, and "
    "provide a clear rationale for each change.  Output ONLY valid JSON."
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

You MUST output your analysis STRICTLY as a single Markdown table.
Columns: Dimension | Status | Actionable Insight
Rows MUST include exactly these dimensions:
- Market Environment
- Signal Alignment
- Overweight Positions
- Underweight Positions
- Top Recommendation
- Key Risk

Do NOT output any paragraph text, introductions, or conclusions outside of
this table.  Every cell must be concise (max 30 words).
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

COMPANY_CLASSIFY = """\
Classify the following company into the Rewired Index investment universe.

COMPANY PROFILE:
- Ticker: {ticker}
- Name: {name}
- Sector: {sector}
- Industry: {industry}
- Market Cap: {market_cap}
- Description: {description}

LAYER DEFINITIONS (L dimension — structural position in the AI value chain):
- L1: Physical Infrastructure — semiconductors, hardware, energy for AI
- L2: Digital Infrastructure — cloud platforms, networking, data centres
- L3: Core Intelligence — companies building foundational AI models & tools
- L4: Dynamic Residual (Applications) — software using AI for end-user value
- L5: Frontier Exploration — early-stage, pre-revenue or speculative AI plays

TIER DEFINITIONS (T dimension — conviction & time horizon):
- T1: Core holdings — highest conviction, buy-and-hold, 40% base allocation
- T2: Growth engine — strong conviction, medium-term, 30% base allocation
- T3: Thematic allocation — moderate conviction, tactical, 20% base allocation
- T4: Speculation — low conviction, short-term, 10% base allocation

INSTRUCTIONS:
1. Assign the company to the single most appropriate Layer based on where it
   sits in the AI value chain.  Use its primary revenue driver, not adjacent
   business lines.
2. Assign a Tier based on how established, profitable, and moat-protected the
   company is.  Large-cap proven AI leaders belong in T1-T2; mid-cap or
   volatile names in T3; pre-profit or highly speculative in T4.
3. Suggest a max single-position weight (1.0 – 15.0 %).

Respond with ONLY valid JSON:
{{
  "layer": "<L1|L2|L3|L4|L5>",
  "tier": "<T1|T2|T3|T4>",
  "max_weight_pct": <1.0-15.0>,
  "reasoning": "<2-3 sentences explaining the classification>",
  "confidence": <0.0-1.0>
}}
"""


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

UNIVERSE_REBALANCE = """\
The Rewired Index evaluator has flagged the following tier mismatches after
a full universe evaluation scan.

TIER MISMATCHES:
{mismatches}

CURRENT UNIVERSE STATE:
{universe_state}

RULES (Cold Determinism):
1. NEVER auto-promote any stock to T1 — flag it as "needs_human_approval".
2. Only change tier by ONE step at a time (e.g. T2→T3, not T2→T4).
3. Provide confidence (0.0-1.0) for each proposed change.
4. If confidence < 0.6, flag as "monitor_only" instead of "apply".

Respond with ONLY valid JSON:
{{{{
  "changes": [
    {{{{
      "ticker": "<TICKER>",
      "current_tier": "<T1|T2|T3|T4>",
      "proposed_tier": "<T1|T2|T3|T4>",
      "action": "<apply|monitor_only|needs_human_approval>",
      "confidence": <0.0-1.0>,
      "reason": "<1-2 sentences>"
    }}}}
  ],
  "summary": "<1-2 sentences overall assessment>"
}}}}
"""

TIER_DOWNGRADE_CHECK = """\
Verify whether the following tier downgrade should proceed.

STOCK: {ticker} ({name})
CURRENT TIER: T{current_tier}
PROPOSED TIER: T{proposed_tier}

EVALUATION DATA:
- Composite Score: {composite_score}/10
- Fundamental Score: {fundamental_score}/10
- AI Relevance: {ai_relevance_score}/10
- Moat: {moat_score}/10
- Conviction: {conviction_level}
- Earnings Trend: {earnings_trend}
- Reasoning: {reasoning}

QUESTIONS TO ANSWER:
1. Is the downgrade justified by the data, or could it be a temporary dip?
2. Would this downgrade cause excessive portfolio churn?
3. Is there an upcoming catalyst (earnings, product launch) that should delay this?

Respond with ONLY valid JSON:
{{{{
  "proceed": <true|false>,
  "reason": "<2-3 sentences>",
  "delay_until": "<null|ISO date if should wait>"
}}}}
"""
