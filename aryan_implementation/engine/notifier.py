"""
Desktop and Alert Notification Engine for Aryan Upwork Acquisition Pipeline.
Dispatches native Windows Toast and Balloon notifications to alert Aryan immediately
whenever human action is required (e.g. proposal approval, client messages, low connects).
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from .config import ENGINE_DIR

logger = logging.getLogger("upwork_notifier")
SCRIPT_DIR = Path(__file__).resolve().parent
NOTIFY_PS1 = SCRIPT_DIR / "notify.ps1"


def notify(
    title: str,
    message: str,
    category: str = "Action Required",
    priority: str = "high",
) -> bool:
    """
    Trigger a native Windows desktop notification with audio prompt.
    Returns True if notification process succeeded.
    """
    logger.info(f"NOTIFICATION [{category}]: {title} - {message}")

    # Fallback to stdout alert if not on Windows
    if sys.platform != "win32":
        print(f"\n🔔 [ACTION REQUIRED] {title}: {message}\n")
        return True

    try:
        if NOTIFY_PS1.exists():
            cmd = [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(NOTIFY_PS1),
                "-Title",
                title,
                "-Message",
                message,
                "-Category",
                category,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                return True
            else:
                logger.warning(f"notify.ps1 returned code {res.returncode}: {res.stderr}")
    except Exception as e:
        logger.warning(f"Failed to execute desktop notification: {e}")

    # Fallback beep
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception:
        sys.stdout.write("\a")
        sys.stdout.flush()

    return False


def notify_proposal_ready(job_title: str, score: float, job_id: str) -> bool:
    """Explicit alert when a proposal draft is staged and requires Aryan's 1-click review."""
    title = f"Action Required: Proposal Staged ({score:.1f} pts)"
    message = f"High-fit lead '{job_title[:60]}' drafted and waiting in review queue."
    return notify(title, message, category="Proposal Review", priority="high")


def notify_client_message_or_invite(sender: str, summary: str) -> bool:
    """Explicit alert for client messages, interviews, or invites."""
    title = f"Action Required: New Client Message / Invite"
    message = f"{sender}: {summary[:80]}"
    return notify(title, message, category="Client Action", priority="critical")


def notify_low_connects(balance: int) -> bool:
    """Explicit alert when Connects balance is low."""
    title = "Action Required: Low Connects Balance"
    message = f"Your Upwork Connects balance is {balance}. Top up needed to continue applying."
    return notify(title, message, category="Connects Alert", priority="high")


def notify_daily_report_ready(report_date: str, staged_count: int) -> bool:
    """Alert when the daily intelligence report has been compiled."""
    title = f"Daily Upwork Report Ready ({report_date})"
    message = f"Market trends, {staged_count} staged leads, content hooks, and improvement insights ready."
    return notify(title, message, category="Daily Report", priority="normal")
