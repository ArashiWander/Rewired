"""Gemini API client wrapper — pinned model fallback chain with diagnostic logging."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# ── Pinned model list (no auto-discovery, no dynamic routing) ────────────
# gemini-2.5-flash: fast, cheapest — tried first for fast feedback
# gemini-2.5-pro:   deep reasoning, evaluation, classification
# gemini-2.0-flash: widely available GA fallback
# Override via GEMINI_MODEL env var (escape hatch).
_PINNED_MODELS = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]


def _candidate_models() -> list[str]:
    """Return the pinned model list, with optional env-var override first."""
    override = os.environ.get("GEMINI_MODEL", "").strip()
    if override:
        return [override, *[m for m in _PINNED_MODELS if m != override]]
    return list(_PINNED_MODELS)


def list_available_models() -> list[dict]:
    """Probe the API to list models that support generateContent.

    Returns a list of dicts with 'name' and 'display_name' keys.
    Used by ``rewired doctor`` — NOT used for routing (pinned list only).
    """
    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or api_key == "your_gemini_api_key_here":
        return []
    try:
        client = genai.Client(api_key=api_key)
        result = []
        for m in client.models.list():
            methods = getattr(m, "supported_generation_methods", []) or []
            if "generateContent" in methods:
                raw_name = getattr(m, "name", "") or ""
                name = raw_name.removeprefix("models/") if raw_name else str(m)
                result.append({
                    "name": name,
                    "display_name": getattr(m, "display_name", ""),
                })
        return result
    except Exception as exc:
        logger.warning("Failed to list models: %s", exc)
        return []


def is_configured() -> bool:
    """Check if Gemini API is configured."""
    key = os.environ.get("GEMINI_API_KEY", "")
    return bool(key and key != "your_gemini_api_key_here")


def generate(
    prompt: str,
    system_instruction: str = "",
    search_grounding: bool = False,
    json_output: bool = False,
    max_retries: int = 2,
) -> str:
    """Generate a response from Gemini.

    Tries pinned models in order: gemini-2.5-flash, gemini-2.5-pro,
    gemini-2.0-flash. Override with GEMINI_MODEL env var.

    Parameters:
        prompt: The user prompt.
        system_instruction: Injected as system-level instruction.
        search_grounding: Enable Google Search for real-time web data.
        json_output: Force temperature=0 and JSON output mode.
        max_retries: Auto-retry with stricter penalty prompt on parse failure.
    """
    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or api_key == "your_gemini_api_key_here":
        return "[Gemini API key not configured. Set GEMINI_API_KEY in .env]"

    try:
        client = genai.Client(api_key=api_key)
        models = _candidate_models()

        for attempt in range(1, max_retries + 2):  # +2 because range is exclusive
            config_kwargs: dict = {}

            # Build system instruction with penalty prompt on retries
            effective_instruction = system_instruction
            if attempt > 1:
                penalty = (
                    "CRITICAL: Your previous response was malformed JSON. "
                    "Respond with ONLY a valid JSON object. No markdown, no code "
                    "fences, no explanation text. Just the raw JSON."
                )
                effective_instruction = f"{penalty}\n\n{system_instruction}" if system_instruction else penalty

            if effective_instruction:
                config_kwargs["system_instruction"] = effective_instruction

            # Temperature=0 for deterministic outputs (blueprint requirement)
            config_kwargs["temperature"] = 0.0

            if json_output:
                config_kwargs["response_mime_type"] = "application/json"

            if search_grounding:
                config_kwargs["tools"] = [
                    genai.types.Tool(google_search=genai.types.GoogleSearch()),
                ]

            config = genai.types.GenerateContentConfig(**config_kwargs)

            errors: list[str] = []
            for model_name in models:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=config,
                    )
                    if response.text:
                        logger.info("Gemini OK via %s (attempt %d)", model_name, attempt)
                        return response.text
                    return "[No response from Gemini]"
                except Exception as model_error:
                    logger.warning("Gemini model %s failed: %s", model_name, model_error)
                    errors.append(f"{model_name}: {model_error}")

            # If all models failed on this attempt, continue to next attempt
            if attempt <= max_retries:
                continue

            summary = "; ".join(errors[:3]) if errors else "unknown"
            logger.error("All candidate models failed after %d attempts: %s", max_retries + 1, summary)
            return f"[Gemini API error: all candidate models failed ({summary})]"

        # Should not reach here, but just in case
        return "[Gemini API error: max retries exceeded]"

    except Exception as e:
        return f"[Gemini API error: {e}]"
