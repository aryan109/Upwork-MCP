"""
Telegram Notification Engine for Aryan Upwork Acquisition Pipeline.
Dispatches formatted HTML/Markdown alerts directly to Telegram for:
1. Proposals staged for 1-click review
2. Daily 4-part intelligence and improvement reports
3. Client messages and interview invites
4. Low Connects balance alerts
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .config import PROJECT_ROOT, ENGINE_DIR

logger = logging.getLogger("telegram_notifier")

# Upwork & Notion Reference URLs
NOTION_DAILY_REPORT_URL = "https://app.notion.com/p/Daily-Intelligence-Action-Reports-3f197b4f861081a1ac3ed59e9c8bf7d7"
NOTION_MARKET_INTEL_URL = "https://app.notion.com/p/Market-Intelligence-Demand-Knowledge-Base-3f197b4f861081a7b919f430b7816837"
NOTION_HUB_URL = "https://app.notion.com/p/Upwork-Acquisition-Market-Intelligence-OS-3f197b4f8610816e8ab0cf54ac7b3a3e"


def load_env_file(env_path: Path) -> Dict[str, str]:
    """Parse a .env file safely without external dependencies."""
    env_vars: Dict[str, str] = {}
    if not env_path.exists():
        return env_vars
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    env_vars[key] = val
    except Exception as e:
        logger.debug(f"Error loading .env from {env_path}: {e}")
    return env_vars


def get_telegram_credentials() -> Tuple[Optional[str], Optional[str]]:
    """
    Resolve Telegram Bot Token and Chat ID from:
    1. Environment variables (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    2. PROJECT_ROOT/.env
    3. ENGINE_DIR/config.json
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    # Check project .env
    if not token or not chat_id:
        env_vars = load_env_file(PROJECT_ROOT / ".env")
        token = token or env_vars.get("TELEGRAM_BOT_TOKEN")
        chat_id = chat_id or env_vars.get("TELEGRAM_CHAT_ID")

    # Check engine dir config
    if not token or not chat_id:
        cfg_file = ENGINE_DIR / "config.json"
        if cfg_file.exists():
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    token = token or cfg.get("TELEGRAM_BOT_TOKEN")
                    chat_id = chat_id or cfg.get("TELEGRAM_CHAT_ID")
            except Exception:
                pass

    # If token exists but chat_id is missing, try automatic discovery from getUpdates
    if token and not chat_id:
        chat_info = auto_discover_chat_id(token=token, save=True)
        if chat_info and "id" in chat_info:
            chat_id = str(chat_info["id"])

    return token, chat_id


def get_bot_info(token: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve bot metadata from Telegram getMe endpoint."""
    bot_token = token or get_telegram_credentials()[0]
    if not bot_token:
        return None
    url = f"https://api.telegram.org/bot{bot_token}/getMe"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                return data.get("result")
    except Exception as e:
        logger.debug(f"Error fetching bot info: {e}")
    return None


def auto_discover_chat_id(
    token: Optional[str] = None,
    save: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Auto-detect user chat ID by reading recent messages sent to the bot via getUpdates.
    If save=True, automatically persists TELEGRAM_CHAT_ID into .env and config.json.
    """
    bot_token = token
    if not bot_token:
        env_vars = load_env_file(PROJECT_ROOT / ".env")
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN") or env_vars.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return None

    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if not data.get("ok"):
                return None
            results = data.get("result", [])
            for update in reversed(results):
                msg = (
                    update.get("message")
                    or update.get("channel_post")
                    or update.get("my_chat_member", {})
                    or update.get("callback_query", {}).get("message", {})
                )
                chat = msg.get("chat", {})
                chat_id = chat.get("id")
                if chat_id:
                    if save:
                        save_telegram_credentials(bot_token, str(chat_id))
                        logger.info(f"Auto-discovered and linked Telegram Chat ID: {chat_id}")
                    return chat
    except Exception as e:
        logger.debug(f"Error in auto_discover_chat_id: {e}")
    return None


def save_telegram_credentials(token: str, chat_id: str) -> None:
    """Save Telegram credentials to PROJECT_ROOT/.env and ENGINE_DIR/config.json."""
    token = token.strip()
    chat_id = chat_id.strip()

    # Update .env
    env_path = PROJECT_ROOT / ".env"
    existing_lines = []
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            existing_lines = f.readlines()

    new_lines = []
    has_token = False
    has_chat_id = False

    for line in existing_lines:
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            new_lines.append(f"TELEGRAM_BOT_TOKEN={token}\n")
            has_token = True
        elif line.startswith("TELEGRAM_CHAT_ID="):
            new_lines.append(f"TELEGRAM_CHAT_ID={chat_id}\n")
            has_chat_id = True
        else:
            new_lines.append(line)

    if not has_token:
        new_lines.append(f"TELEGRAM_BOT_TOKEN={token}\n")
    if not has_chat_id:
        new_lines.append(f"TELEGRAM_CHAT_ID={chat_id}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    # Update ENGINE_DIR/config.json
    ENGINE_DIR.mkdir(parents=True, exist_ok=True)
    cfg_file = ENGINE_DIR / "config.json"
    cfg = {}
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    cfg["TELEGRAM_BOT_TOKEN"] = token
    cfg["TELEGRAM_CHAT_ID"] = chat_id
    with open(cfg_file, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

    logger.info("Saved Telegram credentials to .env and config.json")


def send_telegram_message(
    text: str,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = False,
) -> bool:
    """
    Send a message to Telegram using standard Telegram Bot API.
    Splits long messages automatically to comply with Telegram's 4096 character limit.
    """
    token, chat_id = get_telegram_credentials()
    if not token or not chat_id:
        logger.warning(
            "Telegram notification skipped: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID "
            "are not configured. Set them in .env or run 'python -m aryan_implementation.engine.cli setup-telegram <TOKEN> <CHAT_ID>'."
        )
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    # Telegram message length limit is 4096 characters
    max_len = 3900
    chunks = [text[i:i + max_len] for i in range(0, len(text), max_len)]

    success = True
    for chunk in chunks:
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                if resp.status != 200:
                    logger.warning(f"Telegram API responded with HTTP {resp.status}")
                    success = False
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            logger.warning(f"Telegram API HTTP error {e.code}: {err_body}")
            # If HTML parsing fails due to unescaped chars, fallback to plain text
            if parse_mode == "HTML" and "can't parse entities" in err_body:
                logger.info("Retrying Telegram send without HTML parse_mode...")
                plain_payload = {
                    "chat_id": chat_id,
                    "text": chunk,
                    "disable_web_page_preview": disable_web_page_preview,
                }
                try:
                    retry_req = urllib.request.Request(
                        url,
                        data=json.dumps(plain_payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(retry_req, timeout=12) as retry_resp:
                        if retry_resp.status == 200:
                            continue
                except Exception as retry_err:
                    logger.error(f"Telegram plain retry error: {retry_err}")
            success = False
        except Exception as e:
            logger.error(f"Telegram dispatch error: {e}")
            success = False

    return success


def send_proposal_alert(
    job_title: str,
    score: float,
    job_id: str,
    budget_info: str = "TBD",
    reasons: Optional[list] = None,
) -> bool:
    """Dispatches Telegram alert when a proposal is drafted and ready for human confirmation."""
    clean_title = (job_title or "Untitled").replace("<", "&lt;").replace(">", "&gt;")
    reasons_str = ", ".join(reasons[:4]) if reasons else "high_match"
    job_url = f"https://www.upwork.com/jobs/~{job_id}" if not job_id.startswith("http") else job_id

    text = (
        f"🎯 <b>Action Required: Upwork Proposal Staged for Review</b>\n\n"
        f"<b>Title:</b> <a href=\"{job_url}\">{clean_title}</a>\n"
        f"<b>Score:</b> <code>{score:.1f} / 100</code>\n"
        f"<b>Budget / Pricing:</b> {budget_info}\n"
        f"<b>Signals:</b> <i>{reasons_str}</i>\n\n"
        f"👉 <b>To Review & Submit:</b>\n"
        f"<code>python -m aryan_implementation.engine.cli queue</code>\n"
        f"<i>Review cover letter, verify answers, and click confirm.</i>"
    )
    return send_telegram_message(text, parse_mode="HTML")


def send_client_alert(sender: str, summary: str) -> bool:
    """Dispatches high-priority Telegram alert for client messages / invites."""
    clean_sender = (sender or "Client").replace("<", "&lt;").replace(">", "&gt;")
    clean_summary = (summary or "").replace("<", "&lt;").replace(">", "&gt;")

    text = (
        f"🚨 <b>CRITICAL: New Upwork Message / Invitation!</b>\n\n"
        f"<b>From:</b> <b>{clean_sender}</b>\n"
        f"<b>Message Preview:</b>\n<i>{clean_summary}</i>\n\n"
        f"⚡ <i>Log in to Upwork to respond promptly:</i>\n"
        f"https://www.upwork.com/ab/messages/"
    )
    return send_telegram_message(text, parse_mode="HTML")


def send_connects_alert(balance: int) -> bool:
    """Dispatches Telegram warning when Connects balance drops below threshold."""
    text = (
        f"⚠️ <b>WARNING: Low Connects Balance</b>\n\n"
        f"Your current balance is <b>{balance} Connects</b>.\n"
        f"The pipeline may skip proposals if balance reaches minimum threshold.\n\n"
        f"👉 <i>Top up your Connects on Upwork:</i>\n"
        f"https://www.upwork.com/nx/plans/membership/index"
    )
    return send_telegram_message(text, parse_mode="HTML")


def send_daily_report_alert(
    report_text: str,
    target_date: str,
    staged_count: int,
) -> bool:
    """
    Dispatches a formatted summary of the daily 4-part report to Telegram,
    including direct links to the Notion live document.
    """
    hook_match = re.search(r"\*\*Headline / Hook\*\*:\s*\*\*([^\*]+)\*\*", report_text)
    hook = hook_match.group(1).strip() if hook_match else "Focus on hardening AI prototypes into production RAG & Evals."

    rate_match = re.search(r"Average Top Hourly Rate\*\*:\s*\*\*([^\*]+)\*\*", report_text)
    top_rate = rate_match.group(1).strip() if rate_match else "$80/hr"

    connects_match = re.search(r"Connects Status\*\*:\s*\*\*([^\*]+)\*\*", report_text)
    connects = connects_match.group(1).strip() if connects_match else "110"

    text = (
        f"📊 <b>Daily Upwork Intelligence & Action Report ({target_date})</b>\n\n"
        f"<b>1. Activity & Pipeline:</b>\n"
        f"• Connects Available: <b>{connects}</b>\n"
        f"• New Proposals Staged for Review: <b>{staged_count}</b>\n\n"
        f"<b>2. Market Demand & Velocity:</b>\n"
        f"• High Velocity Stacks: <code>Cursor, Lovable, Supabase, RAG, Evals</code>\n"
        f"• Top Hourly Ceiling: <b>{top_rate}</b>\n\n"
        f"<b>3. Today's Content / Social Hook:</b>\n"
        f"💡 <i>\"{hook}\"</i>\n\n"
        f"<b>4. Live Knowledge Base & Hub Links:</b>\n"
        f"📖 <a href=\"{NOTION_DAILY_REPORT_URL}\">View Full Report on Notion</a>\n"
        f"🧠 <a href=\"{NOTION_MARKET_INTEL_URL}\">Market Intelligence Knowledge Base</a>\n"
        f"💼 <a href=\"{NOTION_HUB_URL}\">Upwork OS Command Center</a>"
    )
    return send_telegram_message(text, parse_mode="HTML")
