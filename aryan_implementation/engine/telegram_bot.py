"""
Interactive Telegram Bot Engine for Aryan Upwork Acquisition Pipeline.
Provides real-time 1-click proposal approvals, status checks, and command execution:
- [✅ Approve & Submit]: Confirms proposal preview and submits to Upwork via MCP.
- [📖 View Cover Letter]: Displays the full 4-part cover letter and screening answers.
- [❌ Skip / Reject]: Rejects the lead and archives it in state.
- Commands: /status, /queue, /hunt, /report, /sync, /help
"""
from __future__ import annotations

import html
import json
import logging
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import PROJECT_ROOT, STATE_DIR
from .draft import sanitize_no_em_dash
from .mcp_client import UpworkMCPClient
from .review_submit import ReviewSubmitManager
from .state_manager import StateManager
from .telegram_notifier import (
    get_telegram_credentials,
    send_telegram_message,
    NOTION_DAILY_REPORT_URL,
    NOTION_HUB_URL,
)

logger = logging.getLogger("telegram_bot")


def telegram_api_call(method: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Generic helper to call Telegram Bot API methods."""
    token, _ = get_telegram_credentials()
    if not token:
        logger.warning(f"Telegram API call {method} aborted: missing token")
        return None

    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        logger.error(f"Telegram API error {method} (HTTP {e.code}): {err}")
    except Exception as e:
        logger.error(f"Telegram API exception {method}: {e}")
    return None


def send_interactive_proposal(
    job: Dict[str, Any],
    score_res: Dict[str, Any],
    draft: Dict[str, Any],
    chat_id: Optional[str] = None,
    state_mgr: Optional[StateManager] = None,
) -> bool:
    """
    Send an interactive proposal card to Telegram with Inline Keyboard Buttons
    allowing 1-click Approval, Viewing Cover Letter, or Rejection.
    Guarantees idempotence via alerted_at timestamp check.
    """
    # Suppress live unmocked Telegram calls during unit tests, test jobs or mock runs
    is_mocked = hasattr(urllib.request.urlopen, "mock_calls") or "unittest.mock" in str(type(urllib.request.urlopen)) or "unittest.mock" in str(type(telegram_api_call))
    if not is_mocked and (os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("UPWORK_TEST_MODE") == "1"):
        logger.debug("Suppressing live interactive proposal card during test/mock execution.")
        return True

    from .job_ledger import is_test_job
    if is_test_job(job.get("job_id", ""), job.get("title", "")):
        logger.info(f"Blocking interactive Telegram alert for test job {job.get('job_id')}")
        return True

    if job.get("alerted_at"):
        logger.info(f"Job {job.get('job_id')} already alerted at {job.get('alerted_at')}; skipping duplicate card.")
        return True

    _, default_chat_id = get_telegram_credentials()
    target_chat = chat_id or default_chat_id
    if not target_chat:
        return False

    jid = job.get("job_id", "").lstrip("~")
    title = (job.get("title") or "Untitled Job").replace("<", "&lt;").replace(">", "&gt;")
    score = score_res.get("score", 0.0)
    reasons = ", ".join(score_res.get("reasons", [])[:4])
    terms = draft.get("terms") or draft.get("proposed_terms") or {}
    job_url = job.get("url") or job.get("job_url") or f"https://www.upwork.com/jobs/~{jid}"

    b_type = terms.get("type", job.get("type", "fixed"))
    b_rate = terms.get("charged_amount") or terms.get("charge_rate") or terms.get("hourly_bid") or "TBD"
    boost = terms.get("boost_connects", 0)

    # Ensure draft is published to Notion Proposal Staging Desk
    notion_url = draft.get("notion_url")
    if not notion_url:
        try:
            from .notion_publisher import publish_staged_proposal
            ok_notion, pid, p_url = publish_staged_proposal(job, score_res)
            if ok_notion and p_url:
                draft["notion_page_id"] = pid
                draft["notion_url"] = p_url
                notion_url = p_url
                if state_mgr:
                    try:
                        state_mgr.save_jobs({job.get("job_id", ""): job})
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Failed to publish staged proposal to Notion for job {job.get('job_id')}: {e}")

    notion_note = f"\n📝 <b>Notion Desk:</b> <a href=\"{notion_url}\">Edit Draft in Notion</a>" if notion_url else ""
    text = (
        f"🎯 <b>Action Required: Upwork Proposal Staged</b>\n\n"
        f"<b>Title:</b> <a href=\"{job_url}\">{title}</a>\n"
        f"<b>Score:</b> <code>{score:.1f} / 100</code> (APPLY)\n"
        f"<b>Terms:</b> {b_type.capitalize()} <b>${b_rate}</b> (Boost: {boost} Connects)\n"
        f"<b>Matched Signals:</b> <i>{reasons}</i>{notion_note}\n\n"
        f"👇 <i>Review/edit in Notion or tap below to submit directly to Upwork:</i>"
    )

    # Inline Keyboard with callback data & direct Notion link
    keyboard = []
    if notion_url:
        keyboard.append([
            {"text": "📝 Edit Draft in Notion", "url": notion_url},
            {"text": "✅ Approve & Submit", "callback_data": f"approve:{jid}"},
        ])
        keyboard.append([
            {"text": "📖 View Draft", "callback_data": f"view:{jid}"},
            {"text": "❌ Skip / Reject", "callback_data": f"reject:{jid}"},
        ])
    else:
        keyboard.append([
            {"text": "✅ Approve & Submit", "callback_data": f"approve:{jid}"},
            {"text": "📖 View Draft", "callback_data": f"view:{jid}"},
        ])
        keyboard.append([
            {"text": "❌ Skip / Reject", "callback_data": f"reject:{jid}"},
        ])
    keyboard.append([
        {"text": "🌐 View on Upwork", "url": job_url},
    ])
    reply_markup = {"inline_keyboard": keyboard}

    res = telegram_api_call("sendMessage", {
        "chat_id": target_chat,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": reply_markup,
        "disable_web_page_preview": True,
    })

    if bool(res and res.get("ok")):
        now_iso = datetime.now(timezone.utc).isoformat()
        job["alerted_at"] = now_iso
        if state_mgr:
            try:
                state_mgr.save_jobs({job.get("job_id", ""): job})
            except Exception as e:
                logger.warning(f"Failed to persist alerted_at for job {job.get('job_id')}: {e}")
        return True
    return False


class TelegramBotListener:
    """Long-polling bot listener for interactive 1-click buttons and slash commands."""

    def __init__(self, mcp_client: UpworkMCPClient, state_mgr: StateManager):
        self.mcp = mcp_client
        self.state_mgr = state_mgr
        self.review_mgr = ReviewSubmitManager(mcp_client, state_mgr)
        self.last_update_id = 0
        self.running = False
        self.consecutive_409_count = 0

    def handle_callback_query(self, cb: Dict[str, Any]) -> None:
        """Handle inline button clicks (Approve, View, Reject)."""
        cb_id = cb.get("id")
        data = cb.get("data", "")
        message = cb.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        message_id = message.get("message_id")

        if ":" not in data:
            telegram_api_call("answerCallbackQuery", {"callback_query_id": cb_id})
            return

        action, jid = data.split(":", 1)
        full_jid = jid if jid.startswith("~") else f"~{jid}"
        jobs = self.state_mgr.load_jobs()
        job = jobs.get(jid) or jobs.get(full_jid)
        if not job:
            for k, v in jobs.items():
                if k.lstrip("~") == jid.lstrip("~") or v.get("id") == jid or v.get("job_id") == jid:
                    job = v
                    break

        if not job:
            telegram_api_call("answerCallbackQuery", {
                "callback_query_id": cb_id,
                "text": "Job record not found in state.",
                "show_alert": True,
            })
            return

        clean_jid = jid.lstrip("~")
        title = html.escape(sanitize_no_em_dash(job.get("title") or "Job"))
        job_url = job.get("url") or job.get("job_url") or f"https://www.upwork.com/jobs/~{clean_jid}"

        if action == "approve":
            telegram_api_call("answerCallbackQuery", {
                "callback_query_id": cb_id,
                "text": "Submitting proposal to Upwork...",
            })

            run_id = f"tg_{int(time.time())}"
            target_job_id = str(job.get("job_id") or clean_jid)

            # Step 0: Sync latest edits from Notion Proposal Staging Desk if available
            notion_pid = (job.get("draft") or {}).get("notion_page_id")
            if notion_pid:
                try:
                    from .notion_publisher import fetch_staged_proposal
                    staged_data = fetch_staged_proposal(notion_pid)
                    if staged_data:
                        if staged_data.get("cover_letter"):
                            job["draft"]["cover_letter"] = staged_data["cover_letter"]
                        if staged_data.get("answers"):
                            job["draft"]["answers"] = staged_data["answers"]
                        # Invalidate existing preview to force fresh regeneration with Aryan's Notion edits
                        job.pop("submission_preview", None)
                        self.state_mgr.save_jobs({job.get("job_id", target_job_id): job})
                        logger.info(f"Synchronized latest Notion edits for job {target_job_id}")
                except Exception as e:
                    logger.warning(f"Failed to fetch staged edits from Notion for job {target_job_id}: {e}")

            # Step 1: Prepare preview if needed
            preview_id = (job.get("submission_preview") or {}).get("preview_id")
            if not preview_id:
                prep = self.review_mgr.prepare_submission(target_job_id, run_id)
                if not prep.get("ok"):
                    err_msg = sanitize_no_em_dash(prep.get("message") or "Unknown error")
                    send_telegram_message(f"❌ Failed to prepare submission: {err_msg}")
                    if chat_id and message_id:
                        telegram_api_call("editMessageText", {
                            "chat_id": chat_id,
                            "message_id": message_id,
                            "text": (
                                f"⚠️ <b>Submission Preparation Failed</b>\n\n"
                                f"<b>Job:</b> <a href=\"{job_url}\">{title}</a>\n"
                                f"<b>Reason:</b> {html.escape(err_msg)}\n\n"
                                f"<i>Tap below to view Draft or open directly on Upwork:</i>"
                            ),
                            "parse_mode": "HTML",
                            "disable_web_page_preview": True,
                            "reply_markup": {
                                "inline_keyboard": [
                                    [
                                        {"text": "🔄 Retry Approve", "callback_data": f"approve:{clean_jid}"},
                                        {"text": "📖 View Draft", "callback_data": f"view:{clean_jid}"},
                                    ],
                                    [
                                        {"text": "🌐 Open on Upwork", "url": job_url},
                                    ],
                                ]
                            },
                        })
                    return
                preview_id = prep.get("preview_id")

            # Step 2: Confirm submission with explicit human approval
            conf = self.review_mgr.confirm_submission(
                job_id=target_job_id,
                preview_id=preview_id,
                human_confirmed=True,
                run_id=run_id,
            )

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M IST")
            if conf.get("ok"):
                spent = conf.get("connects_spent", 16)
                updated_text = (
                    f"✅ <b>PROPOSAL SUBMITTED ON UPWORK</b>\n\n"
                    f"<b>Job:</b> <a href=\"{job_url}\">{title}</a>\n"
                    f"<b>Submitted At:</b> {now_str}\n"
                    f"<b>Connects Spent:</b> {spent}\n"
                    f"<b>Status:</b> Live on Upwork (Approved by Aryan)\n\n"
                    f"<i>Submission confirmed via 1-click Telegram authorization.</i>"
                )
                if notion_pid:
                    try:
                        from .notion_publisher import update_proposal_status
                        update_proposal_status(notion_pid, "submitted", job.get("title", ""))
                    except Exception as e:
                        logger.warning(f"Failed to update Notion status to submitted: {e}")
            else:
                err_msg = html.escape(sanitize_no_em_dash(conf.get("message") or "Submission error"))
                updated_text = (
                    f"⚠️ <b>Submission Failed</b>\n\n"
                    f"<b>Job:</b> <a href=\"{job_url}\">{title}</a>\n"
                    f"<b>Error:</b> {err_msg}\n"
                    f"<i>Check console or open on Upwork.</i>"
                )

            # Update original message to remove buttons
            edit_res = telegram_api_call("editMessageText", {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": updated_text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            })
            if not edit_res and chat_id:
                telegram_api_call("sendMessage", {
                    "chat_id": chat_id,
                    "text": updated_text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                })

        elif action == "view":
            telegram_api_call("answerCallbackQuery", {
                "callback_query_id": cb_id,
                "text": "Displaying cover letter...",
            })
            draft = job.get("draft") or {}
            raw_cl = draft.get("cover_letter") or "No cover letter drafted."
            clean_cl = sanitize_no_em_dash(raw_cl)
            escaped_cl = html.escape(clean_cl)

            terms = draft.get("terms") or draft.get("proposed_terms") or {}
            b_type = str(terms.get("type", job.get("type", "hourly"))).capitalize()
            b_rate = terms.get("charged_amount") or terms.get("charge_rate") or terms.get("hourly_bid") or 65.0
            boost = terms.get("boost_connects", 0)
            notion_url = draft.get("notion_url")

            answers = draft.get("answers") or []
            ans_text = ""
            if answers:
                ans_lines = []
                for a in answers:
                    q_str = html.escape(sanitize_no_em_dash(a.get("question", "")))
                    a_str = html.escape(sanitize_no_em_dash(a.get("answer", "")))
                    ans_lines.append(f"• <i>{q_str}</i>\n  👉 {a_str}")
                ans_text = "\n\n<b>Screening Answers:</b>\n" + "\n".join(ans_lines)

            notion_header = f" | <a href=\"{notion_url}\">Edit in Notion</a>" if notion_url else ""
            preview_msg = (
                f"📝 <b>Cover Letter Preview</b>{notion_header}\n"
                f"<b>Job:</b> <a href=\"{job_url}\">{title}</a>\n"
                f"<b>Terms:</b> {html.escape(b_type)} <b>${b_rate}</b> (Boost: {boost} Connects)\n\n"
                f"<blockquote>{escaped_cl}</blockquote>{ans_text}\n\n"
                f"<i>Tap below to approve &amp; submit or edit on Notion:</i>"
            )
            view_keyboard = [
                [
                    {"text": "✅ Approve & Submit", "callback_data": f"approve:{clean_jid}"},
                    {"text": "❌ Skip / Reject", "callback_data": f"reject:{clean_jid}"},
                ],
            ]
            if notion_url:
                view_keyboard.append([{"text": "📝 Edit Draft in Notion", "url": notion_url}])
            view_keyboard.append([{"text": "🌐 View on Upwork", "url": job_url}])

            view_markup = {"inline_keyboard": view_keyboard}
            send_res = telegram_api_call("sendMessage", {
                "chat_id": chat_id,
                "text": preview_msg,
                "parse_mode": "HTML",
                "reply_markup": view_markup,
                "disable_web_page_preview": True,
            })
            if not send_res and chat_id:
                # Plain-text fallback so View Draft never fails silently
                plain_msg = f"Cover Letter Preview - {sanitize_no_em_dash(job.get('title', 'Job'))}\n\n{clean_cl}"
                telegram_api_call("sendMessage", {
                    "chat_id": chat_id,
                    "text": plain_msg[:4000],
                    "reply_markup": view_markup,
                })

        elif action == "reject":
            telegram_api_call("answerCallbackQuery", {
                "callback_query_id": cb_id,
                "text": "Lead rejected.",
            })
            notion_pid = (job.get("draft") or {}).get("notion_page_id")
            if notion_pid:
                try:
                    from .notion_publisher import update_proposal_status
                    update_proposal_status(notion_pid, "skipped", job.get("title", ""))
                except Exception as e:
                    logger.warning(f"Failed to update Notion status to skipped: {e}")

            self.review_mgr.reject_proposal(job["job_id"], reason="Rejected via Telegram 1-click button")
            updated_text = (
                f"❌ <b>PROPOSAL SKIPPED</b>\n\n"
                f"<b>Job:</b> {title}\n"
                f"<b>Decision:</b> Skipped / Rejected by Aryan on Telegram.\n"
                f"<i>Lead archived in state.</i>"
            )
            telegram_api_call("editMessageText", {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": updated_text,
                "parse_mode": "HTML",
            })

    def handle_message(self, msg: Dict[str, Any]) -> None:
        """Handle incoming text commands (/status, /queue, /hunt, /report, /sync)."""
        text = (msg.get("text") or "").strip()
        chat_id = msg.get("chat", {}).get("id")
        if not text.startswith("/"):
            return

        cmd = text.split()[0].lower()

        if cmd in ("/start", "/help"):
            help_text = (
                "🤖 <b>Aryan's Upwork Pipeline Control Bot</b>\n\n"
                "Available commands:\n"
                "• <b>/queue</b> - View pending proposals awaiting 1-click review\n"
                "• <b>/status</b> - Check engine status, Connects, and campaigns\n"
                "• <b>/hunt</b> - Trigger an immediate job discovery and vetting pass\n"
                "• <b>/report</b> - Send today's 4-part Market & Improvement Report\n"
                "• <b>/monthly</b> - Run 30-day market trend analysis & calibrate proposal rules\n"
                "• <b>/sync</b> - Synchronize living documents to Notion\n\n"
                "<i>You can approve or reject proposals with 1-tap inline buttons!</i>"
            )
            telegram_api_call("sendMessage", {"chat_id": chat_id, "text": help_text, "parse_mode": "HTML"})

        elif cmd == "/status":
            state = self.state_mgr.load_state()
            jobs = self.state_mgr.load_jobs()
            camps = self.state_mgr.load_campaigns()
            queue = self.review_mgr.get_review_queue()

            # Fetch live connects from Freelancer profile
            connects = state.get("connects_balance", 118)
            try:
                bal_res = self.mcp.call_tool("get_profile", "connects_balance", {}, run_id="status_check")
                if bal_res.get("ok"):
                    bal_data = bal_res.get("data", {}).get("balance", {})
                    if isinstance(bal_data, dict) and "connectsBalance" in bal_data:
                        connects = int(bal_data["connectsBalance"])
                        state["connects_balance"] = connects
                        self.state_mgr.save_state(state)
            except Exception as e:
                logger.debug(f"Live connects query note: {e}")

            status_text = (
                "⚡ <b>Upwork Pipeline Status</b>\n\n"
                "• <b>Target Account:</b> Aryan Pegwar (Freelancer / TALENT)\n"
                f"• <b>Live Connects Balance:</b> <b>{connects} Connects</b>\n"
                f"• <b>Pending Reviews:</b> {len(queue)}\n"
                f"• <b>Total Tracked Jobs:</b> {len(jobs)}\n"
                f"• <b>Active Campaigns:</b> {len(camps.get('campaigns', []))}\n"
                f"• <b>Kill Switch:</b> {'🚨 ACTIVE' if state.get('kill_switch') else '✅ Normal (Off)'}\n\n"
                f"📖 <a href=\"{NOTION_HUB_URL}\">View Notion Command Center</a>"
            )
            telegram_api_call("sendMessage", {"chat_id": chat_id, "text": status_text, "parse_mode": "HTML"})

        elif cmd == "/queue":
            queue = self.review_mgr.get_review_queue()
            if not queue:
                telegram_api_call("sendMessage", {
                    "chat_id": chat_id,
                    "text": "✅ <b>Review queue is clean!</b> No proposals currently waiting for review.",
                    "parse_mode": "HTML",
                })
            else:
                telegram_api_call("sendMessage", {
                    "chat_id": chat_id,
                    "text": f"📋 <b>Found {len(queue)} proposal(s) awaiting review:</b>",
                    "parse_mode": "HTML",
                })
                for job in queue:
                    score_res = {
                        "score": job.get("score", 75.0),
                        "reasons": job.get("reasons", ["high_fit"]),
                    }
                    send_interactive_proposal(job, score_res, job.get("draft", {}), chat_id=str(chat_id))

        elif cmd == "/hunt":
            telegram_api_call("sendMessage", {
                "chat_id": chat_id,
                "text": "🔎 <i>Running live marketplace hunt across active campaigns...</i>",
                "parse_mode": "HTML",
            })
            from .hourly_runner import run_single_pass
            try:
                summary = run_single_pass(self.state_mgr, self.mcp)
                staged = summary.get("staged_total", 0)
                msg = (
                    f"✅ <b>Hunt Pass Finished</b>\n\n"
                    f"• Candidates Discovered: {summary.get('discovered_total', 0)}\n"
                    f"• Vetted: {summary.get('vetted_total', 0)}\n"
                    f"• Staged for Review: <b>{staged}</b>\n\n"
                )
                if staged > 0:
                    msg += "Check the interactive approval cards sent above!"
                else:
                    msg += "No leads met the strict threshold (>=70) this pass."
                telegram_api_call("sendMessage", {"chat_id": chat_id, "text": msg, "parse_mode": "HTML"})
            except Exception as e:
                telegram_api_call("sendMessage", {"chat_id": chat_id, "text": f"❌ Hunt pass failed: {e}"})

        elif cmd == "/report":
            from .daily_report import DailyReportEngine
            rep_eng = DailyReportEngine(self.state_mgr.state_dir)
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            res = rep_eng.generate_daily_report(today_str)
            metrics = res.get("metrics", {})
            web_link = metrics.get("web_report_link", "http://localhost:8080/report")
            telegram_api_call("sendMessage", {
                "chat_id": chat_id,
                "text": f"✅ <b>Daily report delivered above!</b>\n\n🌐 <a href=\"{web_link}\">Open Live Web Dashboard on Railway</a>",
                "parse_mode": "HTML",
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "🌐 Open Web Dashboard", "url": web_link}],
                    ]
                }
            })

        elif cmd == "/monthly":
            telegram_api_call("sendMessage", {
                "chat_id": chat_id,
                "text": "⏳ <i>Analyzing 30-day market intelligence trends and calibrating proposal strategy...</i>",
                "parse_mode": "HTML",
            })
            try:
                from .monthly_strategy_engine import MonthlyStrategyEngine
                m_eng = MonthlyStrategyEngine(self.state_mgr.state_dir)
                m_res = m_eng.run_monthly_pass()
                strat = m_res.get("strategy", {})
                trends = m_res.get("trends", {})
                techs = ", ".join(trends.get("top_technologies", [])[:5]) or "AI Workflows & MCP"
                summary_msg = (
                    "📊 <b>Monthly Upwork Strategy Calibration Complete!</b>\n\n"
                    f"• 📈 <b>Top Stacks (30d):</b> {techs}\n"
                    f"• 💡 <b>Proof Priority:</b> {strat.get('recommended_proof_focus')}\n"
                    f"• ⚠️ <b>Key Risk Hook:</b> {strat.get('recommended_risk_focus')}\n"
                    f"• 📝 <b>Guide Updated:</b> <code>UPWORK_PROPOSAL_CRAFTING_GUIDE.md</code> (Rules intact)\n\n"
                    "<i>Proposal generation prompt has been refreshed with current market signals.</i>"
                )
                telegram_api_call("sendMessage", {"chat_id": chat_id, "text": summary_msg, "parse_mode": "HTML"})
            except Exception as e:
                telegram_api_call("sendMessage", {"chat_id": chat_id, "text": f"❌ Monthly strategy pass failed: {e}"})

        elif cmd == "/sync":
            from .notion_publisher import NotionPublisher
            pub = NotionPublisher()
            res = pub.sync_all()
            sync_msg = (
                "📚 <b>Notion Live Sync Finished</b>\n\n"
                f"• Daily Report: {'✅ Synced' if res.get('daily_report') else '❌'}\n"
                f"• Market Intel: {'✅ Synced' if res.get('market_intel') else '❌'}\n"
                f"• Master Hub: {'✅ Synced' if res.get('master_hub') else '❌'}\n\n"
                f"📖 <a href=\"{NOTION_HUB_URL}\">Open Notion Command Center</a>"
            )
            telegram_api_call("sendMessage", {"chat_id": chat_id, "text": sync_msg, "parse_mode": "HTML"})

    def process_update(self, update: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single Telegram update (callback query or message)."""
        if "callback_query" in update:
            self.handle_callback_query(update["callback_query"])
            return {"type": "callback_query", "handled": True}
        elif "message" in update:
            self.handle_message(update["message"])
            return {"type": "message", "handled": True}
        return {"type": "unknown", "handled": False}

    def poll_updates(self, timeout: int = 10) -> None:
        """Single poll pass for Telegram updates."""
        try:
            state = self.state_mgr.load_state()
            inbound_mode = state.get("inbound_mode", "polling:railway")
            from .tier import current_tier
            this_tier = current_tier().lower()
            if inbound_mode == "webhook":
                logger.debug("Inbound mode is 'webhook'; skipping polling to prevent conflicts.")
                return
            if inbound_mode.startswith("polling:") and inbound_mode != f"polling:{this_tier}" and inbound_mode != "polling":
                logger.debug(f"Inbound mode is {inbound_mode}; current tier is {this_tier}; skipping polling.")
                return
        except Exception:
            pass

        token, _ = get_telegram_credentials()
        if not token:
            return

        url = f"https://api.telegram.org/bot{token}/getUpdates?offset={self.last_update_id + 1}&timeout={timeout}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout + 5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if not data.get("ok"):
                    return
                if self.consecutive_409_count > 0:
                    logger.info("Telegram polling recovered successfully after conflict.")
                    try:
                        from .alerts import AlertManager
                        alert_mgr = AlertManager(backend=getattr(self.state_mgr, "backend", None))
                        alert_mgr.resolve_alert("W9", "Telegram polling connection restored successfully.")
                    except Exception:
                        pass
                    self.consecutive_409_count = 0
                for update in data.get("result", []):
                    self.last_update_id = max(self.last_update_id, update.get("update_id", 0))
                    self.process_update(update)
        except urllib.error.HTTPError as e:
            if e.code == 409:
                self.consecutive_409_count += 1
                err_detail = "webhook or another poller active"
                try:
                    err_body = e.read().decode("utf-8", errors="replace")
                    err_json = json.loads(err_body)
                    desc = err_json.get("description", "")
                    if desc:
                        err_detail = desc
                except Exception:
                    pass
                logger.warning(
                    f"Telegram polling returned 409 Conflict (streak {self.consecutive_409_count}): {err_detail}"
                )
                # Only raise alert if conflict persists across multiple cycles (>= 3 consecutive polls),
                # to avoid triggering false alarms on brief momentary collisions (e.g. from a CLI check or link-telegram).
                if self.consecutive_409_count >= 3:
                    try:
                        from .alerts import AlertManager
                        from .tier import current_tier
                        alert_mgr = AlertManager(backend=getattr(self.state_mgr, "backend", None))
                        alert_mgr.raise_alert(
                            "W9",
                            f"Telegram polling 409 Conflict ({err_detail})",
                            severity="WARNING",
                            tier=current_tier(),
                        )
                    except Exception:
                        pass
            else:
                logger.debug(f"Poll updates HTTP error {e.code}: {e}")
        except Exception as e:
            logger.debug(f"Poll updates exception: {e}")

    def run_forever(self, check_interval: int = 2) -> None:
        """Run blocking polling loop."""
        self.running = True
        logger.info("Telegram Bot listener started.")
        while self.running:
            try:
                self.poll_updates(timeout=5)
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                time.sleep(check_interval)
            time.sleep(0.5)

    def stop(self) -> None:
        self.running = False


def process_telegram_update(
    update: Dict[str, Any],
    mcp_client: Optional[UpworkMCPClient] = None,
    state_mgr: Optional[StateManager] = None,
) -> Dict[str, Any]:
    """
    Module-level entrypoint for processing webhook updates (e.g. from Vercel /api/telegram).
    Loads latest state, handles callback queries or commands, and returns result.
    """
    from .state_backend import get_default_backend
    backend = get_default_backend()
    if state_mgr is None:
        state_mgr = StateManager(STATE_DIR, backend=backend)
        try:
            state_mgr.pull()
        except Exception:
            pass

    if mcp_client is None:
        from .upwork_oauth import UpworkOAuthManager
        oauth = UpworkOAuthManager(backend=backend)
        token = oauth.get_valid_access_token(lease_held=True)
        mcp_client = UpworkMCPClient(auth_token=token, oauth_manager=oauth, lease_held=True)

    listener = TelegramBotListener(mcp_client=mcp_client, state_mgr=state_mgr)
    res = listener.process_update(update)
    if state_mgr and state_mgr.backend:
        try:
            state_mgr.push()
        except Exception as e:
            logger.debug(f"State backend push note: {e}")
    return res
