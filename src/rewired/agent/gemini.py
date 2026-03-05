"""Gemini API client wrapper."""

from __future__ import annotations

import os
import re
from dotenv import load_dotenv

load_dotenv()


_STATIC_FALLBACK_MODELS = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
]


def _normalize_model_name(name: str) -> str:
    """Normalize SDK model names (e.g. models/gemini-2.5-pro -> gemini-2.5-pro)."""
    if name.startswith("models/"):
        return name.split("/", 1)[1]
    return name


def _model_rank(name: str) -> tuple[float, int, int, str]:
    """Rank models so strongest Pro models are preferred first.

    Higher tuple sorts first when reverse=True:
    - version number (e.g. 3.1 > 3.0 > 2.5)
    - pro preference over non-pro
    - stable preference over preview/experimental
    """
    model = _normalize_model_name(name).lower()

    version = 0.0
    match = re.search(r"gemini-(\d+(?:\.\d+)?)", model)
    if match:
        try:
            version = float(match.group(1))
        except ValueError:
            version = 0.0

    is_pro = 1 if "-pro" in model else 0
    is_stable = 0 if any(tag in model for tag in ("preview", "experimental", "exp")) else 1

    return (version, is_pro, is_stable, model)


def _supports_generate_content(model_obj) -> bool:
    """Return True if a model advertises generate-content support."""
    methods = (
        getattr(model_obj, "supported_generation_methods", None)
        or getattr(model_obj, "supportedGenerationMethods", None)
        or getattr(model_obj, "supported_actions", None)
        or []
    )
    normalized = [str(m).lower() for m in methods]
    return any(
        "generatecontent" in method
        or "generate_content" in method
        or method.endswith("generate")
        for method in normalized
    )


def _discover_candidate_models(client) -> list[str]:
    """Discover candidate Gemini models from API, strongest-first.

    Falls back to static preference list if discovery fails or returns nothing useful.
    """
    discovered: list[str] = []

    try:
        for model_obj in client.models.list():
            name = _normalize_model_name(getattr(model_obj, "name", ""))
            if not name:
                continue
            lowered = name.lower()
            if not lowered.startswith("gemini-"):
                continue
            if "embedding" in lowered:
                continue
            if not _supports_generate_content(model_obj):
                continue
            discovered.append(name)
    except Exception:
        discovered = []

    if discovered:
        discovered = sorted(set(discovered), key=_model_rank, reverse=True)
        for fallback in _STATIC_FALLBACK_MODELS:
            if fallback not in discovered:
                discovered.append(fallback)
        return discovered

    return list(_STATIC_FALLBACK_MODELS)


def _candidate_models(client) -> list[str]:
    """Return preferred model candidates in order.

    If GEMINI_MODEL is set, use it first as an explicit override.
    """
    override = os.environ.get("GEMINI_MODEL", "").strip()
    base = _discover_candidate_models(client)
    if override:
        return [override, *[m for m in base if m != override]]
    return base


def is_configured() -> bool:
    """Check if Gemini API is configured."""
    key = os.environ.get("GEMINI_API_KEY", "")
    return bool(key and key != "your_gemini_api_key_here")


def generate(prompt: str, system_instruction: str = "", search_grounding: bool = False) -> str:
    """Generate a response from Gemini.

    Uses the strongest available Gemini Pro model (auto-discovered), with
    fallback to stable known models.

    You can pin a model via GEMINI_MODEL in .env.

    When search_grounding=True, enables Google Search as a tool so
    Gemini can access real-time web information instead of relying on
    stale training data.
    """
    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or api_key == "your_gemini_api_key_here":
        return "[Gemini API key not configured. Set GEMINI_API_KEY in .env]"

    try:
        client = genai.Client(api_key=api_key)
        models = _candidate_models(client)

        config_kwargs = {}
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if search_grounding:
            config_kwargs["tools"] = [
                genai.types.Tool(google_search=genai.types.GoogleSearch()),
            ]

        config = genai.types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

        errors: list[str] = []
        for model_name in models:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config,
                )
                if response.text:
                    return response.text
                return "[No response from Gemini]"
            except Exception as model_error:
                errors.append(f"{model_name}: {model_error}")

        summary = "; ".join(errors[:3]) if errors else "unknown"
        return f"[Gemini API error: all candidate models failed ({summary})]"

    except Exception as e:
        return f"[Gemini API error: {e}]"
