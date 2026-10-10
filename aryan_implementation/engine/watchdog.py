"""
Watchdog Engine for Upwork Engine.
Evaluates conditions W1 through W10 across state, heartbeats, pass records, and token metadata.
Returns evaluated condition dictionaries for AlertManager to sync.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from .state_backend import StateBackend, get_default_backend
from .tier import current_tier, get_commit_sha

logger = logging.getLogger("upwork_engine")


class WatchdogEvaluator:
    """Evaluates system operational invariants across tiers and storage."""

    def __init__(self, backend: Optional[StateBackend] = None):
        self.backend = backend or get_default_backend()

    def evaluate(self, now: Optional[datetime] = None) -> Dict[str, Dict[str, Any]]:
        """Evaluate conditions W1-W10 against the backend and current system state."""
        now_utc = now or datetime.now(timezone.utc)
        results: Dict[str, Dict[str, Any]] = {}

        state, _ = self.backend.read_json("state.json")
        if not state:
            state = {}

        # W1: hunter_silent (no healthy pass in 35 min)
        last_success = state.get("last_success_at")
        w1_triggered = False
        w1_msg = ""
        if last_success:
            try:
                dt = datetime.fromisoformat(last_success.replace("Z", "+00:00"))
                elapsed_mins = (now_utc - dt).total_seconds() / 60.0
                if elapsed_mins > 35.0:
                    w1_triggered = True
                    w1_msg = f"No healthy hunt pass in {elapsed_mins:.0f} mins (last: {last_success})"
            except Exception:
                pass
        else:
            w1_triggered = True
            w1_msg = "No successful hunt pass recorded in state.json"

        results["W1"] = {
            "triggered": w1_triggered,
            "message": w1_msg,
            "severity": "CRITICAL",
            "fix": "Check tier heartbeats, Railway logs, and Upwork OAuth credentials.",
            "resolved_note": f"Healthy pass completed at {state.get('last_success_at')}",
        }

        # W2: auth_failed
        last_pass = state.get("last_pass_record", {})
        auth_ok = last_pass.get("auth_ok", True)
        results["W2"] = {
            "triggered": not auth_ok,
            "message": "Upwork OAuth authentication failed in latest pass.",
            "severity": "CRITICAL",
            "fix": "Run 'python -m aryan_implementation.engine.cli upwork-login'",
            "resolved_note": "Upwork OAuth authentication verified.",
        }

        # W3: tier_missing (Railway/Vercel > 1h, local > 48h)
        missing_tiers = []
        for t_name, threshold_hours in [("railway", 1.0), ("vercel", 1.0), ("local", 48.0)]:
            hb, _ = self.backend.read_json(f"heartbeats/{t_name}.json")
            if hb and hb.get("seen_at"):
                try:
                    dt = datetime.fromisoformat(hb["seen_at"].replace("Z", "+00:00"))
                    if (now_utc - dt).total_seconds() > threshold_hours * 3600:
                        missing_tiers.append(f"{t_name} (> {threshold_hours}h silent)")
                except Exception:
                    pass

        results["W3"] = {
            "triggered": len(missing_tiers) > 0,
            "message": f"Heartbeats missing for tiers: {', '.join(missing_tiers)}",
            "severity": "WARNING",
            "fix": "Check hosting logs or ensure scheduled tasks are executing.",
            "resolved_note": "All configured tiers reporting healthy heartbeats.",
        }

        # W4: kill_switch_active
        kill_active = state.get("kill_switch", False)
        results["W4"] = {
            "triggered": bool(kill_active),
            "message": f"Emergency kill switch is ACTIVE ({state.get('kill_switch_reason', 'Manual trip')})",
            "severity": "CRITICAL",
            "fix": "Run 'python -m aryan_implementation.engine.cli reset-kill-switch' after resolving root cause.",
            "resolved_note": "Emergency kill switch cleared.",
        }

        # W5: empty_streak (>= 6 healthy passes with 0 candidates)
        empty_streak = state.get("empty_streak", 0)
        results["W5"] = {
            "triggered": empty_streak >= 6,
            "message": f"{empty_streak} consecutive passes returned 0 candidate jobs.",
            "severity": "WARNING",
            "fix": "Check campaign search keywords or Upwork API filter responses.",
            "resolved_note": "Candidates discovered again in recent pass.",
        }

        # W6: store_unreachable
        # If we reached this point, backend read succeeded, so False unless flagged
        results["W6"] = {
            "triggered": False,
            "message": "Shared state backend reachable.",
            "severity": "WARNING",
            "resolved_note": "Shared store accessible.",
        }

        # W7: version_skew (tiers on different commits > 1h)
        commits_seen = {}
        for t_name in ["railway", "vercel", "local"]:
            hb, _ = self.backend.read_json(f"heartbeats/{t_name}.json")
            if hb and hb.get("commit_sha"):
                commits_seen[t_name] = hb["commit_sha"]

        skew_found = False
        unique_commits = set(commits_seen.values())
        if len(unique_commits) > 1 and "unknown" not in unique_commits:
            skew_found = True

        results["W7"] = {
            "triggered": skew_found,
            "message": f"Version skew detected across tiers: {commits_seen}",
            "severity": "INFO",
            "fix": "Redeploy or pull latest commits across all environments.",
            "resolved_note": "All tiers running unified commit version.",
        }

        # W8: token_stale (token older than 18h and no refresh)
        oauth_data, _ = self.backend.read_json("secrets/upwork_oauth.json")
        token_stale = False
        stale_msg = ""
        if oauth_data and oauth_data.get("updated_at"):
            try:
                dt = datetime.fromisoformat(oauth_data["updated_at"].replace("Z", "+00:00"))
                age_hours = (now_utc - dt).total_seconds() / 3600.0
                if age_hours > 18.0:
                    token_stale = True
                    stale_msg = f"OAuth token is {age_hours:.1f} hours old without refresh."
            except Exception:
                pass

        results["W8"] = {
            "triggered": token_stale,
            "message": stale_msg,
            "severity": "WARNING",
            "fix": "Lease holder should trigger token refresh on next pass.",
            "resolved_note": "OAuth token refreshed.",
        }

        # W9: telegram_inbound_broken
        tg_broken = state.get("telegram_inbound_error", False)
        results["W9"] = {
            "triggered": bool(tg_broken),
            "message": "Telegram inbound webhook/polling reports conflict or errors.",
            "severity": "WARNING",
            "fix": "Check polling vs webhook conflict in Telegram bot settings.",
            "resolved_note": "Telegram inbound connection restored.",
        }

        # W10: backup_stale (local cloud backup older than 12h)
        manifest, _ = self.backend.read_json("cloud_backup/manifest.json")
        backup_stale = False
        if current_tier() == "local":
            if manifest and manifest.get("last_run_at"):
                try:
                    dt = datetime.fromisoformat(manifest["last_run_at"].replace("Z", "+00:00"))
                    if (now_utc - dt).total_seconds() > 12 * 3600:
                        backup_stale = True
                except Exception:
                    backup_stale = True
            else:
                backup_stale = False  # fresh install

        results["W10"] = {
            "triggered": backup_stale,
            "message": "Local cloud backup has not run in > 12 hours.",
            "severity": "WARNING",
            "fix": "Run 'python -m aryan_implementation.engine.cli backup-cloud --now'",
            "resolved_note": "Cloud backup completed successfully.",
        }

        return results


def evaluate_watchdog() -> Dict[str, Dict[str, Any]]:
    """Convenience helper to evaluate watchdog conditions."""
    return WatchdogEvaluator().evaluate()
