"""Telegram notification integration."""

from __future__ import annotations

import os
import asyncio
from dotenv import load_dotenv

load_dotenv()


def _get_config() -> tuple[str, str]:
    """Get Telegram bot token and chat ID from environment."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    return token, chat_id


def is_configured() -> bool:
    """Check if Telegram is properly configured."""
    token, chat_id = _get_config()
    return bool(token and chat_id and token != "your_telegram_bot_token_here")


async def _send_message_async(text: str) -> bool:
    """Send a message via Telegram Bot API."""
    from telegram import Bot

    token, chat_id = _get_config()
    if not token or not chat_id:
        return False

    try:
        bot = Bot(token=token)
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown",
        )
        return True
    except Exception as e:
        print(f"Telegram send failed: {e}")
        return False


def send_alert(message: str) -> bool:
    """Send a text alert via Telegram. Returns True if successful."""
    if not is_configured():
        return False
    return asyncio.run(_send_message_async(message))


def send_signal_change(from_color: str, to_color: str, summary: str) -> bool:
    """Send a signal color change alert."""
    color_emoji = {
        "green": "GREEN",
        "yellow": "YELLOW",
        "orange": "ORANGE",
        "red": "RED",
    }

    msg = (
        "*REWIRED INDEX ALERT*\n\n"
        f"Signal Change: {color_emoji.get(from_color, from_color)} -> {color_emoji.get(to_color, to_color)}\n\n"
        f"{summary}\n\n"
    )

    # Add action guidance based on new color
    actions = {
        "green": "ACTION: Full allocation per plan",
        "yellow": "ACTION: Reduce new positions, trim T4 by 50%",
        "orange": "ACTION: Defensive - exit T3/T4, hold T1/T2",
        "red": "ACTION: Retreat - only hold T1 core, exit T2-T4",
    }
    msg += actions.get(to_color, "")

    return send_alert(msg)


def send_portfolio_summary(summary_text: str) -> bool:
    """Send a portfolio summary."""
    msg = f"*REWIRED INDEX - Portfolio Summary*\n\n{summary_text}"
    return send_alert(msg)
