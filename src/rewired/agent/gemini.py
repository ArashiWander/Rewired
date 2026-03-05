"""Gemini API client wrapper."""

from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()


def is_configured() -> bool:
    """Check if Gemini API is configured."""
    key = os.environ.get("GEMINI_API_KEY", "")
    return bool(key and key != "your_gemini_api_key_here")


def generate(prompt: str, system_instruction: str = "") -> str:
    """Generate a response from Gemini.

    Uses gemini-2.5-flash for fast, cost-effective analysis.
    """
    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or api_key == "your_gemini_api_key_here":
        return "[Gemini API key not configured. Set GEMINI_API_KEY in .env]"

    try:
        client = genai.Client(api_key=api_key)

        config = None
        if system_instruction:
            config = genai.types.GenerateContentConfig(
                system_instruction=system_instruction,
            )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=config,
        )
        return response.text or "[No response from Gemini]"

    except Exception as e:
        return f"[Gemini API error: {e}]"
