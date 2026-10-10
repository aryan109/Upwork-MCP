"""
Alert Management Engine & Dead Man's Switch for Upwork Engine.
Handles deduplicated notifications across Telegram, local Windows toasts,
cooldown periods, resolution messages, and healthchecks.io heartbeats.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import ENGINE_DIR
from .telegram_notifier import send_telegram_message

logger = logging.getLogger("upwork_engine")

ALERTS_FILE = ENGINE_DIR / "alerts.json"

ALERT_CONFIG = {
    "W1": {"name": "hunter_silent", "severity": "CRITICAL", "resend_hours": 2.0},
    "W2": {"name": "auth_failed", "severity": "CRITICAL", "resend_hours": 1.0},
    "W3": {"name": "tier_missing", "severity": "WARNING", "resend_hours": 12.0},
    "W4": {"name": "kill_switch_active", "severity": "CRITICAL", "resend_hours": 6.0},
    "W5": {"name": "empty_streak", "severity": "WARNING", "resend_hours": 6.0},
    "W6": {"name": "store_unreachable", "severity": "WARNING", "resend_hours": 2.0},
    "W7": {"name": "version_skew", "severity": "INFO", "resend_hours": 24.0},
    "W8": {"name": "token_stale", "severity": "WARNING", "resend_hours": 1.0},
    "W9": {"name": "telegram_inbound_broken", "severity": "WARNING", "resend_hours": 1.0},
    "W10": {"name": "backup_stale", "severity": "WARNING", "resend_hours": 6.0},
}


def send_windows_toast(title: str, message: str) -> None:
    """Trigger a Windows desktop toast notification if running on Windows."""
    if os.name != "nt" or os.environ.get("UPWORK_TEST_MODE"):
        return
    try:
        clean_title = title.replace('"', '`"').replace("'", "`'")
        clean_msg = message.replace('"', '`"').replace("'", "`'")[:200]
        ps_cmd = (
            f"[void] [System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms');"
            f"$notify = New-Object System.Windows.Forms.NotifyIcon;"
            f"$notify.Icon = [System.Drawing.SystemIcons]::Information;"
            f"$notify.Visible = $True;"
            f"$notify.ShowBalloonTip(5000, '{clean_title}', '{clean_msg}', [System.Windows.Forms.ToolTipIcon]::Warning)"
        )
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        logger.debug(f"Windows toast skipped: {e}")


class AlertManager:
    """Manages active alerts, deduplication windows, resolutions, and notification channels."""

    def __init__(self, backend: Optional[Any] = None, alerts_file: Optional[Path] = None):
        self.backend = backend
        self.alerts_file = alerts_file or ALERTS_FILE

    def load_alerts_state(self) -> Dict[str, Any]:
        """Load alerts state from backend or local storage."""
        if self.backend:
            try:
                data, _ = self.backend.read_json("alerts.json")
                if data:
                    return data
            except Exception as e:
                logger.debug(f"Failed to read alerts.json from backend: {e}")

        if self.alerts_file.exists():
            try:
                with open(self.alerts_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading {self.alerts_file}: {e}")

        return {"active": {}, "history": []}

    def save_alerts_state(self, state: Dict[str, Any]) -> None:
        """Persist alerts state to backend and local storage."""
        if self.backend:
            try:
                self.backend.write_json("alerts.json", state)
            except Exception as e:
                logger.warning(f"Failed to write alerts.json to backend: {e}")

        try:
            self.alerts_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.alerts_file.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            tmp.replace(self.alerts_file)
        except Exception as e:
            logger.warning(f"Error writing {self.alerts_file}: {e}")

    def raise_alert(
        self,
        key: str,
        message: str,
        severity: Optional[str] = None,
        fix: Optional[str] = None,
        tier: str = "unknown",
    ) -> bool:
        """
        Raise or resend an alert if outside the cooldown window.
        Returns True if a notification was dispatched.
        """
        try:
            state = self.load_alerts_state()
            active = state.setdefault("active", {})
            now_utc = datetime.now(timezone.utc)
            now_iso = now_utc.isoformat()

            cfg = ALERT_CONFIG.get(key, {"resend_hours": 2.0, "severity": "WARNING"})
            resend_seconds = cfg.get("resend_hours", 2.0) * 3600
            sev = severity or cfg.get("severity", "WARNING")

            should_send = False
            if key not in active:
                should_send = True
                active[key] = {
                    "key": key,
                    "severity": sev,
                    "message": message,
                    "fix": fix,
                    "tier": tier,
                    "raised_at": now_iso,
                    "last_sent_at": now_iso,
                    "send_count": 1,
                }
            else:
                existing = active[key]
                last_sent = datetime.fromisoformat(existing["last_sent_at"].replace("Z", "+00:00"))
                if (now_utc - last_sent).total_seconds() >= resend_seconds:
                    should_send = True
                    existing["last_sent_at"] = now_iso
                    existing["send_count"] = existing.get("send_count", 1) + 1
                    existing["message"] = message

            if should_send:
                self._dispatch_alert(key, sev, message, fix, tier)
                self.save_alerts_state(state)
                return True

            return False
        except Exception as e:
            logger.error(f"Error in raise_alert ({key}): {e}")
            return False

    def resolve_alert(self, key: str, resolution_note: str = "Condition cleared") -> bool:
        """
        Resolve an active alert and send a resolution notification.
        """
        try:
            state = self.load_alerts_state()
            active = state.get("active", {})
            if key in active:
                item = active.pop(key)
                item["resolved_at"] = datetime.now(timezone.utc).isoformat()
                item["resolution_note"] = resolution_note
                history = state.setdefault("history", [])
                history.append(item)
                if len(history) > 100:
                    state["history"] = history[-100:]

                self._dispatch_resolution(key, item, resolution_note)
                self.save_alerts_state(state)
                return True
            return False
        except Exception as e:
            logger.error(f"Error in resolve_alert ({key}): {e}")
            return False

    def sync(self, conditions: Dict[str, Dict[str, Any]], tier: str = "unknown") -> None:
        """
        Sync evaluated conditions:
        - If condition triggered, raise_alert.
        - If condition not triggered and alert active, resolve_alert.
        """
        try:
            state = self.load_alerts_state()
            active_keys = set(state.get("active", {}).keys())

            for key, cond in conditions.items():
                if cond.get("triggered"):
                    self.raise_alert(
                        key,
                        cond.get("message", f"Alert {key} triggered"),
                        severity=cond.get("severity"),
                        fix=cond.get("fix"),
                        tier=tier,
                    )
                elif key in active_keys:
                    self.resolve_alert(key, resolution_note=cond.get("resolved_note", "Condition cleared"))
        except Exception as e:
            logger.error(f"Error syncing alerts: {e}")

    def _dispatch_alert(
        self,
        key: str,
        severity: str,
        message: str,
        fix: Optional[str] = None,
        tier: str = "unknown",
    ) -> None:
        """Dispatch alert across Telegram and Windows toast."""
        icon = "🚨" if severity == "CRITICAL" else "⚠️"
        lines = [
            f"{icon} <b>UPWORK ENGINE ALERT: [{severity}] {key}</b>",
            f"<b>Tier:</b> <code>{tier}</code>",
            f"<b>Message:</b> {message}",
        ]
        if fix:
            lines.append(f"<b>Suggested Fix:</b> <code>{fix}</code>")

        tg_text = "\n".join(lines)
        send_telegram_message(tg_text, parse_mode="HTML")

        if tier == "local" or os.environ.get("ENGINE_TIER") == "local":
            send_windows_toast(f"Upwork Alert: {key}", message)

    def _dispatch_resolution(self, key: str, item: Dict[str, Any], note: str) -> None:
        """Dispatch resolution notice."""
        lines = [
            f"✅ <b>RESOLVED: [{item.get('severity', 'INFO')}] {key}</b>",
            f"<b>Original Issue:</b> {item.get('message', '')}",
            f"<b>Resolution:</b> {note}",
        ]
        send_telegram_message("\n".join(lines), parse_mode="HTML")


def dead_man_ping(ping_url: Optional[str] = None) -> bool:
    """
    Send proof-of-work HTTP GET to external dead-man's switch (healthchecks.io).
    Never raises an exception.
    """
    url = ping_url or os.environ.get("HEALTHCHECK_PING_URL")
    if not url or os.environ.get("UPWORK_TEST_MODE"):
        return False

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "UpworkEngine-DeadMan/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status in (200, 204)
    except Exception as e:
        logger.debug(f"Dead man switch ping note: {e}")
        return False
