"""
Dynamic Web-Based Daily Report & Analytics Dashboard Engine.
Compiles comprehensive daily audit data for Aryan's Upwork Pipeline:
- Strict 24h date isolation: ensures daily intelligence contains ONLY that target day's activity
- System Health & Downtime Tracker: detects if the hunter was offline or idle (elapsed hours/days)
- Explicit Queue Backlog: clearly separates proposals staged TODAY vs older pending backlog
- Selected jobs with detailed 'Why Selected' rationale
- Disqualified/rejected jobs with granular breakdown (D1-D11, AI toxicity, score floor)
- Connects preserved and economic impact
- Market observations, tech velocity, and rate ceilings
- Concrete next actions
- Dynamically rendered standalone HTML dashboard hosted on Railway
- Clean, structured Telegram summary
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import DISQUALIFIERS, PROJECT_ROOT, STATE_DIR
from .market_intel import MarketIntelEngine
from .state_manager import StateManager

logger = logging.getLogger("web_report")

# Positive matching signal human-readable descriptions
POSITIVE_SIGNAL_LABELS = {
    "title_strong_match": "High keyword match with core AI/Agent services",
    "title_moderate_match": "Target tech keywords in title",
    "desc_high_fit": "High technical overlap in project description",
    "client_verified": "Verified client payment method",
    "spend_high": "High historical client spend ($10k+)",
    "spend_medium": "Established client spend ($1k–$10k)",
    "hire_rate_strong": "High client hire rate (>50%)",
    "rating_top": "Top rated client (4.8+ ⭐)",
    "rung_impl": "Direct implementation sprint fit",
    "proof_adjacent": "Direct alignment with Aryan's proof portfolio",
    "budget_in_sweet_spot": "Budget in target zone ($50–$80/hr)",
    "ai_fit_high": "Passed AI deep vetting with low toxicity & clean scope",
}

DISQUALIFIER_EXPLANATIONS = {
    "D1": "Already applied, invitation exists, or cannot apply",
    "D2": "Location restricted (India ineligible)",
    "D3": "Capability gate (native mobile, 3D, Solidity outside target stack)",
    "D4": "Terms of Service or policy violation (off-platform contact)",
    "D5": "Staffing/agency pool or unpaid equity/commission only",
    "D6": "Payment unverified AND $0 spend AND 0 hires (Ghost client filter)",
    "D7": "Fixed under $100 or hourly ceiling under $25 (Below rate floor)",
    "D8": "Stale posting (>72h old, 50+ proposals, 0 interviewing)",
    "D9": "Free test task over 1 hour",
    "D10": "Conflict: open proposal or contract with same client",
    "D11": "Job already filled (hires reached limit; Connects preserved)",
    "AI_REJECTED": "AI Vetting intercepted toxic client / unrealistic scope trap",
    "SCORE_LOW": "Score below minimum threshold (<70 pts; low relevance)",
}


def get_public_service_url() -> str:
    """Retrieve public web report URL from environment or .env."""
    env_file = PROJECT_ROOT / ".env"
    env_vars = {}
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env_vars[k.strip()] = v.strip().strip("'\"")
        except Exception:
            pass

    domain = (
        os.environ.get("RAILWAY_PUBLIC_DOMAIN")
        or env_vars.get("RAILWAY_PUBLIC_DOMAIN")
        or os.environ.get("SERVICE_URL")
        or env_vars.get("SERVICE_URL")
        or os.environ.get("PUBLIC_URL")
        or env_vars.get("PUBLIC_URL")
        or os.environ.get("RAILWAY_STATIC_URL")
        or env_vars.get("RAILWAY_STATIC_URL")
    )
    if domain:
        domain = domain.strip()
        if not domain.startswith("http"):
            return f"https://{domain.rstrip('/')}"
        return domain.rstrip("/")

    return "http://localhost:8080"


def compile_daily_report_metrics(
    state_dir: Optional[Path] = None,
    target_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Compile exhaustive daily report metrics strictly isolated to target_date.
    Tracks today's activity, system downtime / health, and cumulative review backlog.
    """
    s_dir = state_dir or STATE_DIR
    state_mgr = StateManager(s_dir)
    intel_eng = MarketIntelEngine(s_dir)

    now_utc = datetime.now(timezone.utc)
    t_date = target_date or now_utc.strftime("%Y-%m-%d")

    state = state_mgr.load_state()
    jobs = state_mgr.load_jobs()
    intel = intel_eng.load_intelligence()

    # -------------------------------------------------------------
    # 1. System Health & Downtime Tracker
    # -------------------------------------------------------------
    latest_activity_dt: Optional[datetime] = None
    all_ts: List[str] = []
    # Principle P3: Heartbeat = proof of work (auth_ok & searches_ok), never just "loop ticked"
    if state.get("last_success_at"):
        all_ts.append(state["last_success_at"])
    elif state.get("last_hunt_pass_at") and state.get("last_pass_record", {}).get("auth_ok", True):
        all_ts.append(state["last_hunt_pass_at"])

    for j in jobs.values():
        for k in ["first_seen_at", "scraped_at", "vetted_at", "staged_at", "rejected_at"]:
            v = j.get(k)
            if v and isinstance(v, str):
                all_ts.append(v)

    for t_str in all_ts:
        try:
            dt_val = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
            if latest_activity_dt is None or dt_val > latest_activity_dt:
                latest_activity_dt = dt_val
        except Exception:
            pass

    if latest_activity_dt:
        elapsed_secs = max(0.0, (now_utc - latest_activity_dt).total_seconds())
        elapsed_hours = elapsed_secs / 3600.0
        elapsed_days = elapsed_secs / 86400.0
        if elapsed_days >= 1.0:
            elapsed_desc = f"{elapsed_days:.1f} days ago"
        elif elapsed_hours >= 1.0:
            elapsed_desc = f"{elapsed_hours:.1f} hours ago"
        else:
            elapsed_desc = f"{int(elapsed_secs // 60)} mins ago"

        # If more than 2 hours without a hunt, flag downtime
        is_downtime = (elapsed_hours > 2.0)
        system_health = {
            "is_downtime": is_downtime,
            "last_activity_at": latest_activity_dt.strftime("%Y-%m-%d %H:%M UTC"),
            "last_activity_date": latest_activity_dt.strftime("%Y-%m-%d"),
            "elapsed_hours": round(elapsed_hours, 1),
            "elapsed_desc": elapsed_desc,
            "status_label": f"⚠️ System Downtime / Inactive ({elapsed_desc})" if is_downtime else f"🟢 Hunter Online ({elapsed_desc})",
            "detail": f"Last marketplace hunt executed on {latest_activity_dt.strftime('%Y-%m-%d %H:%M UTC')}."
        }
    else:
        system_health = {
            "is_downtime": True,
            "last_activity_at": "Never",
            "last_activity_date": "None",
            "elapsed_hours": 999.0,
            "elapsed_desc": "No prior runs",
            "status_label": "⚠️ System Initializing: No hunt runs recorded",
            "detail": "No previous hunt runs recorded."
        }

    # -------------------------------------------------------------
    # 2. Strict Date Filtering for Target Day
    # -------------------------------------------------------------
    jobs_in_window: List[Dict[str, Any]] = []
    for jid, j in jobs.items():
        # Match if ANY timestamp belongs to target_date
        ts_candidates = [
            j.get("event_date"),
            j.get("vetted_date"),
            j.get("staged_date"),
            j.get("rejected_date"),
            j.get("vetted_at", "")[:10] if j.get("vetted_at") else "",
            j.get("staged_at", "")[:10] if j.get("staged_at") else "",
            j.get("rejected_at", "")[:10] if j.get("rejected_at") else "",
            j.get("scraped_at", "")[:10] if j.get("scraped_at") else "",
            j.get("first_seen_at", "")[:10] if j.get("first_seen_at") else "",
        ]
        if t_date in ts_candidates:
            jobs_in_window.append(j)

    # -------------------------------------------------------------
    # 3. Categorize Today's Activity & Cumulative Backlog
    # -------------------------------------------------------------
    selected_jobs_today: List[Dict[str, Any]] = []
    rejected_jobs_today: List[Dict[str, Any]] = []
    rejection_breakdown_today: Dict[str, Dict[str, Any]] = {}
    connects_saved_today = 0

    review_queue_backlog: List[Dict[str, Any]] = []

    # Process all jobs in state to track review queue backlog
    for jid, j in jobs.items():
        status = j.get("status", "")
        decision = j.get("decision", "")
        score = float(j.get("score") or 0.0)
        jid_str = str(j.get("job_id", "") or jid).lstrip("~")
        title = j.get("title") or "Untitled Job"
        url = j.get("url") or j.get("job_url") or f"https://www.upwork.com/jobs/~{jid_str}"

        terms = j.get("draft", {}).get("terms") or j.get("draft", {}).get("proposed_terms") or {}
        rate_info = j.get("pricing_hint")
        if not rate_info:
            b_type = terms.get("type") or j.get("type", "hourly")
            b_val = terms.get("charged_amount") or terms.get("charge_rate") or terms.get("hourly_bid") or j.get("budget_hourly_max") or "TBD"
            rate_info = f"{b_type.capitalize()} ${b_val}"

        reasons_raw = j.get("reasons", [])
        why_list = [POSITIVE_SIGNAL_LABELS.get(r, r.replace("_", " ").capitalize()) for r in reasons_raw]
        ai_analysis = j.get("ai_analysis") or {}
        if ai_analysis.get("fit_reasoning"):
            why_list.append(f"AI Fit: {ai_analysis.get('fit_reasoning')}")

        st_date = (
            j.get("staged_date")
            or (j.get("staged_at", "")[:10] if j.get("staged_at") else "")
            or (j.get("first_seen_at", "")[:10] if j.get("first_seen_at") else "")
            or "Unknown"
        )

        age_days = 0
        if st_date != "Unknown":
            try:
                s_dt = datetime.strptime(st_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                age_days = max(0, (now_utc - s_dt).days)
            except Exception:
                pass

        job_summary = {
            "job_id": jid_str,
            "title": title,
            "url": url,
            "score": score,
            "status": status,
            "pricing": rate_info,
            "why_selected": why_list or ["High client fit score"],
            "staged_date": st_date,
            "age_days": age_days,
            "ai_fit_score": ai_analysis.get("fit_score", score),
            "risk_level": ai_analysis.get("client_risk_level", "LOW"),
        }

        # Check if in pending review queue
        if status in ("drafted", "preview_ready"):
            if st_date == t_date:
                selected_jobs_today.append(job_summary)
            else:
                review_queue_backlog.append(job_summary)
        elif status == "submitted" and st_date == t_date:
            selected_jobs_today.append(job_summary)

    # Process jobs strictly in today's window for rejections
    for j in jobs_in_window:
        status = j.get("status", "")
        decision = j.get("decision", "")
        score = float(j.get("score") or 0.0)
        jid_str = str(j.get("job_id", "") or "").lstrip("~")
        title = j.get("title") or "Untitled Job"
        url = j.get("url") or j.get("job_url") or f"https://www.upwork.com/jobs/~{jid_str}"

        # If not selected
        if not (status in ("drafted", "preview_ready", "submitted") or decision == "APPLY"):
            code = "SKIP"
            reason_text = "Filtered by evaluation rubric"
            cat = "safeguard"

            disqs = j.get("disqualifiers", [])
            if disqs:
                code = disqs[0]
                reason_text = DISQUALIFIER_EXPLANATIONS.get(code, j.get("reasons", [code])[0] if j.get("reasons") else code)
                cat = "safeguard"
            elif status == "ai_rejected":
                code = "AI_REJECTED"
                reason_text = DISQUALIFIER_EXPLANATIONS["AI_REJECTED"]
                if j.get("reasons"):
                    reason_text = ", ".join(j.get("reasons")[:2])
                cat = "ai_risk"
            elif score > 0 and score < 70.0:
                code = "SCORE_LOW"
                reason_text = f"Score ({score:.1f}) below minimum 70.0 threshold"
                cat = "score_threshold"

            savings = 16 if code == "D11" else 8
            connects_saved_today += savings

            rejected_jobs_today.append({
                "job_id": jid_str,
                "title": title,
                "url": url,
                "score": score,
                "code": code,
                "reason": reason_text,
                "category": cat,
                "savings": savings,
            })

            if code not in rejection_breakdown_today:
                rejection_breakdown_today[code] = {
                    "code": code,
                    "label": DISQUALIFIERS.get(code, code),
                    "explanation": DISQUALIFIER_EXPLANATIONS.get(code, reason_text),
                    "count": 0,
                    "connects_saved": 0,
                    "examples": [],
                }
            rejection_breakdown_today[code]["count"] += 1
            rejection_breakdown_today[code]["connects_saved"] += savings
            if len(rejection_breakdown_today[code]["examples"]) < 3:
                rejection_breakdown_today[code]["examples"].append(title)

    total_analysed_today = len(jobs_in_window)
    sel_count_today = len(selected_jobs_today)
    rej_count_today = len(rejected_jobs_today)

    connects_balance = state.get("connects_balance", 110)
    connects_budget = state.get("connects_budget_month", 250)

    # Market Trends & Velocity
    records = list(intel.get("records", {}).values())
    tech_counts: Dict[str, int] = {}
    for r in records:
        for t in r.get("tech_stack", []):
            tech_counts[t] = tech_counts.get(t, 0) + 1

    top_techs: List[Tuple[str, int, str]] = []
    for tech, count in sorted(tech_counts.items(), key=lambda x: x[1], reverse=True)[:8]:
        velocity = "🔥 High Velocity (<3h hire)" if tech in ["Cursor", "Lovable", "RAG", "Evals", "Supabase", "MCP", "Claude"] else "Active"
        top_techs.append((tech, count, velocity))

    hourly_rates = [
        float(r["budget"]["hourly_max"])
        for r in records
        if r.get("budget", {}).get("type") == "hourly" and r.get("budget", {}).get("hourly_max")
    ]
    avg_hourly = (sum(hourly_rates) / len(hourly_rates)) if hourly_rates else 65.0
    top_ceiling = max(hourly_rates) if hourly_rates else 80.0

    # -------------------------------------------------------------
    # 4. Dynamic Observations & Synthesis
    # -------------------------------------------------------------
    observations: List[str] = []
    conclusions: List[str] = []
    possible_actions: List[str] = []

    if total_analysed_today == 0:
        if system_health["is_downtime"]:
            observations.append(
                f"⚠️ System Downtime / Inactivity Alert: No hunter passes executed on {t_date}. "
                f"Last marketplace hunt pass occurred on {system_health['last_activity_at']} ({system_health['elapsed_desc']})."
            )
            conclusions.append(f"Zero opportunities scanned today because the autonomous runner has been inactive.")
            possible_actions.append(f"Trigger an on-demand hunt pass immediately via Telegram (/hunt command) or check Railway cloud runner logs.")
        else:
            observations.append(
                f"🟢 System Healthy & Active: Hunter runner ran recently ({system_health['elapsed_desc']}), "
                f"but zero newly published jobs met campaign keywords during today's passes."
            )
            conclusions.append(f"Marketplace was quiet for target search terms on {t_date}.")
            possible_actions.append("Autonomous hunter loop continues monitoring campaigns every 15 minutes.")

        if review_queue_backlog:
            observations.append(
                f"Pending Review Backlog: {len(review_queue_backlog)} proposal(s) staged on earlier dates remain unreviewed in your queue."
            )
            conclusions.append(f"{len(review_queue_backlog)} older proposal(s) sitting in backlog awaiting operator review.")
            possible_actions.append(f"Clear your backlog: review {len(review_queue_backlog)} older staged draft(s) via Telegram (/queue command).")
    else:
        sel_pct = (sel_count_today / total_analysed_today * 100) if total_analysed_today > 0 else 0.0
        d6_count = rejection_breakdown_today.get("D6", {}).get("count", 0)
        d11_count = rejection_breakdown_today.get("D11", {}).get("count", 0)

        observations.append(f"Analyzed {total_analysed_today} opportunities today with a {sel_pct:.1f}% selection rate.")
        if d6_count > 0:
            observations.append(f"High noise of unverified clients: D6 filtered {d6_count} ghost leads with $0 spend, saving ~{d6_count * 8} Connects.")
        if d11_count > 0:
            observations.append(f"Intercepted {d11_count} already-filled jobs via D11, saving {d11_count * 16} Connects.")

        conclusions.append(f"{sel_count_today} proposals staged today; {rej_count_today} low-probability leads filtered out.")
        if sel_count_today > 0:
            possible_actions.append(f"Review and 1-click approve the {sel_count_today} proposal(s) staged today via Telegram (/queue).")

    possible_actions.append(f"Connects balance: {connects_balance} Connects remaining (within {connects_budget}/mo budget).")

    top_stack_name = top_techs[0][0] if top_techs else "Claude MCP"
    second_stack = top_techs[1][0] if len(top_techs) > 1 else "RAG"
    dynamic_hook = f"Why {top_stack_name} & {second_stack} prototypes fail on real customer documents (and how automated evals fix them)"
    if selected_jobs_today:
        best_title = selected_jobs_today[0]["title"]
        dynamic_hook = f"De-risking {best_title[:45]}: How to move from prototype to production architecture"
    elif review_queue_backlog:
        best_title = review_queue_backlog[0]["title"]
        dynamic_hook = f"De-risking {best_title[:45]}: How to move from prototype to production architecture"

    public_url = get_public_service_url()
    web_report_link = f"{public_url}/report"

    return {
        "date": t_date,
        "generated_at": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "system_health": system_health,
        "total_analysed": total_analysed_today,
        "selected_jobs": selected_jobs_today,
        "rejected_jobs": rejected_jobs_today,
        "rejection_breakdown": rejection_breakdown_today,
        "selected_count": sel_count_today,
        "rejected_count": rej_count_today,
        "connects_saved": connects_saved_today,
        "review_queue_backlog": review_queue_backlog,
        "backlog_count": len(review_queue_backlog),
        "total_tracked_cumulative": len(jobs),
        "connects_balance": connects_balance,
        "connects_budget": connects_budget,
        "avg_hourly": avg_hourly,
        "top_ceiling": top_ceiling,
        "top_techs": top_techs,
        "observations": observations,
        "conclusions": conclusions,
        "possible_actions": possible_actions,
        "dynamic_hook": dynamic_hook,
        "web_report_link": web_report_link,
    }


def render_telegram_summary_message(metrics: Dict[str, Any]) -> str:
    """
    Format a clean, concise, high-signal Telegram HTML notification
    with strict date isolation, downtime status, and review backlog.
    """
    date_str = metrics["date"]
    analysed = metrics["total_analysed"]
    sel_count = metrics["selected_count"]
    rej_count = metrics["rejected_count"]
    saved = metrics["connects_saved"]
    balance = metrics["connects_balance"]
    web_link = metrics["web_report_link"]
    health = metrics.get("system_health", {})
    backlog = metrics.get("review_queue_backlog", [])

    lines = [
        f"📊 <b>Daily Upwork Intelligence & Action Report ({date_str})</b>",
        "",
        "<b>1. Activity & Pipeline Today:</b>",
        f"• Jobs Analysed Today: <b>{analysed}</b>",
        f"• Selected for Review: <b>{sel_count}</b> 🎯",
        f"• Disqualified / Filtered: <b>{rej_count}</b> 🛑",
        f"• Connects Preserved Today: <b>~{saved} Connects</b> 🛡️",
        f"• Connects Balance: <b>{balance}</b>",
        "",
        "<b>2. System Health & Runner Status:</b>",
    ]

    if health.get("is_downtime"):
        lines.append(f"⚠️ <b>DOWNTIME / INACTIVE ALERT:</b> Last marketplace scan was <b>{health.get('elapsed_desc')}</b> ({health.get('last_activity_at')}). No hunter passes ran today.")
    else:
        lines.append(f"🟢 <b>SYSTEM ACTIVE:</b> Hunter loop is running healthy (last pass: {health.get('elapsed_desc')}).")
    lines.append("")

    # 3. Review Queue Backlog
    if backlog:
        lines.append(f"<b>3. 📋 Review Queue Backlog ({len(backlog)} pending from earlier dates):</b>")
        for job in backlog[:3]:
            title = html.escape(job["title"])
            url = job["url"]
            score = job["score"]
            pricing = job["pricing"]
            s_date = job.get("staged_date", "earlier")
            age = job.get("age_days", 0)
            lines.append(f"• <a href=\"{url}\"><b>{title}</b></a>")
            lines.append(f"  ├ <i>Staged:</i> <b>{s_date} ({age}d ago)</b> | <i>Score:</i> <code>{score:.1f}/100</code> | <i>Terms:</i> {pricing}")
            lines.append(f"  └ <i>Status:</i> Awaiting your approval (use /queue)")
        lines.append("")
    else:
        lines.append("<b>3. 📋 Review Queue Backlog:</b>")
        lines.append("• <i>Review queue is completely clean (0 pending).</i>")
        lines.append("")

    # 4. Selected Jobs Today
    if metrics["selected_jobs"]:
        lines.append(f"<b>4. 🎯 Selected Jobs (Why Selected) — {date_str}:</b>")
        for job in metrics["selected_jobs"][:3]:
            title = html.escape(job["title"])
            url = job["url"]
            score = job["score"]
            pricing = job["pricing"]
            why_text = "; ".join(job["why_selected"][:2])
            lines.append(f"• <a href=\"{url}\"><b>{title}</b></a>")
            lines.append(f"  ├ <i>Score:</i> <code>{score:.1f}/100</code> | <i>Terms:</i> <b>{pricing}</b>")
            lines.append(f"  └ <i>Why:</i> {html.escape(why_text)}")
        lines.append("")
    else:
        lines.append(f"<b>4. 🎯 Proposals Staged TODAY ({date_str}):</b>")
        lines.append("• <i>0 proposals staged today (high selectivity & date isolation active).</i>")
        lines.append("")

    # 5. Rejections Breakdown Today
    breakdown = metrics.get("rejection_breakdown", {})
    if breakdown:
        lines.append(f"<b>5. 🛑 Rejections Breakdown & Why ({rej_count} filtered):</b>")
        sorted_bd = sorted(breakdown.values(), key=lambda x: x["count"], reverse=True)
        for item in sorted_bd[:4]:
            code = item["code"]
            count = item["count"]
            expl = html.escape(item["explanation"])
            lines.append(f"• <b>{code} ({count} jobs):</b> {expl}")
        lines.append("")
    else:
        lines.append("<b>5. 🛑 Rejections Breakdown & Why:</b>")
        lines.append(f"• <i>0 leads filtered today.</i>")
        lines.append("")

    # 6. Today's Observation & Conclusion
    lines.append("<b>6. 💡 Today's Observation & Conclusion:</b>")
    for obs in metrics.get("observations", [])[:2]:
        lines.append(f"• {html.escape(obs)}")
    lines.append("")

    # 7. Possible Actions
    lines.append("<b>7. 🚀 Recommended Actions:</b>")
    for idx, act in enumerate(metrics.get("possible_actions", [])[:3], 1):
        lines.append(f"{idx}. {html.escape(act)}")
    lines.append("")

    # 8. Links
    lines.append("<b>8. Live Report & Command Links:</b>")
    lines.append(f"🌐 <a href=\"{web_link}\"><b>Open Dynamic Web Report Dashboard</b></a>")
    lines.append("💼 <a href=\"https://app.notion.com/p/Upwork-Acquisition-Market-Intelligence-OS-3f197b4f8610816e8ab0cf54ac7b3a3e\">Command Center</a> • 🤖 Send <b>/hunt</b> or <b>/queue</b>")

    return "\n".join(lines)


def render_html_dashboard(metrics: Dict[str, Any]) -> str:
    """
    Render a modern, high-aesthetic, responsive dark-mode HTML daily report dashboard.
    Features live uptime banner, date isolation, and separate review queue backlog.
    """
    date_str = html.escape(metrics["date"])
    gen_at = html.escape(metrics["generated_at"])
    analysed = metrics["total_analysed"]
    sel_count = metrics["selected_count"]
    rej_count = metrics["rejected_count"]
    saved = metrics["connects_saved"]
    balance = metrics["connects_balance"]
    avg_hourly = metrics["avg_hourly"]
    top_ceiling = metrics["top_ceiling"]
    health = metrics.get("system_health", {})
    backlog = metrics.get("review_queue_backlog", [])
    total_cum = metrics.get("total_tracked_cumulative", 0)

    # Health Banner
    if health.get("is_downtime"):
        banner_html = f"""
        <div class="banner banner-warning">
            <div class="banner-icon">&#9888;&#65039;</div>
            <div>
                <strong>SYSTEM DOWNTIME / INACTIVITY DETECTED</strong> &bull;
                Last active marketplace hunt occurred <strong>{health.get('elapsed_desc')}</strong> ({health.get('last_activity_at')}).
                No hunt passes were recorded on {date_str}.
            </div>
        </div>
        """
    else:
        banner_html = f"""
        <div class="banner banner-success">
            <div class="banner-icon">&#9989;</div>
            <div>
                <strong>SYSTEM OPERATIONAL &bull; CLOUD RUNNER ACTIVE</strong> &bull;
                Last cycle completed {health.get('elapsed_desc')} ({health.get('last_activity_at')}).
            </div>
        </div>
        """

    # Selected Today HTML Cards
    selected_html_cards = []
    if metrics["selected_jobs"]:
        for job in metrics["selected_jobs"]:
            j_title = html.escape(job["title"])
            j_url = html.escape(job["url"])
            j_score = f"{job['score']:.1f}"
            j_pricing = html.escape(job["pricing"])
            why_badges = "".join(f'<span class="badge badge-success">{html.escape(w)}</span>' for w in job["why_selected"])
            selected_html_cards.append(f"""
            <div class="job-card selected">
                <div class="job-header">
                    <div>
                        <div class="job-title"><a href="{j_url}" target="_blank">{j_title}</a></div>
                        <div class="job-meta">
                            <span class="badge badge-primary">Score {j_score}/100</span>
                            <span class="badge badge-accent">{j_pricing}</span>
                            <span class="badge badge-success">STAGED TODAY</span>
                        </div>
                    </div>
                    <a href="{j_url}" target="_blank" class="btn btn-sm btn-primary">Review on Upwork &rarr;</a>
                </div>
                <div class="job-why">
                    <div class="why-label">&#10004; Why Selected:</div>
                    <div class="badges-wrap">{why_badges}</div>
                </div>
            </div>
            """)
    else:
        selected_html_cards.append(f"""
        <div class="empty-state">
            <div class="empty-icon">&#128065;</div>
            <div class="empty-title">Zero Proposals Staged Today ({date_str})</div>
            <div class="empty-desc">Strict date isolation active: no new leads met thresholds or were scraped on this date.</div>
        </div>
        """)
    selected_cards_rendered = "\n".join(selected_html_cards)

    # Review Queue Backlog Cards
    backlog_html_cards = []
    if backlog:
        for job in backlog:
            b_title = html.escape(job["title"])
            b_url = html.escape(job["url"])
            b_score = f"{job['score']:.1f}"
            b_pricing = html.escape(job["pricing"])
            b_date = html.escape(job.get("staged_date", "earlier"))
            b_age = job.get("age_days", 0)
            why_badges = "".join(f'<span class="badge badge-outline">{html.escape(w)}</span>' for w in job["why_selected"])
            backlog_html_cards.append(f"""
            <div class="job-card backlog">
                <div class="job-header">
                    <div>
                        <div class="job-title"><a href="{b_url}" target="_blank">{b_title}</a></div>
                        <div class="job-meta">
                            <span class="badge badge-warning">Staged on {b_date} ({b_age}d ago)</span>
                            <span class="badge badge-primary">Score {b_score}/100</span>
                            <span class="badge badge-accent">{b_pricing}</span>
                        </div>
                    </div>
                    <a href="{b_url}" target="_blank" class="btn btn-sm btn-outline">Review &rarr;</a>
                </div>
                <div class="job-why">
                    <div class="why-label">Original Match Rationale:</div>
                    <div class="badges-wrap">{why_badges}</div>
                </div>
            </div>
            """)
    else:
        backlog_html_cards.append("""
        <div class="empty-state">
            <div class="empty-icon">&#10004;&#65039;</div>
            <div class="empty-title">Review Queue Backlog is Clean</div>
            <div class="empty-desc">No older proposals pending human review.</div>
        </div>
        """)
    backlog_cards_rendered = "\n".join(backlog_html_cards)

    # Rejections Breakdown HTML
    rejection_items = []
    breakdown = metrics.get("rejection_breakdown", {})
    if breakdown:
        sorted_bd = sorted(breakdown.values(), key=lambda x: x["count"], reverse=True)
        for item in sorted_bd:
            code = html.escape(item["code"])
            label = html.escape(item["label"])
            expl = html.escape(item["explanation"])
            cnt = item["count"]
            pct = (cnt / rej_count * 100) if rej_count > 0 else 0
            c_saved = item["connects_saved"]
            examples_html = "".join(f"<li>{html.escape(ex)}</li>" for ex in item["examples"])
            rejection_items.append(f"""
            <div class="rejection-item">
                <div class="rej-top">
                    <div class="rej-title">
                        <span class="badge badge-danger">{code}</span>
                        <strong>{label}</strong>
                    </div>
                    <div class="rej-count">{cnt} jobs <span class="pct">({pct:.0f}%)</span> &bull; <em>+{c_saved} connects saved</em></div>
                </div>
                <div class="rej-desc">{expl}</div>
                {f'<details class="rej-examples"><summary>Show sample filtered jobs ({len(item["examples"])})</summary><ul>{examples_html}</ul></details>' if examples_html else ''}
                <div class="progress-bar-bg"><div class="progress-bar-fill" style="width: {pct}%"></div></div>
            </div>
            """)
    else:
        rejection_items.append(f"""
        <div class="empty-state">
            <div class="empty-icon">&#128737;&#65039;</div>
            <div class="empty-title">Zero Rejections Recorded Today ({date_str})</div>
            <div class="empty-desc">No new opportunities were ingested or processed today.</div>
        </div>
        """)
    rejection_cards_rendered = "\n".join(rejection_items)

    obs_html = "".join(f"<li>{html.escape(o)}</li>" for o in metrics.get("observations", []))
    conc_html = "".join(f"<li>{html.escape(c)}</li>" for c in metrics.get("conclusions", []))
    actions_html = "".join(f"<li><label><input type='checkbox'> <span>{html.escape(a)}</span></label></li>" for a in metrics.get("possible_actions", []))

    tech_badges = "".join(
        f'<span class="badge badge-tech">{html.escape(t[0])} <small>({t[1]} leads &bull; {t[2]})</small></span>'
        for t in metrics.get("top_techs", [])
    )

    dynamic_hook = html.escape(metrics.get("dynamic_hook", ""))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Daily Upwork Intelligence & Action Report &bull; {date_str}</title>
    <style>
        :root {{
            --bg-base: #090d16;
            --bg-surface: #0f172a;
            --bg-card: #1e293b;
            --border: #334155;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #38bdf8;
            --primary-glow: rgba(56, 189, 248, 0.15);
            --success: #10b981;
            --success-glow: rgba(16, 185, 129, 0.15);
            --danger: #f43f5e;
            --danger-glow: rgba(244, 63, 94, 0.15);
            --warning: #f59e0b;
            --accent: #818cf8;
            --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background-color: var(--bg-base);
            color: var(--text-main);
            font-family: var(--font);
            line-height: 1.6;
            padding: 24px 16px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        header {{
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 24px 28px;
            margin-bottom: 16px;
            box-shadow: 0 10px 25px -5px rgba(0,0,0,0.5);
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
        }}
        .brand-title {{
            font-size: 1.6rem;
            font-weight: 700;
            background: linear-gradient(to right, #38bdf8, #818cf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .brand-subtitle {{ color: var(--text-muted); font-size: 0.95rem; margin-top: 4px; }}
        .header-badges {{ display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }}
        .banner {{
            border-radius: 12px;
            padding: 14px 18px;
            margin-bottom: 24px;
            display: flex;
            align-items: center;
            gap: 14px;
            font-size: 0.92rem;
            border: 1px solid transparent;
        }}
        .banner-warning {{ background: rgba(245, 158, 11, 0.12); border-color: rgba(245, 158, 11, 0.3); color: #fde68a; }}
        .banner-success {{ background: rgba(16, 185, 129, 0.12); border-color: rgba(16, 185, 129, 0.3); color: #a7f3d0; }}
        .banner-icon {{ font-size: 1.4rem; }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 16px;
            margin-bottom: 28px;
        }}
        .kpi-card {{
            background: var(--bg-surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
            transition: transform 0.2s, border-color 0.2s;
        }}
        .kpi-card:hover {{ transform: translateY(-2px); border-color: var(--primary); }}
        .kpi-label {{
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            margin-bottom: 6px;
        }}
        .kpi-value {{ font-size: 2.1rem; font-weight: 800; line-height: 1.1; }}
        .kpi-subtext {{ font-size: 0.82rem; color: var(--text-muted); margin-top: 6px; }}
        .kpi-success .kpi-value {{ color: var(--success); }}
        .kpi-danger .kpi-value {{ color: var(--danger); }}
        .kpi-primary .kpi-value {{ color: var(--primary); }}
        .kpi-warning .kpi-value {{ color: var(--warning); }}
        .grid-2col {{
            display: grid;
            grid-template-columns: 1.1fr 0.9fr;
            gap: 24px;
            margin-bottom: 28px;
        }}
        @media (max-width: 900px) {{ .grid-2col {{ grid-template-columns: 1fr; }} }}
        .panel {{
            background: var(--bg-surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3);
            margin-bottom: 24px;
        }}
        .panel-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--border);
        }}
        .panel-title {{
            font-size: 1.25rem;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .badge {{
            display: inline-flex;
            align-items: center;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
        }}
        .badge-primary {{ background: var(--primary-glow); color: var(--primary); border: 1px solid rgba(56, 189, 248, 0.3); }}
        .badge-success {{ background: var(--success-glow); color: var(--success); border: 1px solid rgba(16, 185, 129, 0.3); }}
        .badge-danger {{ background: var(--danger-glow); color: var(--danger); border: 1px solid rgba(244, 63, 94, 0.3); }}
        .badge-warning {{ background: rgba(245, 158, 11, 0.15); color: var(--warning); border: 1px solid rgba(245, 158, 11, 0.3); }}
        .badge-accent {{ background: rgba(129, 140, 248, 0.15); color: var(--accent); border: 1px solid rgba(129, 140, 248, 0.3); }}
        .badge-outline {{ background: transparent; color: var(--text-muted); border: 1px solid var(--border); }}
        .badge-tech {{ background: #1e293b; color: #cbd5e1; border: 1px solid #475569; padding: 6px 12px; margin: 4px; }}
        .badge-tech small {{ color: #94a3b8; margin-left: 4px; }}
        .btn {{
            display: inline-flex;
            align-items: center;
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 0.85rem;
            font-weight: 600;
            text-decoration: none;
            cursor: pointer;
            border: none;
        }}
        .btn-sm {{ padding: 6px 12px; font-size: 0.8rem; }}
        .btn-primary {{ background: var(--primary); color: #0f172a; }}
        .btn-outline {{ background: transparent; color: var(--text-main); border: 1px solid var(--border); }}
        .job-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 18px;
            margin-bottom: 16px;
        }}
        .job-card.selected {{ border-left: 4px solid var(--success); }}
        .job-card.backlog {{ border-left: 4px solid var(--warning); }}
        .job-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 12px;
            margin-bottom: 12px;
        }}
        .job-title a {{ color: var(--text-main); text-decoration: none; font-weight: 700; font-size: 1.05rem; }}
        .job-title a:hover {{ color: var(--primary); }}
        .job-meta {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 6px; }}
        .job-why {{
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 12px;
            margin-top: 10px;
        }}
        .why-label {{ font-size: 0.8rem; font-weight: 700; color: var(--text-muted); margin-bottom: 6px; }}
        .badges-wrap {{ display: flex; flex-wrap: wrap; gap: 6px; }}
        .rejection-item {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 14px 16px;
            margin-bottom: 12px;
        }}
        .rej-top {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }}
        .rej-title {{ display: flex; align-items: center; gap: 8px; }}
        .rej-count {{ font-size: 0.85rem; font-weight: 600; color: var(--text-main); }}
        .rej-desc {{ font-size: 0.85rem; color: var(--text-muted); margin-bottom: 8px; }}
        .progress-bar-bg {{ background: #0f172a; border-radius: 999px; height: 6px; overflow: hidden; margin-top: 8px; }}
        .progress-bar-fill {{ background: linear-gradient(to right, var(--danger), var(--warning)); height: 100%; }}
        .empty-state {{ text-align: center; padding: 36px 20px; color: var(--text-muted); }}
        .empty-icon {{ font-size: 2.2rem; margin-bottom: 10px; }}
        .empty-title {{ font-size: 1.1rem; font-weight: 600; color: var(--text-main); }}
        .empty-desc {{ font-size: 0.85rem; margin-top: 4px; }}
        ul.clean-list {{ list-style: none; padding: 0; }}
        ul.clean-list li {{ position: relative; padding-left: 24px; margin-bottom: 12px; font-size: 0.92rem; color: #cbd5e1; }}
        ul.clean-list li::before {{ content: "•"; position: absolute; left: 8px; color: var(--primary); font-weight: bold; }}
        ul.checklist label {{ display: flex; align-items: center; gap: 10px; cursor: pointer; }}
        ul.checklist input[type="checkbox"] {{ accent-color: var(--success); width: 16px; height: 16px; }}
        .hook-box {{
            background: linear-gradient(135deg, rgba(56, 189, 248, 0.08) 0%, rgba(129, 140, 248, 0.08) 100%);
            border: 1px dashed var(--primary);
            border-radius: 12px;
            padding: 18px;
            margin-top: 14px;
        }}
        .hook-label {{ font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--primary); font-weight: 700; margin-bottom: 6px; }}
        .hook-text {{ font-size: 1.05rem; font-weight: 600; color: #fff; font-style: italic; }}
        footer {{ text-align: center; padding: 30px 20px; color: var(--text-muted); font-size: 0.85rem; border-top: 1px solid var(--border); margin-top: 40px; }}
        footer a {{ color: var(--primary); text-decoration: none; }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header>
            <div>
                <div class="brand-title">Aryan Upwork Intelligence & Action OS</div>
                <div class="brand-subtitle">Strict 24h Date Audit &bull; Target Date: <strong>{date_str}</strong> &bull; Generated: {gen_at}</div>
            </div>
            <div class="header-badges">
                <span class="badge badge-primary">{balance} Connects Available</span>
                <span class="badge badge-outline">{total_cum} Cumulative in Archive</span>
                <a href="/api/daily-report" target="_blank" class="btn btn-sm btn-primary">JSON API &rarr;</a>
            </div>
        </header>

        <!-- System Uptime & Downtime Alert Banner -->
        {banner_html}

        <!-- KPI Grid for Target Date -->
        <div class="kpi-grid">
            <div class="kpi-card kpi-primary">
                <div class="kpi-label">Jobs Analysed Today</div>
                <div class="kpi-value">{analysed}</div>
                <div class="kpi-subtext">Scanned strictly on {date_str}</div>
            </div>
            <div class="kpi-card kpi-success">
                <div class="kpi-label">Staged Today (APPLY)</div>
                <div class="kpi-value">{sel_count}</div>
                <div class="kpi-subtext">New drafts prepared today</div>
            </div>
            <div class="kpi-card kpi-warning">
                <div class="kpi-label">Queue Backlog</div>
                <div class="kpi-value">{len(backlog)}</div>
                <div class="kpi-subtext">Pending from previous days</div>
            </div>
            <div class="kpi-card kpi-danger">
                <div class="kpi-label">Disqualified Today</div>
                <div class="kpi-value">{rej_count}</div>
                <div class="kpi-subtext">Filtered by safeguards on {date_str}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">Connects Preserved Today</div>
                <div class="kpi-value">~{saved}</div>
                <div class="kpi-subtext">&asymp; ${saved * 0.15:.2f} budget saved</div>
            </div>
        </div>

        <!-- Section: Today's Staged Proposals vs Today's Rejections -->
        <div class="grid-2col">
            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title">&#127919; Staged Today on {date_str} ({sel_count})</div>
                    <span class="badge badge-success">New Activity</span>
                </div>
                {selected_cards_rendered}
            </div>

            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title">&#128721; Disqualified Today ({rej_count})</div>
                    <span class="badge badge-danger">Safeguards Active</span>
                </div>
                {rejection_cards_rendered}
            </div>
        </div>

        <!-- Section: Review Queue Backlog from Earlier Dates -->
        <div class="panel">
            <div class="panel-header">
                <div class="panel-title">&#128203; Review Queue Backlog ({len(backlog)} Pending from Earlier Dates)</div>
                <span class="badge badge-warning">Awaiting Aryan's Approval</span>
            </div>
            <div style="font-size: 0.88rem; color: var(--text-muted); margin-bottom: 16px;">
                These proposals were staged on previous dates and remain unreviewed in your queue. They are NOT new leads from today.
            </div>
            {backlog_cards_rendered}
        </div>

        <!-- Observations & Next Actions Panels -->
        <div class="grid-2col">
            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title">&#128161; Today's Observation & Conclusion</div>
                    <span class="badge badge-primary">Intelligence</span>
                </div>
                <ul class="clean-list">
                    {obs_html}
                </ul>
                <div style="margin-top: 18px;">
                    <div style="font-size: 0.8rem; text-transform: uppercase; color: var(--text-muted); font-weight: 700; margin-bottom: 8px;">Top High-Velocity Stacks:</div>
                    <div style="display: flex; flex-wrap: wrap; gap: 4px;">
                        {tech_badges}
                    </div>
                </div>
            </div>

            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title">&#128640; Actionable Next Steps</div>
                    <span class="badge badge-warning">Operator Focus</span>
                </div>
                <ul class="clean-list checklist">
                    {actions_html}
                </ul>
                <div style="margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--border);">
                    <div style="font-size: 0.8rem; text-transform: uppercase; color: var(--text-muted); font-weight: 700; margin-bottom: 6px;">Executive Summary:</div>
                    <ul class="clean-list" style="font-size: 0.85rem;">
                        {conc_html}
                    </ul>
                </div>
            </div>
        </div>

        <!-- Optional Marketing Concept -->
        <div class="panel">
            <div class="panel-header">
                <div class="panel-title">&#128227; Today's Market-Derived Proof Angle</div>
                <span class="badge badge-accent">Authority Asset</span>
            </div>
            <div class="hook-box">
                <div class="hook-label">Topic Derived from Active Client Pain Points:</div>
                <div class="hook-text">&ldquo;{dynamic_hook}&rdquo;</div>
                <div style="font-size: 0.82rem; color: var(--text-muted); margin-top: 6px;">
                    Optional angle for a 3-minute Loom video or Upwork Project Catalog headline.
                </div>
            </div>
        </div>

        <!-- Footer -->
        <footer>
            Aryan Upwork Autonomous Acquisition Engine &bull; Deployed on Railway &bull;
            <a href="https://app.notion.com/p/Upwork-Acquisition-Market-Intelligence-OS-3f197b4f8610816e8ab0cf54ac7b3a3e" target="_blank">Notion Command Center</a> &bull;
            Telegram Bot: <code>/hunt</code> &bull; <code>/queue</code> &bull; <code>/status</code> &bull; <code>/report</code>
        </footer>
    </div>
</body>
</html>
"""
