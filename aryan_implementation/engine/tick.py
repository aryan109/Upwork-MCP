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
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from .alerts import AlertManager, dead_man_ping
from .config import PROJECT_ROOT, STATE_DIR
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


def _read_env_fallback(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if val:
        return val
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() == key:
                            return v.strip().strip("'\"")
        except Exception:
            pass
    return ""


def ping_vercel_standby(from_tier: str) -> bool:
    """
    Wake the Vercel standby tick. Railway and local call this after their own tick
    so Vercel still writes a heartbeat while Railway holds the hunter lease.
    Independent 15-minute GitHub Actions also hit the same URL.
    """
    if from_tier.lower() == "vercel":
        return False
    if os.environ.get("UPWORK_TEST_MODE") or os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    url = _read_env_fallback("VERCEL_TICK_URL")
    secret = _read_env_fallback("TICK_SECRET")
    if not url:
        logger.debug("VERCEL_TICK_URL unset; skipping Vercel standby ping")
        return False
    try:
        headers = {
            "User-Agent": "UpworkEngine-StandbyPing/1.0",
            "Accept": "application/json",
        }
        if secret:
            headers["X-Tick-Secret"] = secret
        req = urllib.request.Request(url, data=b"", headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=20) as r:
            logger.info("Vercel standby ping from %s -> HTTP %s", from_tier, r.status)
            return r.status in (200, 204)
    except Exception as e:
        logger.warning("Vercel standby ping from %s failed: %s", from_tier, e)
        return False


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


IST_OFFSET = timedelta(hours=5, minutes=30)
PROOF_OF_LIFE_MAX_CHARS = 3900


def _now_ist(now_utc: Optional[datetime] = None) -> datetime:
    return (now_utc or datetime.now(timezone.utc)) + IST_OFFSET


def _ist_calendar_date(value: Any) -> Optional[str]:
    """Normalize a timestamp or YYYY-MM-DD string to an IST calendar date."""
    if not value or not isinstance(value, str):
        return None
    raw = value.strip()
    try:
        if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
            return raw
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (dt + IST_OFFSET).strftime("%Y-%m-%d")
    except Exception:
        return raw[:10] if len(raw) >= 10 else None


def _job_activity_dt(job: Dict[str, Any]) -> Optional[datetime]:
    for key in ("vetted_at", "rejected_at", "staged_at", "scraped_at", "first_seen_at"):
        value = job.get(key)
        if not value or not isinstance(value, str):
            continue
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue
    return None


def _classify_job_outcome(job: Dict[str, Any]) -> str:
    status = job.get("status") or ""
    decision = (job.get("decision") or "").upper()
    disqs = job.get("disqualifiers") or []
    if status in ("drafted", "preview_ready", "submitted") or decision == "APPLY":
        return "APPLY"
    if decision == "REVIEW" or status in ("scored", "in_review"):
        score = float(job.get("score") or 0.0)
        if score and score < 70.0:
            return "SCORE_LOW"
        return "REVIEW"
    if disqs:
        return str(disqs[0])
    if status == "ai_rejected":
        return "AI_REJECTED"
    score = float(job.get("score") or 0.0)
    if score and score < 70.0:
        return "SCORE_LOW"
    return "SKIP"


def summarize_jobs_for_proof(
    jobs: Dict[str, Any],
    target_ist: str,
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Count jobs processed on the IST calendar day. If that window is empty,
    fall back to the last 24 hours so the proof-of-life still has learnings.
    """
    from .web_report import DISQUALIFIER_EXPLANATIONS

    now = now_utc or datetime.now(timezone.utc)
    window: List[Dict[str, Any]] = []
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        dates = [
            job.get("event_date"),
            job.get("vetted_date"),
            job.get("rejected_date"),
            job.get("staged_date"),
            _ist_calendar_date(job.get("vetted_at")),
            _ist_calendar_date(job.get("rejected_at")),
            _ist_calendar_date(job.get("staged_at")),
            _ist_calendar_date(job.get("scraped_at")),
            _ist_calendar_date(job.get("first_seen_at")),
        ]
        if target_ist in {d for d in dates if d}:
            window.append(job)

    window_label = f"IST {target_ist}"
    if not window:
        cutoff = now - timedelta(hours=24)
        for job in jobs.values():
            if not isinstance(job, dict):
                continue
            dt = _job_activity_dt(job)
            if dt and dt >= cutoff:
                window.append(job)
        window_label = "last 24 hours"

    breakdown: Dict[str, int] = {}
    apply_n = review_n = 0
    examples: Dict[str, List[str]] = {}
    for job in window:
        code = _classify_job_outcome(job)
        if code == "APPLY":
            apply_n += 1
        elif code == "REVIEW":
            review_n += 1
        breakdown[code] = breakdown.get(code, 0) + 1
        title = (job.get("title") or "Untitled")[:72]
        examples.setdefault(code, [])
        if len(examples[code]) < 2:
            examples[code].append(title)

    analysed = len(window)
    d6 = breakdown.get("D6", 0)
    score_low = breakdown.get("SCORE_LOW", 0)
    ai_n = breakdown.get("AI_REJECTED", 0)
    learnings: List[str] = []
    if analysed == 0:
        learnings.append(
            "No newly timestamped jobs in this window. If searches are healthy, candidates are repeats already in the ledger."
        )
    else:
        learnings.append(
            f"Processed {analysed} jobs ({apply_n} APPLY, {review_n} REVIEW, {analysed - apply_n - review_n} filtered)."
        )
        if d6:
            share = int(round(100.0 * d6 / analysed)) if analysed else 0
            learnings.append(
                f"D6 ghost clients are {share}% of the funnel ({d6}/{analysed}): unverified payment + $0 spend + 0 hires. "
                "This is why nothing is apply-ready — not because queries are empty."
            )
        if score_low:
            learnings.append(
                f"{score_low} jobs cleared hard filters but scored under 70 (REVIEW floor). Close misses, not missing search coverage."
            )
        if ai_n:
            learnings.append(f"AI vetting skipped {ai_n} jobs (scope/toxicity/fit risk).")
        top_other = [
            (code, n)
            for code, n in sorted(breakdown.items(), key=lambda kv: kv[1], reverse=True)
            if code not in ("APPLY", "REVIEW", "D6", "SCORE_LOW", "AI_REJECTED")
        ]
        if top_other:
            code, n = top_other[0]
            expl = DISQUALIFIER_EXPLANATIONS.get(code, code)
            learnings.append(f"{code} ({n}): {expl}")
        if apply_n == 0 and review_n == 0 and analysed > 0:
            learnings.append(
                "Campaign keywords are matching live posts. Loosening D6 would increase apply volume but spend Connects on unproven clients."
            )

    return {
        "window_label": window_label,
        "analysed": analysed,
        "apply": apply_n,
        "review": review_n,
        "filtered": max(0, analysed - apply_n - review_n),
        "breakdown": breakdown,
        "examples": examples,
        "learnings": learnings,
    }


def build_proof_of_life_message(
    state: Dict[str, Any],
    tier: str,
    jobs: Optional[Dict[str, Any]] = None,
    token_age: str = "Unknown",
    today_ist: Optional[str] = None,
    now_utc: Optional[datetime] = None,
) -> str:
    """Compose the daily proof-of-life Telegram HTML body (health + funnel + learnings)."""
    import html as html_mod
    from .web_report import DISQUALIFIER_EXPLANATIONS

    now = now_utc or datetime.now(timezone.utc)
    today_ist = today_ist or _now_ist(now).strftime("%Y-%m-%d")
    last_pass = state.get("last_pass_record") or {}
    connects = state.get("connects_balance", "Unknown")
    staged = state.get("staged_proposals") or []
    queue_count = len([j for j in staged if isinstance(j, dict)]) if isinstance(staged, list) else 0
    if queue_count == 0 and jobs:
        queue_count = sum(
            1 for j in jobs.values()
            if isinstance(j, dict) and j.get("status") in ("drafted", "preview_ready")
        )
    funnel = summarize_jobs_for_proof(jobs or {}, today_ist, now_utc=now)

    health_label = "HEALTHY" if last_pass.get("healthy") else "WARNING"
    searches_ok = last_pass.get("searches_ok", "?")
    searches_failed = last_pass.get("searches_failed", 0)
    candidates = last_pass.get("candidates", "?")
    new_jobs = last_pass.get("new", "?")
    staged_pass = last_pass.get("staged", 0)

    lines: List[str] = [
        "📡 <b>Daily Proof-of-Life: Upwork Engine Operational</b>",
        "",
        f"• 👑 <b>Lease:</b> <code>{html_mod.escape(str(tier))}</code> (commit <code>{html_mod.escape(str(get_commit_sha()))}</code>)",
        f"• 🟢 <b>Last pass:</b> {health_label} · searches {searches_ok} ok / {searches_failed} fail · candidates {candidates} · new {new_jobs} · staged {staged_pass}",
        f"• 🔑 <b>OAuth token age:</b> {html_mod.escape(str(token_age))}",
        f"• ⚡ <b>Connects:</b> {html_mod.escape(str(connects))} · 📋 <b>Review queue:</b> {queue_count}",
        f"• 🕒 <b>Date:</b> {today_ist} IST",
        "",
        f"<b>Jobs processed ({html_mod.escape(funnel['window_label'])}):</b>",
        f"• Analysed <b>{funnel['analysed']}</b> · APPLY <b>{funnel['apply']}</b> · REVIEW <b>{funnel['review']}</b> · filtered <b>{funnel['filtered']}</b>",
    ]

    breakdown = funnel.get("breakdown") or {}
    if breakdown:
        lines.append("")
        lines.append("<b>Why they did not make APPLY:</b>")
        for code, count in sorted(breakdown.items(), key=lambda kv: kv[1], reverse=True)[:5]:
            if code in ("APPLY", "REVIEW"):
                continue
            expl = DISQUALIFIER_EXPLANATIONS.get(code, code)
            lines.append(f"• <b>{html_mod.escape(str(code))}</b> ×{count} — {html_mod.escape(expl)}")

    lines.append("")
    lines.append("<b>Learnings:</b>")
    for item in funnel.get("learnings") or []:
        lines.append(f"• {html_mod.escape(item)}")

    msg = "\n".join(lines)
    if len(msg) > PROOF_OF_LIFE_MAX_CHARS:
        msg = msg[: PROOF_OF_LIFE_MAX_CHARS - 20] + "\n…<i>truncated</i>"
    return msg


def is_proof_of_life_due(state: Dict[str, Any], now_utc: Optional[datetime] = None) -> bool:
    """Check if daily proof-of-life is due (09:00 IST = 03:30 UTC)."""
    now_ist = _now_ist(now_utc)
    today_ist = now_ist.strftime("%Y-%m-%d")
    if now_ist.hour >= 9 and state.get("last_proof_of_life_date") != today_ist:
        return True
    return False


def persist_proof_of_life_date(state: Dict[str, Any], today_ist: str, state_mgr: Optional[StateManager] = None) -> None:
    """Write last_proof_of_life_date to local + store so the next tick does not resend."""
    state["last_proof_of_life_date"] = today_ist
    if not state_mgr:
        return
    try:
        persisted = dict(state_mgr.load_state() or {})
        persisted["last_proof_of_life_date"] = today_ist
        if state.get("last_pass_record"):
            persisted["last_pass_record"] = state["last_pass_record"]
        state_mgr.save_state(persisted)
        state.update(persisted)
    except Exception as e:
        logger.warning(f"Could not persist last_proof_of_life_date: {e}")


def send_proof_of_life(
    state: Dict[str, Any],
    tier: str,
    backend: StateBackend,
    state_mgr: Optional[StateManager] = None,
    jobs: Optional[Dict[str, Any]] = None,
) -> bool:
    """Dispatch daily 09:00 IST proof-of-life with job funnel and learnings. Once per IST day."""
    try:
        from .telegram_notifier import send_telegram_message

        now_utc = datetime.now(timezone.utc)
        today_ist = _now_ist(now_utc).strftime("%Y-%m-%d")

        if jobs is None and state_mgr is not None:
            try:
                jobs = state_mgr.load_jobs()
            except Exception as e:
                logger.warning(f"Proof-of-life jobs load failed: {e}")
                jobs = {}

        token_age = "Unknown"
        try:
            oauth_data, _ = backend.read_json("secrets/upwork_oauth.json")
            if oauth_data and oauth_data.get("updated_at"):
                up_dt = datetime.fromisoformat(str(oauth_data["updated_at"]).replace("Z", "+00:00"))
                token_age = f"{(now_utc - up_dt).total_seconds() / 3600.0:.1f}h"
        except Exception:
            pass

        msg = build_proof_of_life_message(
            state,
            tier,
            jobs=jobs or {},
            token_age=token_age,
            today_ist=today_ist,
            now_utc=now_utc,
        )
        sent = send_telegram_message(msg, parse_mode="HTML")
        if sent:
            persist_proof_of_life_date(state, today_ist, state_mgr=state_mgr)
        return bool(sent)
    except Exception as e:
        logger.warning(f"Error sending proof-of-life: {e}")
        return False


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
            ping_vercel_standby(active_tier)
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
        if is_proof_of_life_due(state):
            send_proof_of_life(state, active_tier, active_backend, state_mgr=state_mgr, jobs=jobs)
        write_heartbeat(active_backend, active_tier, ok=True, detail="Watchdog/Standby tick complete")
        ping_vercel_standby(active_tier)
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

    # 9. Daily report and proof-of-life (reload so last_pass + jobs include this hunt)
    try:
        state = state_mgr.load_state()
        jobs = state_mgr.load_jobs()
    except Exception as e:
        logger.warning(f"Reload after hunt for proof-of-life failed: {e}")
    if is_proof_of_life_due(state):
        send_proof_of_life(state, active_tier, active_backend, state_mgr=state_mgr, jobs=jobs)

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
    ping_vercel_standby(active_tier)
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
