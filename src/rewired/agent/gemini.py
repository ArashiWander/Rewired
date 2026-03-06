"""Gemini API client wrapper — pinned model fallback chain with diagnostic logging."""

from __future__ import annotations

import logging
import os
import threading
import time

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# ── Pinned model list (no auto-discovery, no dynamic routing) ────────────
# gemini-2.5-flash: fast, cheapest — tried first for fast feedback
# gemini-2.5-pro:   deep reasoning, evaluation, classification
# gemini-2.0-flash: widely available GA fallback
# Override via GEMINI_MODEL env var (escape hatch).
_PINNED_MODELS = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]


# ── Global call counter (thread-safe) ────────────────────────────────────
_call_lock = threading.Lock()
_call_count: int = 0
_call_count_window_start: float = 0.0
_CALL_COUNT_WINDOW_SECONDS = 300  # 5-minute rolling window


def get_call_stats() -> dict:
    """Return current call statistics for observability."""
    with _call_lock:
        return {
            "total_calls": _call_count,
            "window_start": _call_count_window_start,
            "window_seconds": _CALL_COUNT_WINDOW_SECONDS,
        }


def _increment_call_count() -> int:
    """Increment and return the call count; resets every 5 minutes."""
    global _call_count, _call_count_window_start
    now = time.time()
    with _call_lock:
        if now - _call_count_window_start > _CALL_COUNT_WINDOW_SECONDS:
            _call_count = 0
            _call_count_window_start = now
        _call_count += 1
        current = _call_count
    return current


# ── Rate-limit error detection ───────────────────────────────────────────

def _is_rate_limit_error(error: Exception) -> bool:
    """Return True if the error indicates quota exhaustion (429)."""
    msg = str(error).lower()
    return "429" in msg or "resource_exhausted" in msg or "quota" in msg


def _is_timeout_error(error: Exception) -> bool:
    """Return True if the error indicates a deadline/timeout (504)."""
    msg = str(error).lower()
    return "504" in msg or "deadline_exceeded" in msg or "timed out" in msg


def _is_connection_reset_error(error: Exception) -> bool:
    """Return True if the error indicates a socket reset/abort from the remote side."""
    if isinstance(error, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
        return True

    msg = str(error).lower()
    return (
        "10054" in msg
        or "connection reset" in msg
        or "forcibly closed" in msg
        or "broken pipe" in msg
        or "connection aborted" in msg
    )


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
    max_retries: int = 1,
    timeout_seconds: int = 60,
) -> str:
    """Generate a response from Gemini.

    Tries pinned models in order: gemini-2.5-flash, gemini-2.5-pro,
    gemini-2.0-flash. Override with GEMINI_MODEL env var.

    On 429 RESOURCE_EXHAUSTED or 504 DEADLINE_EXCEEDED, stops the model
    cascade immediately and returns an error — these are quota/load issues,
    not model-availability problems.

    Parameters:
        prompt: The user prompt.
        system_instruction: Injected as system-level instruction.
        search_grounding: Enable Google Search for real-time web data.
        json_output: Force temperature=0 and JSON output mode.
        max_retries: Auto-retry with stricter penalty prompt on parse failure.
            Default 1 (max 2 attempts per model).
        timeout_seconds: Per-model call timeout in seconds (default 60).
    """
    from google import genai

    if json_output and search_grounding:
        logger.warning(
            "Disabling Gemini search grounding because tool use is unsupported with JSON output mode",
        )
        search_grounding = False

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or api_key == "your_gemini_api_key_here":
        return "[Gemini API key not configured. Set GEMINI_API_KEY in .env]"

    try:
        client = genai.Client(
            api_key=api_key,
            http_options={"timeout": timeout_seconds * 1000},
        )
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
                call_num = _increment_call_count()
                logger.info(
                    "Gemini call #%d: model=%s attempt=%d",
                    call_num, model_name, attempt,
                )
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

                    if _is_connection_reset_error(model_error):
                        logger.error("Gemini connection reset (%s): %s", model_name, model_error)
                        return (
                            f"[Gemini network error: connection reset while calling {model_name}. "
                            "Retry later.]"
                        )

                    # On rate-limit (429) or timeout (504), stop immediately.
                    # These are quota/load issues — trying the next model will
                    # only make things worse.
                    if _is_rate_limit_error(model_error):
                        msg = f"Gemini quota exhausted ({model_name}): {model_error}"
                        logger.error(msg)
                        return f"[Gemini rate limit: {model_name} returned 429 RESOURCE_EXHAUSTED. Retry later.]"
                    if _is_timeout_error(model_error):
                        msg = f"Gemini timeout ({model_name}): {model_error}"
                        logger.error(msg)
                        return f"[Gemini timeout: {model_name} returned 504 DEADLINE_EXCEEDED. Retry later.]"

            # If all models failed on this attempt, back off before retrying
            if attempt <= max_retries:
                backoff = 2 ** attempt  # 2s, 4s, ...
                logger.info(
                    "All models failed on attempt %d, backing off %ds",
                    attempt, backoff,
                )
                time.sleep(backoff)
                continue

            summary = "; ".join(errors[:3]) if errors else "unknown"
            logger.error("All candidate models failed after %d attempts: %s", max_retries + 1, summary)
            return f"[Gemini API error: all candidate models failed ({summary})]"

        # Should not reach here, but just in case
        return "[Gemini API error: max retries exceeded]"

    except Exception as e:
        return f"[Gemini API error: {e}]"
