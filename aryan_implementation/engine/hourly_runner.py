"""
Hourly Hunter & Market Intelligence Automation Runner for Aryan Upwork Acquisition Pipeline.
Discovers new jobs within minutes of posting, vets with D1-D11 disqualifiers, records demand
signals into Market Intelligence, and stages high-scoring drafts for rapid human review.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .ai_job_analyzer import AIJobAnalyzer
from .config import STATE_DIR, PROJECT_ROOT
from .daily_report import DailyReportEngine
from .draft import ProposalDrafter
from .hunt import JobHunter
from .market_intel import MarketIntelEngine
from .mcp_client import UpworkMCPClient
from .notifier import notify_proposal_ready
from .state_manager import StateManager
from .vet import check_disqualifiers, score_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("hourly_hunter")


def run_single_pass(
    state_mgr: StateManager,
    mcp_client: UpworkMCPClient,
    max_searches: int = 15,
    max_details: int = 20,
) -> Dict[str, Any]:
    """Execute a single hourly hunt, vet, intel capture, and staging pass."""
    now_utc = datetime.now(timezone.utc)
    run_id = f"hourly_{now_utc.strftime('%Y%m%d_%H%M%S')}"
    logger.info(f"=== Starting Hourly Hunter Pass [{run_id}] ===")

    state = state_mgr.load_state()
    if state.get("kill_switch", False):
        logger.warning("Emergency kill switch is active. Aborting hourly hunt pass.")
        return {"status": "aborted", "reason": "kill_switch_active"}

    jobs = state_mgr.load_jobs()
    hunter = JobHunter(mcp_client, state_mgr)
    intel_eng = MarketIntelEngine(state_mgr.state_dir)
    drafter = ProposalDrafter()
    ai_analyzer = AIJobAnalyzer(state_mgr.state_dir)

    # 1. Discover newly posted jobs
    hunt_res = hunter.run_hunt(
        run_id=run_id,
        max_searches=max_searches,
        max_details=max_details,
        include_best_match=False,
    )
    logger.info(
        f"Discovery completed: {hunt_res['candidates_found']} candidates found, "
        f"{hunt_res['new']} new, {hunt_res['detail_fetched']} details fetched."
    )

    # 2. Vet all newly discovered or refreshed jobs
    jobs = state_mgr.load_jobs()
    discovered_ids = [
        jid for jid, j in jobs.items()
        if j.get("status") == "discovered"
    ]

    vetted_count = 0
    staged_proposals: List[Dict[str, Any]] = []
    filled_caught: List[Dict[str, Any]] = []
    skipped_count = 0

    for jid in discovered_ids:
        job = jobs[jid]
        is_disq, d_id, d_reason = check_disqualifiers(job)

        if is_disq:
            job["status"] = "skipped"
            job["decision"] = "SKIP"
            job["disqualifiers"] = [d_id]
            job["reasons"] = [d_reason]
            job["score"] = 0.0

            if d_id == "D11":
                filled_caught.append(job)
                logger.info(f"⚡ [D11] Already-filled job caught: {job.get('title')} ({d_reason})")
                # Even though filled, catalog into Market Intelligence!
                intel_eng.record_job(job, status_override="FILLED")
            else:
                skipped_count += 1
        else:
            score_res = score_job(job)
            job["status"] = "scored"
            job["decision"] = score_res["decision"]
            job["score"] = score_res["score"]
            job["score_breakdown"] = score_res["score_breakdown"]
            job["reasons"] = score_res["reasons"]
            job["rung_suggested"] = score_res["rung_suggested"]
            job["pricing_hint"] = score_res["pricing_hint"]

            # Always capture high scoring jobs into intelligence
            if score_res["score"] >= 60.0:
                try:
                    intel_eng.record_job(job, status_override="OPEN")
                except Exception as intel_err:
                    logger.warning(f"Market intel capture warning for {jid}: {intel_err}")

            # 3. Deep AI Vetting for candidate APPLY jobs
            if score_res["decision"] == "APPLY":
                ai_eval = ai_analyzer.analyze_job_fit(job, score_res)
                job["ai_analysis"] = ai_eval

                if ai_eval.get("decision") == "SKIP" or ai_eval.get("client_risk_level") in ("HIGH", "CRITICAL"):
                    job["status"] = "ai_rejected"
                    job["decision"] = "SKIP"
                    job["reasons"] = ai_eval.get("toxic_client_flags", ["AI detected bad client / toxic flags"])
                    skipped_count += 1
                    logger.info(
                        f"🛑 [AI VETTING] Bad client intercepted: '{job.get('title')}' "
                        f"(Risk: {ai_eval.get('client_risk_level')}) - {ai_eval.get('fit_reasoning')}"
                    )
                else:
                    draft = drafter.generate_full_draft(job, score_res)
                    job["draft"] = draft
                    job["status"] = "drafted"
                    staged_proposals.append(job)
                    state_mgr.save_jobs(jobs)  # Persist immediately to prevent state loss
                    logger.info(
                        f"🎯 [APPLY] Staged proposal for '{job.get('title')}' "
                        f"(Score: {score_res['score']}, AI Fit: {ai_eval.get('fit_score')}) in review queue."
                    )
                    # Dispatch explicit desktop notification + interactive Telegram card
                    terms = draft.get("proposed_terms", {}) or draft.get("terms", {})
                    b_info = f"{terms.get('type', 'fixed')} (${terms.get('charge_rate', terms.get('charged_amount', 'TBD'))})"
                    job_url = job.get("url") or job.get("job_url") or f"https://www.upwork.com/jobs/~{jid}"
                    notify_proposal_ready(
                        job.get("title", "High-Fit Job"),
                        score_res["score"],
                        jid,
                        budget_info=b_info,
                        reasons=score_res.get("reasons", []),
                        job_url=job_url,
                        send_telegram=False,  # send_interactive_proposal below sends the rich card with buttons
                    )
                    try:
                        from .telegram_bot import send_interactive_proposal
                        send_interactive_proposal(job, score_res, draft)
                    except Exception as e:
                        logger.debug(f"Interactive proposal card note: {e}")

        vetted_count += 1

    # Save state
    state_mgr.save_jobs(jobs)
    try:
        intel_eng.generate_digest()
    except Exception as e:
        logger.warning(f"Digest generation warning: {e}")

    # Once-a-day daily comprehensive report compilation
    today_str = now_utc.strftime("%Y-%m-%d")
    if state.get("last_daily_report_date") != today_str:
        try:
            report_eng = DailyReportEngine(state_mgr.state_dir)
            report_eng.generate_daily_report(today_str)
            state["last_daily_report_date"] = today_str
            state_mgr.save_state(state)
            logger.info(f"Daily intelligence and improvement report compiled for {today_str}.")
        except Exception as e:
            logger.warning(f"Failed to auto-generate daily report: {e}")

    summary = {
        "run_id": run_id,
        "timestamp": now_utc.isoformat(),
        "discovered_total": len(discovered_ids),
        "vetted_count": vetted_count,
        "already_filled_caught": len(filled_caught),
        "staged_proposals": len(staged_proposals),
        "staged_titles": [p.get("title") for p in staged_proposals],
        "skipped_other": skipped_count,
    }

    logger.info(
        f"=== Hourly Pass Finished: {len(staged_proposals)} staged for review, "
        f"{len(filled_caught)} filled jobs intercepted by D11 ==="
    )
    return summary


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Aryan Upwork Hourly Hunter & Intel Runner")
    parser.add_argument("--once", action="store_true", help="Run a single pass and exit")
    parser.add_argument("--loop", action="store_true", help="Run continuously on an hourly schedule")
    parser.add_argument("--interval-minutes", type=int, default=60, help="Loop interval in minutes")
    parser.add_argument("--state-dir", type=Path, default=STATE_DIR, help="Path to state dir")
    parser.add_argument("--mock", action="store_true", default=False, help="Force mock mode")
    args = parser.parse_args()

    state_mgr = StateManager(args.state_dir)
    mcp_client = UpworkMCPClient(mock_mode=args.mock)

    if args.loop:
        logger.info(f"Starting continuous hourly hunter loop (interval: {args.interval_minutes}m)...")
        while True:
            try:
                run_single_pass(state_mgr, mcp_client)
            except Exception as e:
                logger.error(f"Error during hourly hunter execution: {e}", exc_info=True)
            logger.info(f"Sleeping for {args.interval_minutes} minutes until next run...")
            time.sleep(args.interval_minutes * 60)
    else:
        summary = run_single_pass(state_mgr, mcp_client)
        print("\n=== HOURLY HUNTER SUMMARY ===")
        print(f"Run ID: {summary.get('run_id')}")
        print(f"Discovered: {summary.get('discovered_total')}")
        print(f"Vetted: {summary.get('vetted_count')}")
        print(f"Filled Jobs Intercepted (D11): {summary.get('already_filled_caught')}")
        print(f"New Proposals Staged for Review: {summary.get('staged_proposals')}")
        if summary.get("staged_titles"):
            for t in summary["staged_titles"]:
                print(f"  - {t}")
        print("Market intelligence digest updated at market_intelligence_digest.md\n")


if __name__ == "__main__":
    main()
