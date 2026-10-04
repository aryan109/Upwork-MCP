"""
Unified CLI for Aryan Upwork MCP Acquisition Engine.
Allows manual and automated execution of hunt, vet, draft, review, submit, rebake, and maintenance.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import DEFAULT_ENGINE_DIR, STATE_DIR, FACTS_PATH
from .state_manager import StateManager
from .mcp_client import UpworkMCPClient
from .hunt import JobHunter
from .vet import check_disqualifiers, score_job
from .draft import ProposalDrafter
from .review_submit import ReviewSubmitManager
from .rebake import RebakeEngine
from .campaign_editor import CampaignEditor


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="upwork-engine",
        description="Aryan Upwork MCP Acquisition Engine",
    )
    parser.add_argument("--state-dir", type=str, default=None, help="Path to state directory")
    parser.add_argument("--mock", action="store_true", help="Force mock/offline mode for Upwork MCP")

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # init
    p_init = subparsers.add_parser("init", help="Initialize private state directory from templates")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing state files")

    # status
    subparsers.add_parser("status", help="Display operational status and metrics")

    # hunt
    p_hunt = subparsers.add_parser("hunt", help="Run job discovery across active campaigns")
    p_hunt.add_argument("--max-searches", type=int, default=20)
    p_hunt.add_argument("--max-details", type=int, default=25)
    p_hunt.add_argument("--best-match", action="store_true")

    # vet
    p_vet = subparsers.add_parser("vet", help="Score discovered jobs with the lead scoring rubric")
    p_vet.add_argument("--job-id", type=str, default=None, help="Vet specific job ID")

    # draft
    p_draft = subparsers.add_parser("draft", help="Draft proposals for APPLY jobs")
    p_draft.add_argument("--job-id", type=str, default=None)
    p_draft.add_argument("--max-drafts", type=int, default=3)

    # queue
    subparsers.add_parser("queue", help="Display pending proposals review queue")

    # submit
    p_submit = subparsers.add_parser("submit", help="Prepare or confirm proposal submission")
    p_submit.add_argument("--job-id", type=str, required=True)
    p_submit.add_argument("--confirm", action="store_true", help="Confirm submission (step 2)")
    p_submit.add_argument("--preview-id", type=str, default=None)

    # reject
    p_rej = subparsers.add_parser("reject", help="Reject a proposal draft")
    p_rej.add_argument("--job-id", type=str, required=True)
    p_rej.add_argument("--reason", type=str, default="Human reviewer skipped")

    # rebake
    subparsers.add_parser("rebake", help="Execute evening rebake and ledger reconciliation")

    # kill-switch
    p_ks = subparsers.add_parser("kill-switch", help="Toggle emergency kill switch")
    p_ks.add_argument("action", choices=["on", "off", "status"])
    p_ks.add_argument("--reason", type=str, default="")

    # dry-run
    p_dr = subparsers.add_parser("dry-run", help="Run simulated dry run across sample jobs")
    p_dr.add_argument("--sample-count", type=int, default=5)

    args = parser.parse_args()

    state_mgr = StateManager(args.state_dir)
    mcp_client = UpworkMCPClient(mock_mode=args.mock or True)  # default mock if offline

    if args.command == "init":
        res = state_mgr.init_state_directory(force=args.force)
        print("Initialization results:")
        for k, v in res.items():
            print(f"  {k}: {v}")
        print(f"State directory: {state_mgr.state_dir}")

    elif args.command == "status":
        state = state_mgr.load_state()
        jobs = state_mgr.load_jobs()
        camps = state_mgr.load_campaigns()

        print("=== UPWORK MCP ENGINE STATUS ===")
        print(f"State Directory: {state_mgr.state_dir}")
        print(f"Connects Balance: {state.get('connects_balance', 0)}")
        print(f"Monthly Connects Budget: {state.get('connects_budget_month', 250)}")
        print(f"Kill Switch: {'ACTIVE' if state.get('kill_switch') else 'OFF'}")
        print(f"Scoring Version: {state.get('scoring_version', '1.0')}")
        print(f"Last Run: {state.get('last_run_at', 'Never')}")

        status_counts: dict = {}
        for j in jobs.values():
            s = j.get("status", "unknown")
            status_counts[s] = status_counts.get(s, 0) + 1
        print(f"Jobs in Database: {len(jobs)} ({status_counts})")

        active_camps = [c['id'] for c in camps.get('campaigns', []) if c.get('active')]
        print(f"Active Campaigns ({len(active_camps)}): {', '.join(active_camps)}")

        incidents = [i for i in state.get("incidents", []) if not i.get("resolved")]
        print(f"Unresolved Incidents: {len(incidents)}")
        for inc in incidents[-3:]:
            print(f"  - [{inc.get('type')}] {inc.get('detail')}")

    elif args.command == "hunt":
        hunter = JobHunter(mcp_client, state_mgr)
        run_id = f"hunt_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        res = hunter.run_hunt(
            run_id=run_id,
            max_searches=args.max_searches,
            max_details=args.max_details,
            include_best_match=args.best_match,
        )
        print(f"Hunt complete: {res['new']} new, {res['detail_fetched']} fetched, {res['candidates_found']} candidates.")

    elif args.command == "vet":
        jobs = state_mgr.load_jobs()
        target_ids = [args.job_id] if args.job_id else [jid for jid, j in jobs.items() if j.get("status") == "discovered"]
        scored_count = 0
        apply_count = 0

        for jid in target_ids:
            if jid not in jobs:
                continue
            job = jobs[jid]
            is_disq, d_id, d_reason = check_disqualifiers(job)
            if is_disq:
                job["status"] = "skipped"
                job["decision"] = "SKIP"
                job["disqualifiers"] = [d_id]
                job["reasons"] = [d_reason]
                job["score"] = 0
            else:
                score_res = score_job(job)
                job["status"] = "scored"
                job["decision"] = score_res["decision"]
                job["score"] = score_res["score"]
                job["score_breakdown"] = score_res["score_breakdown"]
                job["reasons"] = score_res["reasons"]
                job["rung_suggested"] = score_res["rung_suggested"]
                job["pricing_hint"] = score_res["pricing_hint"]
                if score_res["decision"] == "APPLY":
                    apply_count += 1
            scored_count += 1

        state_mgr.save_jobs(jobs)
        print(f"Vetted {scored_count} jobs. APPLY count: {apply_count}")

    elif args.command == "draft":
        jobs = state_mgr.load_jobs()
        drafter = ProposalDrafter()
        drafted_count = 0

        target_ids = [args.job_id] if args.job_id else [jid for jid, j in jobs.items() if j.get("status") == "scored" and j.get("decision") == "APPLY"]

        for jid in target_ids[:args.max_drafts]:
            if jid not in jobs:
                continue
            job = jobs[jid]
            score_data = {
                "score": job.get("score", 70),
                "rung_suggested": job.get("rung_suggested", "sprint"),
            }
            draft_res = drafter.generate_full_draft(job, score_data)
            job["draft"] = draft_res
            job["status"] = draft_res["status"]
            drafted_count += 1

        state_mgr.save_jobs(jobs)
        print(f"Drafted proposals for {drafted_count} jobs.")

    elif args.command == "queue":
        rev_mgr = ReviewSubmitManager(mcp_client, state_mgr)
        queue = rev_mgr.get_review_queue()
        if not queue:
            print("Review queue is currently empty.")
            return
        print(f"=== REVIEW QUEUE ({len(queue)} items) ===\n")
        for item in queue:
            print(rev_mgr.format_review_item(item))
            print("\n" + "=" * 40 + "\n")

    elif args.command == "submit":
        rev_mgr = ReviewSubmitManager(mcp_client, state_mgr)
        run_id = f"submit_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        if not args.confirm:
            # Step 1: Prepare preview
            res = rev_mgr.prepare_submission(args.job_id, run_id=run_id)
            if res.get("ok"):
                print(f"[STEP 1 SUCCESS] Preview generated for {args.job_id}!")
                print(f"Preview ID: {res['preview_id']}")
                print("To complete submission, human must re-run with: --confirm --preview-id <PREVIEW_ID>")
            else:
                print(f"[PREVIEW ERROR]: {res.get('message')}")
        else:
            # Step 2: Confirm submission
            preview_id = args.preview_id or "prev_confirmed"
            res = rev_mgr.confirm_submission(
                job_id=args.job_id,
                preview_id=preview_id,
                human_confirmed=True,
                run_id=run_id,
            )
            if res.get("ok"):
                print(f"[SUBMISSION SUCCESS] Proposal {res['proposal_id']} submitted! Connects spent: {res['connects_spent']}")
            else:
                print(f"[SUBMISSION ERROR]: {res.get('message')}")

    elif args.command == "reject":
        rev_mgr = ReviewSubmitManager(mcp_client, state_mgr)
        res = rev_mgr.reject_draft(args.job_id, reason=args.reason)
        print(f"Job {args.job_id} status updated to {res.get('status')}")

    elif args.command == "rebake":
        rebake_eng = RebakeEngine(mcp_client, state_mgr)
        run_id = f"rebake_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        res = rebake_eng.run_rebake(run_id=run_id)
        print(res.get("digest"))

    elif args.command == "kill-switch":
        if args.action == "status":
            state = state_mgr.load_state()
            print(f"Kill switch status: {'ACTIVE (Blocked)' if state.get('kill_switch') else 'OFF (Normal)'}")
        elif args.action == "on":
            state_mgr.toggle_kill_switch(True, reason=args.reason or "Manually enabled via CLI")
            print("Emergency kill switch ACTIVATED. No proposals can be drafted or submitted.")
        elif args.action == "off":
            state_mgr.toggle_kill_switch(False, reason="Manually disabled via CLI")
            print("Kill switch DEACTIVATED. Normal operation resumed.")

    elif args.command == "dry-run":
        print("Executing end-to-end dry run test...")
        # 1. Init
        state_mgr.init_state_directory()
        # 2. Mock job injection
        jobs = state_mgr.load_jobs()
        sample_job = {
            "job_id": "~01sample_claude_job",
            "title": "Claude AI Automation & MCP Integration Expert",
            "description": "Looking for an expert to automate customer intake via Claude Code and custom MCP tools. Long-term workflow.",
            "type": "fixed",
            "budget_fixed": 1200,
            "duration": "1 to 3 months",
            "proposals_count": 8,
            "connects_cost": 16,
            "client_record": {
                "total_spent": 12000,
                "hire_rate_percent": 85,
                "rating": 4.95,
                "payment_verified": True,
                "country": "United Kingdom",
            },
            "activityStat": {
                "jobActivity": {"totalInvitedToInterview": 1, "invitesSent": 1}
            },
            "screening_questions": ["What is your experience with Claude and MCP?"],
            "first_seen_at": datetime.now(timezone.utc).isoformat(),
            "status": "discovered",
            "campaign": "claude-implementation",
        }
        jobs[sample_job["job_id"]] = sample_job
        state_mgr.save_jobs(jobs)

        # 3. Vet
        score_res = score_job(sample_job)
        sample_job["status"] = "scored"
        sample_job["decision"] = score_res["decision"]
        sample_job["score"] = score_res["score"]
        sample_job["score_breakdown"] = score_res["score_breakdown"]
        sample_job["reasons"] = score_res["reasons"]
        sample_job["rung_suggested"] = score_res["rung_suggested"]
        sample_job["pricing_hint"] = score_res["pricing_hint"]
        jobs[sample_job["job_id"]] = sample_job
        state_mgr.save_jobs(jobs)

        # 4. Draft
        drafter = ProposalDrafter()
        draft_res = drafter.generate_full_draft(sample_job, score_res)
        sample_job["draft"] = draft_res
        sample_job["status"] = draft_res["status"]
        jobs[sample_job["job_id"]] = sample_job
        state_mgr.save_jobs(jobs)

        print("\n=== DRY RUN RESULTS ===")
        print(f"Sample Job Score: {sample_job['score']} ({sample_job['decision']})")
        print(f"Self-Check Passed: {draft_res['self_check']['passed']}")
        print(f"Cover Letter Word Count: {draft_res['self_check']['word_count']}")
        print("Draft Status: Ready for human review")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
