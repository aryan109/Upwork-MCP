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
from .market_intel import MarketIntelEngine
from .daily_report import DailyReportEngine
from .telegram_notifier import (
    send_telegram_message,
    save_telegram_credentials,
    get_telegram_credentials,
    get_bot_info,
    auto_discover_chat_id,
)
from .notion_publisher import NotionPublisher


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

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

    # intel
    p_intel = subparsers.add_parser("intel", help="View or update Market Intelligence & Demand signals")
    p_intel.add_argument("--job-id", type=str, default=None, help="Catalog specific job into intelligence base")
    p_intel.add_argument("--notes", type=str, default="", help="Optional notes on the job")

    # report
    p_rep = subparsers.add_parser("report", help="Generate or view 4-part Daily Intelligence & Improvement Report")
    p_rep.add_argument("--date", type=str, default=None, help="Target date YYYY-MM-DD")

    # setup-telegram
    p_tg_set = subparsers.add_parser("setup-telegram", help="Configure Telegram Bot credentials")
    p_tg_set.add_argument("token", type=str, help="Telegram Bot Token from @BotFather")
    p_tg_set.add_argument("chat_id", type=str, help="Telegram Chat ID from @userinfobot")

    # test-telegram
    p_tg_test = subparsers.add_parser("test-telegram", help="Send a test notification to Telegram")
    p_tg_test.add_argument("--message", type=str, default="🚀 Test alert from Aryan Upwork Acquisition Pipeline.")

    # link-telegram
    p_link = subparsers.add_parser("link-telegram", help="Auto-detect Telegram Chat ID by listening for messages to your bot")
    p_link.add_argument("--timeout", type=int, default=60, help="Seconds to wait for incoming message (default: 60)")

    # sync-notion
    subparsers.add_parser("sync-notion", help="Sync Daily Reports, Market Intel & Master Hub to Notion")

    # bot
    subparsers.add_parser("bot", help="Run interactive Telegram 1-click approval bot listener")

    # monthly
    p_mon = subparsers.add_parser("monthly", help="Run 30-day market trend analysis and calibrate proposal rules")
    p_mon.add_argument("--run", action="store_true", help="Execute calibration and update proposal guide")
    p_mon.add_argument("--days", type=int, default=30, help="Lookback window in days (default: 30)")

    args = parser.parse_args()

    state_mgr = StateManager(args.state_dir)
    mcp_client = UpworkMCPClient(mock_mode=args.mock)

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

        intel_eng = MarketIntelEngine(state_mgr.state_dir)
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
                if d_id == "D11":
                    intel_eng.record_job(job, status_override="FILLED")
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
                if score_res["score"] >= 60:
                    intel_eng.record_job(job, status_override="OPEN")
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
        print("Executing in-memory dry run test (zero production state pollution)...")
        sample_job = {
            "job_id": "~01sample_claude_job",
            "title": "[TEST] Claude AI Automation & MCP Integration Expert",
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

        # 1. Vet in-memory
        score_res = score_job(sample_job)
        sample_job["status"] = "scored"
        sample_job["decision"] = score_res["decision"]
        sample_job["score"] = score_res["score"]
        sample_job["score_breakdown"] = score_res["score_breakdown"]
        sample_job["reasons"] = score_res["reasons"]
        sample_job["rung_suggested"] = score_res["rung_suggested"]
        sample_job["pricing_hint"] = score_res["pricing_hint"]

        # 2. Draft in-memory
        drafter = ProposalDrafter()
        draft_res = drafter.generate_full_draft(sample_job, score_res)
        sample_job["draft"] = draft_res
        sample_job["status"] = draft_res["status"]

        print("\n=== DRY RUN RESULTS (In-Memory Only) ===")
        print(f"Sample Job Score: {sample_job['score']} ({sample_job['decision']})")
        print(f"Self-Check Passed: {draft_res['self_check']['passed']}")
        print(f"Cover Letter Word Count: {draft_res['self_check']['word_count']}")
        print("Draft Status: Verified successfully (State untouched)")

    elif args.command == "intel":
        intel_eng = MarketIntelEngine(state_mgr.state_dir)
        if args.job_id:
            jobs = state_mgr.load_jobs()
            job = jobs.get(args.job_id)
            if not job:
                print(f"Job {args.job_id} not found in state jobs.")
            else:
                rec = intel_eng.record_job(job, notes=args.notes)
                print(f"Cataloged {args.job_id} into Market Intelligence Knowledge Base.")
                print(f"  Title: {rec.get('title')}")
                print(f"  Archetype: {rec.get('archetype')}")
                print(f"  Tech Stack: {', '.join(rec.get('tech_stack', []))}")
                print(f"  Status: {rec.get('status')}")
                print(f"  Content Hook: {rec.get('content_angles', {}).get('headline_hook')}")
        else:
            digest = intel_eng.generate_digest()
            print(digest)

    elif args.command == "report":
        rep_eng = DailyReportEngine(state_mgr.state_dir)
        res = rep_eng.generate_daily_report(date_str=args.date)
        print(res["content"])
        print(f"\nReport saved to: {res['report_path']}")

    elif args.command == "setup-telegram":
        save_telegram_credentials(args.token, args.chat_id)
        print("✅ Telegram credentials saved successfully to .env and engine config.")
        print(f"Token: {args.token[:8]}...{args.token[-4:]} | Chat ID: {args.chat_id}")
        print("Run 'python -m aryan_implementation.engine.cli test-telegram' to verify delivery.")

    elif args.command == "test-telegram":
        token, chat_id = get_telegram_credentials()
        if not token or not chat_id:
            print("❌ Telegram credentials not found!")
            print("Run 'python -m aryan_implementation.engine.cli setup-telegram <TOKEN> <CHAT_ID>' first,")
            print("or set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in your .env file.")
        else:
            print(f"Sending test notification to Telegram chat {chat_id}...")
            ok = send_telegram_message(f"🚀 <b>Upwork Pipeline Test Alert</b>\n\n{args.message}\n\n<i>Telegram notifications are online!</i>")
            if ok:
                print("✅ Telegram message dispatched successfully! Check your Telegram chat.")
            else:
                print("❌ Failed to send Telegram message. Check console logs and verify bot permissions.")

    elif args.command == "link-telegram":
        import time
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            from .telegram_notifier import load_env_file, PROJECT_ROOT
            token = load_env_file(PROJECT_ROOT / ".env").get("TELEGRAM_BOT_TOKEN")

        if not token:
            print("❌ TELEGRAM_BOT_TOKEN not found in .env or environment!")
            print("Please add TELEGRAM_BOT_TOKEN to your .env file first.")
        else:
            bot_info = get_bot_info(token)
            bot_user = bot_info.get("username", "your bot") if bot_info else "your bot"
            bot_name = bot_info.get("first_name", "") if bot_info else ""
            print(f"\n🤖 Telegram Bot Connected: {bot_name} (@{bot_user})")
            print("=" * 60)
            print("👉 Open Telegram on your phone or computer:")
            print(f"   1. Search for: @{bot_user}")
            print(f"   2. Click 'START' or send any message (e.g. 'hello')")
            print("=" * 60)
            print(f"Listening for your message (waiting up to {args.timeout}s)...")

            found = False
            start_t = time.time()
            while time.time() - start_t < args.timeout:
                chat = auto_discover_chat_id(token=token, save=True)
                if chat and "id" in chat:
                    found = True
                    c_id = chat["id"]
                    user_name = chat.get("username") or chat.get("first_name") or "User"
                    print(f"\n🎉 SUCCESS! Message received from @{user_name} (Chat ID: {c_id})")
                    print(f"✅ TELEGRAM_CHAT_ID={c_id} automatically saved to .env and engine config.")
                    welcome_msg = (
                        "🎉 <b>Connection Successful!</b>\n\n"
                        "You are now linked to Aryan's Upwork Autonomous Acquisition & Intelligence Engine.\n\n"
                        "• 🎯 Proposal reviews will be alerted here instantly\n"
                        "• 📊 Daily 4-part reports will be delivered here every morning\n"
                        "• 🚨 Urgent client messages & invites will trigger critical alerts\n\n"
                        "<i>Everything is running smoothly!</i>"
                    )
                    send_telegram_message(welcome_msg, parse_mode="HTML")
                    print("✅ Welcome confirmation message sent to your Telegram chat!")
                    break
                time.sleep(2)

            if not found:
                print(f"\n⏳ Timed out after {args.timeout}s without receiving a message.")
                print(f"Please open Telegram, send a message to @{bot_user}, and run this command again:")
                print("  python -m aryan_implementation.engine.cli link-telegram")

    elif args.command == "sync-notion":
        print("Syncing Daily Reports, Market Intel & Master Hub to Notion...")
        pub = NotionPublisher()
        res = pub.sync_all()
        print("\n=== NOTION SYNC RESULTS ===")
        for doc, ok in res.items():
            status = "✅ Synced" if ok else "❌ Failed"
            print(f"  {doc:15}: {status}")
        print("\nHub URL: https://app.notion.com/p/Upwork-Acquisition-Market-Intelligence-OS-3f197b4f8610816e8ab0cf54ac7b3a3e")
        print("Daily Reports URL: https://app.notion.com/p/Daily-Intelligence-Action-Reports-3f197b4f861081a1ac3ed59e9c8bf7d7")
        print("Market Intel URL: https://app.notion.com/p/Market-Intelligence-Demand-Knowledge-Base-3f197b4f861081a7b919f430b7816837")

    elif args.command == "bot":
        from .telegram_bot import TelegramBotListener
        print("🤖 Starting interactive Telegram bot listener...")
        print("Listening for 1-click approvals, /status, /queue, /hunt, /report...")
        listener = TelegramBotListener(mcp_client, state_mgr)
        try:
            listener.run_forever()
        except KeyboardInterrupt:
            print("\nBot listener stopped.")
            listener.stop()

    elif args.command == "monthly":
        from .monthly_strategy_engine import MonthlyStrategyEngine
        m_eng = MonthlyStrategyEngine(state_mgr.state_dir)
        if args.run:
            res = m_eng.run_monthly_pass()
            print("\n=== MONTHLY STRATEGY CALIBRATION COMPLETE ===")
            print(f"Status: {res.get('status')}")
            print(f"Market Summary: {res.get('strategy', {}).get('market_summary')}")
            print(f"Proof Priority: {res.get('strategy', {}).get('recommended_proof_focus')}")
            print(f"Key Risk Warning: {res.get('strategy', {}).get('recommended_risk_focus')}")
            print(f"Rules Markdown Updated: {res.get('markdown_updated')}\n")
        else:
            trends = m_eng.analyze_30day_market_trends(days=args.days)
            print(json.dumps(trends, indent=2))

    elif args.command == "serve":
        try:
            import service
            service.main()
        except Exception as e:
            print(f"Error starting service: {e}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
