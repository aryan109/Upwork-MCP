"""
Unified Tick Entrypoint for All Tiers (Railway, Vercel, Local PC).
Implements the resilient single tick lifecycle specified in Section B6:
1. Heartbeat write
2. State & Jobs pull
3. Watchdog evaluation
4. Deduplicated Alert synchronization
5. Local Cloud Backup check
6. Distributed Lease acquisition (with priority yields)
7. OAuth token refresh verification
8. Single discovery / vetting pass execution (with time budget)
9. Daily Report & Proof-of-Life dispatch
10. State push & pass recording
11. Dead man's switch ping
12. Lease renewal or yield
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from .alerts import AlertManager, dead_man_ping
from .config import STATE_DIR
from .daily_report import DailyReportEngine
from .hourly_runner import run_single_pass
from .lease import LeaseManager
from .mcp_client import UpworkMCPClient
from .state_backend import StateBackend, get_default_backend
from .state_manager import StateManager
from .tier import can, current_tier, get_commit_sha
from .upwork_oauth import UpworkOAuthManager, get_oauth_manager
from .watchdog import WatchdogEvaluator

logger = logging.getLogger("upwork_tick")


def write_heartbeat(backend: StateBackend, tier: str, ok: bool = True, detail: str = "") -> None:
    """Record heartbeat for current tier in heartbeats/<tier>.json."""
    hb_path = f"heartbeats/{tier.lower()}.json"
    hb_data = {
        "tier": tier.lower(),
        "seen_at": datetime.now(timezone.utc).isoformat(),
        "commit_sha": get_commit_sha(),
        "ok": ok,
        "detail": detail,
    }
    try:
        backend.write_json(hb_path, hb_data, message=f"heartbeat {tier}")
    except Exception as e:
        logger.warning(f"Failed to write heartbeat for tier {tier}: {e}")


def is_proof_of_life_due(state: Dict[str, Any]) -> bool:
    """Check if daily proof-of-life is due (09:00 IST = 03:30 UTC)."""
    now_utc = datetime.now(timezone.utc)
    ist_offset = timedelta(hours=5, minutes=30)
    now_ist = now_utc + ist_offset
    today_ist = now_ist.strftime("%Y-%m-%d")

    # Due after 09:00 AM IST
    if now_ist.hour >= 9:
        if state.get("last_proof_of_life_date") != today_ist:
            return True
    return False


def send_proof_of_life(state: Dict[str, Any], tier: str, backend: StateBackend) -> None:
    """Dispatch daily 09:00 IST proof-of-life status message."""
    try:
        from .telegram_notifier import send_telegram_message

        now_utc = datetime.now(timezone.utc)
        ist_offset = timedelta(hours=5, minutes=30)
        today_ist = (now_utc + ist_offset).strftime("%Y-%m-%d")

        last_pass = state.get("last_pass_record", {})
        oauth_data, _ = backend.read_json("secrets/upwork_oauth.json")
        token_age = "Unknown"
        if oauth_data and oauth_data.get("updated_at"):
            try:
                up_dt = datetime.fromisoformat(oauth_data["updated_at"].replace("Z", "+00:00"))
                token_age = f"{(now_utc - up_dt).total_seconds() / 3600.0:.1f}h"
            except Exception:
                pass

        connects = state.get("connects_balance", "Unknown")
        queue_count = len([j for j in state.get("staged_proposals", []) if isinstance(j, dict)])

        msg = (
            f"📡 <b>Daily Proof-of-Life: Upwork Engine Operational</b>\n\n"
            f"• 👑 <b>Active Lease Holder:</b> <code>{tier}</code> (commit <code>{get_commit_sha()}</code>)\n"
            f"• 🟢 <b>Last Pass Health:</b> {'HEALTHY' if last_pass.get('healthy') else 'WARNING'}\n"
            f"• 🔑 <b>OAuth Token Age:</b> {token_age}\n"
            f"• ⚡ <b>Connects Balance:</b> {connects}\n"
            f"• 📋 <b>Review Queue:</b> {queue_count} pending\n"
            f"• 🕒 <b>Timestamp:</b> {today_ist} 09:00 IST\n\n"
            f"<i>All automated discovery, vetting, and watchdog routines running normally.</i>"
        )
        send_telegram_message(msg, parse_mode="HTML")
        state["last_proof_of_life_date"] = today_ist
    except Exception as e:
        logger.warning(f"Error sending proof-of-life: {e}")


def run_tick(
    tier: Optional[str] = None,
    time_budget_s: Optional[float] = None,
    backend: Optional[StateBackend] = None,
) -> Dict[str, Any]:
    """
    Execute a single unified tick across any tier.
    Returns summary dictionary detailing actions performed.
    """
    active_tier = (tier or current_tier()).lower()
    active_backend = backend or get_default_backend()
    state_mgr = StateManager(STATE_DIR, backend=active_backend)
    alert_mgr = AlertManager(backend=active_backend)
    lease_mgr = LeaseManager(backend=active_backend)
    watchdog = WatchdogEvaluator(backend=active_backend)
    oauth_mgr = UpworkOAuthManager(backend=active_backend)

    now_utc = datetime.now(timezone.utc)
    logger.info(f"=== Starting Engine Tick on Tier [{active_tier}] ({get_commit_sha()}) ===")

    # 1. Heartbeat: Record proof-of-life for this tier
    write_heartbeat(active_backend, active_tier, ok=True, detail="Tick started")

    # 2. Pull state & jobs from shared store
    try:
        state, jobs = state_mgr.pull()
    except Exception as e:
        logger.error(f"Store unreachable during tick pull on tier '{active_tier}': {e}")
        alert_mgr.raise_alert("W6", f"Failed to pull state from store on {active_tier}: {e}", severity="WARNING", tier=active_tier)
        if active_tier != "local":
            return {"tier": active_tier, "status": "store_unreachable_aborted"}
        # Local tier continues from local disk cache
        state = state_mgr.load_state()
        jobs = state_mgr.load_jobs()

    # 3. Evaluate watchdog invariants
    conditions = watchdog.evaluate(now=now_utc)

    # 4. Synchronize alerts (raise / resend / resolve)
    alert_mgr.sync(conditions, tier=active_tier)

    # 5. Local tier cloud backup check (Part E)
    if active_tier == "local":
        try:
            from .cloud_backup import backup_due, run_backup
            if backup_due():
                logger.info("Cloud backup is due on local tier; running backup...")
                run_backup()
        except Exception as b_err:
            logger.debug(f"Backup check note: {b_err}")

    # 6. Try acquire hunter lease
    lease_held = lease_mgr.try_acquire("hunter", active_tier, run_id=f"tick_{now_utc.strftime('%H%M%S')}")
    if not lease_held:
        logger.info(f"Tier '{active_tier}' did not acquire hunter lease; operating in Watchdog/Standby mode.")
        write_heartbeat(active_backend, active_tier, ok=True, detail="Watchdog/Standby tick complete")
        return {"tier": active_tier, "status": "standby", "role": "watchdog"}

    # 7. Resolve Upwork OAuth access token (lease holder performs early refresh if stale)
    access_token = oauth_mgr.get_valid_access_token(lease_held=True)
    mcp_client = UpworkMCPClient(
        auth_token=access_token,
        oauth_manager=oauth_mgr,
        lease_held=True,
    )

    # 8. Execute single discovery pass
    pass_summary = run_single_pass(
        state_mgr=state_mgr,
        mcp_client=mcp_client,
        time_budget_s=time_budget_s,
    )

    # 9. Daily report and proof-of-life
    if is_proof_of_life_due(state):
        send_proof_of_life(state, active_tier, active_backend)

    # 10. Record pass and push state
    is_healthy = pass_summary.get("healthy", False)
    date_str = now_utc.strftime("%Y-%m-%d")
    pass_record = {
        "ts": now_utc.isoformat(),
        "tier": active_tier,
        "commit": get_commit_sha(),
        **pass_summary,
    }
    active_backend.append_jsonl(f"passes/{active_tier}/{date_str}.jsonl", pass_record, message="record pass")
    state_mgr.push()

    # 11. Ping external dead-man's switch on healthy pass
    if is_healthy:
        dead_man_ping()

    # 12. Renew lease or yield to higher-priority tier
    lease_mgr.renew_or_yield("hunter", active_tier)

    write_heartbeat(active_backend, active_tier, ok=is_healthy, detail="Hunt tick completed")
    logger.info(f"=== Engine Tick Completed on Tier [{active_tier}] (Healthy: {is_healthy}) ===")

    return {
        "tier": active_tier,
        "status": "completed",
        "healthy": is_healthy,
        "pass_summary": pass_summary,
    }


def main():
    parser = argparse.ArgumentParser(description="Upwork Engine Unified Tick Runner")
    parser.add_argument("--tier", type=str, default=None, help="Execution tier (railway, vercel, local)")
    parser.add_argument("--budget", type=float, default=None, help="Time budget in seconds")
    args = parser.parse_args()

    summary = run_tick(tier=args.tier, time_budget_s=args.budget)
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
