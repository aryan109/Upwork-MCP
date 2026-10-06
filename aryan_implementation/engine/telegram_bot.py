"""
Interactive Telegram Bot Engine for Aryan Upwork Acquisition Pipeline.
Provides real-time 1-click proposal approvals, status checks, and command execution:
- [✅ Approve & Submit]: Confirms proposal preview and submits to Upwork via MCP.
- [📖 View Cover Letter]: Displays the full 4-part cover letter and screening answers.
- [❌ Skip / Reject]: Rejects the lead and archives it in state.
- Commands: /status, /queue, /hunt, /report, /sync, /help
"""
from __future__ import annotations

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
) -> bool:
    """
    Send an interactive proposal card to Telegram with Inline Keyboard Buttons
    allowing 1-click Approval, Viewing Cover Letter, or Rejection.
    """
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

    text = (
        f"🎯 <b>Action Required: Upwork Proposal Staged</b>\n\n"
        f"<b>Title:</b> <a href=\"{job_url}\">{title}</a>\n"
        f"<b>Score:</b> <code>{score:.1f} / 100</code> (APPLY)\n"
        f"<b>Terms:</b> {b_type.capitalize()} <b>${b_rate}</b> (Boost: {boost} Connects)\n"
        f"<b>Matched Signals:</b> <i>{reasons}</i>\n\n"
        f"👇 <i>Review draft or tap below to submit directly to Upwork:</i>"
    )

    # Inline Keyboard with callback data
    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "✅ Approve & Submit", "callback_data": f"approve:{jid}"},
                {"text": "📖 View Draft", "callback_data": f"view:{jid}"},
            ],
            [
                {"text": "❌ Skip / Reject", "callback_data": f"reject:{jid}"},
                {"text": "🌐 View on Upwork", "url": job_url},
            ],
        ]
    }

    res = telegram_api_call("sendMessage", {
        "chat_id": target_chat,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": reply_markup,
        "disable_web_page_preview": True,
    })
    return bool(res and res.get("ok"))


class TelegramBotListener:
    """Long-polling bot listener for interactive 1-click buttons and slash commands."""

    def __init__(self, mcp_client: UpworkMCPClient, state_mgr: StateManager):
        self.mcp = mcp_client
        self.state_mgr = state_mgr
        self.review_mgr = ReviewSubmitManager(mcp_client, state_mgr)
        self.last_update_id = 0
        self.running = False

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

        title = (job.get("title") or "Job").replace("<", "&lt;").replace(">", "&gt;")

        if action == "approve":
            telegram_api_call("answerCallbackQuery", {
                "callback_query_id": cb_id,
                "text": "Submitting proposal to Upwork...",
            })

            run_id = f"tg_{int(time.time())}"
            # Step 1: Prepare preview if needed
            preview_id = job.get("submission_preview", {}).get("preview_id")
            if not preview_id:
                prep = self.review_mgr.prepare_submission(job["job_id"], run_id)
                if not prep.get("ok"):
                    send_telegram_message(f"❌ Failed to prepare submission: {prep.get('message')}")
                    return
                preview_id = prep.get("preview_id")

            # Step 2: Confirm submission with explicit human approval
            conf = self.review_mgr.confirm_submission(
                job_id=job["job_id"],
                preview_id=preview_id,
                human_confirmed=True,
                run_id=run_id,
            )

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M IST")
            if conf.get("ok"):
                spent = conf.get("connects_spent", 16)
                updated_text = (
                    f"✅ <b>PROPOSAL SUBMITTED ON UPWORK</b>\n\n"
                    f"<b>Job:</b> {title}\n"
                    f"<b>Submitted At:</b> {now_str}\n"
                    f"<b>Connects Spent:</b> {spent}\n"
                    f"<b>Status:</b> Live on Upwork (Approved by Aryan)\n\n"
                    f"<i>Submission confirmed via 1-click Telegram authorization.</i>"
                )
            else:
                updated_text = (
                    f"⚠️ <b>Submission Failed</b>\n\n"
                    f"<b>Job:</b> {title}\n"
                    f"<b>Error:</b> {conf.get('message')}\n"
                    f"<i>Check console or retry via CLI.</i>"
                )

            # Update original message to remove buttons
            telegram_api_call("editMessageText", {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": updated_text,
                "parse_mode": "HTML",
            })

        elif action == "view":
            telegram_api_call("answerCallbackQuery", {
                "callback_query_id": cb_id,
                "text": "Displaying cover letter...",
            })
            draft = job.get("draft", {})
            cl = draft.get("cover_letter", "No cover letter drafted.")
            answers = draft.get("answers", [])
            ans_text = ""
            if answers:
                ans_text = "\n\n<b>Screening Answers:</b>\n" + "\n".join(
                    f"• <i>{a.get('question')}</i>\n  👉 {a.get('answer')}" for a in answers
                )

            preview_msg = (
                f"📝 <b>Cover Letter Preview</b>\n"
                f"<b>Job:</b> {title}\n\n"
                f"<blockquote>{cl}</blockquote>{ans_text}\n\n"
                f"<i>Use the original message above to approve or reject.</i>"
            )
            telegram_api_call("sendMessage", {
                "chat_id": chat_id,
                "text": preview_msg,
                "parse_mode": "HTML",
            })

        elif action == "reject":
            telegram_api_call("answerCallbackQuery", {
                "callback_query_id": cb_id,
                "text": "Lead rejected.",
            })
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
                "• <b>/sync</b> - Synchronize living documents to Notion\n\n"
                "<i>You can approve or reject proposals with 1-tap inline buttons!</i>"
            )
            telegram_api_call("sendMessage", {"chat_id": chat_id, "text": help_text, "parse_mode": "HTML"})

        elif cmd == "/status":
            state = self.state_mgr.load_state()
            jobs = self.state_mgr.load_jobs()
            camps = self.state_mgr.load_campaigns()
            queue = self.review_mgr.get_review_queue()

            connects = state.get("ledger", {}).get("available_connects", 110)
            status_text = (
                "⚡ <b>Upwork Pipeline Status</b>\n\n"
                f"• <b>Available Connects:</b> {connects}\n"
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
            telegram_api_call("sendMessage", {
                "chat_id": chat_id,
                "text": "✅ <i>Daily report generated and delivered above!</i>",
                "parse_mode": "HTML",
            })

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

    def poll_updates(self, timeout: int = 10) -> None:
        """Single poll pass for Telegram updates."""
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
                for update in data.get("result", []):
                    self.last_update_id = max(self.last_update_id, update.get("update_id", 0))
                    if "callback_query" in update:
                        self.handle_callback_query(update["callback_query"])
                    elif "message" in update:
                        self.handle_message(update["message"])
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
