"""
Human-in-the-loop review queue and proposal submission safety wrapper.
Enforces the mandatory two-step confirmation before any live proposal is submitted.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .mcp_client import UpworkMCPClient
from .state_manager import StateManager

logger = logging.getLogger("upwork_engine")


from .ai_client_learner import ClientLearningEngine
from .job_ledger import JobLedger, is_test_job


class ReviewSubmitManager:
    """Manages proposal review queues and human-confirmed submissions."""

    def __init__(self, mcp_client: UpworkMCPClient, state_mgr: StateManager):
        self.mcp = mcp_client
        self.state_mgr = state_mgr
        self.learner = ClientLearningEngine(state_mgr.state_dir)
        self.ledger = JobLedger(state_mgr.state_dir)

    def get_review_queue(self) -> List[Dict[str, Any]]:
        """Return all jobs currently awaiting human review."""
        jobs = self.state_mgr.load_jobs()
        queue = []
        for jid, job in jobs.items():
            jtitle = job.get("title", "")
            if is_test_job(jid, jtitle):
                continue
            if self.ledger.is_blacklisted(jid):
                continue
            if job.get("status") in ("drafted", "in_review", "preview_ready"):
                queue.append(job)
        # Sort by score descending
        queue.sort(key=lambda x: x.get("score", 0), reverse=True)
        return queue

    def format_review_item(self, job: Dict[str, Any]) -> str:
        """Format a single review item for human inspection."""
        jid = job.get("job_id", "")
        title = job.get("title", "")
        url = job.get("url") or job.get("job_url") or f"https://www.upwork.com/jobs/~{jid.lstrip('~')}"
        score = job.get("score", 0)
        reasons = ", ".join(job.get("reasons", [])[:4])
        draft = job.get("draft", {})
        terms = draft.get("terms", {})
        terms_str = f"Type: {terms.get('type')}, Charged: {terms.get('charged_amount') or terms.get('hourly_bid')}, Boost: {terms.get('boost_connects', 0)}"
        self_check = draft.get("self_check", {})
        passed = self_check.get("passed", False)
        word_count = self_check.get("word_count", 0)

        lines = [
            f"=== [REVIEW QUEUE] Job: {title} ===",
            f"ID: {jid} | Link: {url}",
            f"Score: {score} | Reasons: {reasons}",
            f"Proposed Terms: {terms_str}",
            f"Self-Check: {'PASSED' if passed else 'FAILED'} ({word_count} words)",
            "--- COVER LETTER ---",
            draft.get("cover_letter", "").strip(),
            "--------------------",
        ]
        answers = draft.get("answers", [])
        if answers:
            lines.append("--- SCREENING ANSWERS ---")
            for ans in answers:
                lines.append(f"Q: {ans.get('question')}")
                lines.append(f"A: {ans.get('answer')}")
            lines.append("-------------------------")

        return "\n".join(lines)

    def _resolve_job_key(self, jobs: Dict[str, Dict[str, Any]], job_id: str) -> Optional[str]:
        if job_id in jobs:
            return job_id
        clean = str(job_id).lstrip("~")
        if clean in jobs:
            return clean
        tilde = f"~{clean}"
        if tilde in jobs:
            return tilde
        for k, v in jobs.items():
            if str(k).lstrip("~") == clean or str(v.get("job_id", "")).lstrip("~") == clean:
                return k
        return None

    def prepare_submission(self, job_id: str, run_id: str) -> Dict[str, Any]:
        """
        Step 1 of Two-Step Confirmation:
        Calls manage_proposals create to generate a preview.
        Does NOT submit.
        """
        from .draft import sanitize_no_em_dash

        state = self.state_mgr.load_state()
        if state.get("kill_switch", False):
            return {"ok": False, "message": "Submission blocked: kill switch is active"}

        jobs = self.state_mgr.load_jobs()
        resolved_key = self._resolve_job_key(jobs, job_id)
        if not resolved_key:
            return {"ok": False, "message": f"Job {job_id} not found in state"}

        job = jobs[resolved_key]

        draft = job.get("draft")
        if not draft:
            return {"ok": False, "message": f"No draft exists for job {job_id}"}

        # Sync latest edits from Notion Proposal Staging Desk if available
        notion_pid = draft.get("notion_page_id")
        if notion_pid:
            try:
                from .notion_publisher import fetch_staged_proposal
                staged = fetch_staged_proposal(notion_pid)
                if staged:
                    if staged.get("cover_letter"):
                        draft["cover_letter"] = staged["cover_letter"]
                    if staged.get("answers"):
                        draft["answers"] = staged["answers"]
            except Exception as e:
                logger.debug(f"Notion pre-fetch in prepare_submission note: {e}")

        terms = draft.get("terms", {})
        cover_letter = sanitize_no_em_dash(draft.get("cover_letter", ""))
        draft["cover_letter"] = cover_letter

        raw_answers = draft.get("answers", []) or []
        sanitized_answers = [
            {
                "question": sanitize_no_em_dash(a.get("question", "")),
                "answer": sanitize_no_em_dash(a.get("answer", "")),
            }
            for a in raw_answers
            if isinstance(a, dict) and a.get("answer")
        ]
        draft["answers"] = sanitized_answers

        charged_raw = terms.get("charged_amount") or terms.get("hourly_bid") or 65.0
        try:
            charged_amount = float(charged_raw)
        except Exception:
            charged_amount = 65.0

        boost_val = int(terms.get("boost_connects", 0) or 0)

        if self.mcp.mock_mode:
            params: Dict[str, Any] = {
                "job_reference": job_id,
                "cover_letter": cover_letter,
                "charged_amount": charged_amount,
                "boost_connects": boost_val,
                "answers": [a.get("answer") for a in sanitized_answers],
            }
        else:
            # Mandatory Upwork MCP pre-check guard before manage_proposals.create
            try:
                self.mcp.call_tool("list_freelancer_proposals", "invitations", {}, run_id=run_id, state=state)
                self.mcp.call_tool("list_freelancer_proposals", "list", {}, run_id=run_id, state=state)
            except Exception as e:
                logger.debug(f"Pre-check guard note before manage_proposals.create: {e}")

            numeric_ref = str(job.get("job_id") or job_id).lstrip("~")
            params = {
                "job_reference": numeric_ref,
                "cover_letter": cover_letter,
                "charged_amount": charged_amount,
            }
            if boost_val > 0:
                params["boost_connects"] = boost_val
            if sanitized_answers:
                params["answers"] = sanitized_answers
            job_type = str(terms.get("type") or job.get("type") or "").lower()
            if "fixed" in job_type and job_type != "fixed_alternative":
                params["payment_mode"] = "by_project"
                params["estimated_duration"] = "1_to_3_months"

        # Step 1: create preview
        res = self.mcp.call_tool("manage_proposals", "create", params, run_id=run_id, state=state)
        if not res.get("ok") and not self.mcp.mock_mode and "boost_connects" in params:
            # Retry without boost_connects if boost bidding is unavailable or below floor
            retry_params = {k: v for k, v in params.items() if k != "boost_connects"}
            logger.info(f"Retrying manage_proposals.create for {job_id} without boost_connects...")
            res = self.mcp.call_tool("manage_proposals", "create", retry_params, run_id=run_id, state=state)

        if not res.get("ok"):
            return {"ok": False, "message": f"Failed to create preview: {res.get('message')}"}

        res_data = res.get("data", {}) if isinstance(res.get("data"), dict) else {}
        preview_id = (
            res_data.get("preview_id")
            or (res_data.get("preview") or {}).get("preview_id")
            or res_data.get("draft_id")
        )
        job["status"] = "in_review"
        job["submission_preview"] = {
            "preview_id": preview_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "terms": terms,
        }
        self.state_mgr.save_jobs(jobs)

        return {
            "ok": True,
            "preview_id": preview_id,
            "job_id": resolved_key,
            "terms": terms,
            "action_required": "Human must review preview and explicitly confirm submission",
        }

    def confirm_submission(
        self,
        job_id: str,
        preview_id: str,
        human_confirmed: bool,
        run_id: str,
    ) -> Dict[str, Any]:
        """
        Step 2 of Two-Step Confirmation:
        Executes confirm_preview ONLY if human_confirmed is True.
        """
        if not human_confirmed:
            return {
                "ok": False,
                "message": "Submission aborted: Human confirmation is required per rule NN1",
            }

        jobs = self.state_mgr.load_jobs()
        resolved_key = self._resolve_job_key(jobs, job_id)
        if not resolved_key:
            return {"ok": False, "message": f"Job {job_id} not found"}

        job = jobs[resolved_key]
        state = self.state_mgr.load_state()

        if state.get("kill_switch", False):
            return {"ok": False, "message": "Submission blocked: kill switch is active"}

        params = {"preview_id": preview_id}
        res = self.mcp.call_tool("manage_proposals", "confirm_preview", params, run_id=run_id, state=state)

        if not res.get("ok"):
            job["status"] = "error"
            job["error"] = res.get("message")
            self.state_mgr.save_jobs(jobs)
            return {"ok": False, "message": f"Failed to confirm submission: {res.get('message')}"}

        data = res.get("data", {}) if isinstance(res.get("data"), dict) else {}
        proposal_id = (
            data.get("proposal_id")
            or (data.get("proposal") or {}).get("id")
            or f"prop_{resolved_key}"
        )
        connects_spent = int(data.get("connects_spent") or data.get("connectsSpent") or 16)

        now_iso = datetime.now(timezone.utc).isoformat()
        job["status"] = "submitted"
        job["submission"] = {
            "proposal_id": proposal_id,
            "submitted_at": now_iso,
            "connects_spent": connects_spent,
            "boost": job.get("draft", {}).get("terms", {}).get("boost_connects", 0),
        }
        self.state_mgr.save_jobs(jobs)

        # Update state counters
        camp = job.get("campaign", "claude-implementation")
        state["applies_today"] = state.get("applies_today", 0) + 1
        applies_camp = state.setdefault("applies_today_by_campaign", {})
        applies_camp[camp] = applies_camp.get(camp, 0) + 1
        state["connects_balance"] = max(0, state.get("connects_balance", 110) - connects_spent)
        state["connects_spent_month"] = state.get("connects_spent_month", 0) + connects_spent
        self.state_mgr.save_state(state)

        # Record positive client pattern in continuous learner
        try:
            self.learner.record_approval(job)
        except Exception as e:
            logger.debug(f"Learner approval note: {e}")

        # Update ledger
        try:
            self.ledger.record_job(job, status="submitted", decision="APPLY")
        except Exception as e:
            logger.debug(f"Ledger record approval note: {e}")

        # Update Notion proposal status if staged on Notion
        notion_pid = job.get("draft", {}).get("notion_page_id")
        if notion_pid:
            try:
                from .notion_publisher import update_proposal_status
                update_proposal_status(notion_pid, "submitted", job.get("title", ""))
            except Exception as e:
                logger.debug(f"Notion status update in confirm_submission note: {e}")

        return {
            "ok": True,
            "proposal_id": proposal_id,
            "connects_spent": connects_spent,
            "status": "submitted",
        }

    def reject_draft(self, job_id: str, reason: str) -> Dict[str, Any]:
        """Mark a drafted proposal as rejected by Aryan."""
        jobs = self.state_mgr.load_jobs()
        resolved_key = self._resolve_job_key(jobs, job_id)
        if not resolved_key:
            return {"ok": False, "message": f"Job {job_id} not found"}

        job = jobs[resolved_key]
        job["status"] = "rejected_by_aryan"
        job["review"] = {
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "outcome": "rejected",
            "reject_reason": reason,
        }
        self.state_mgr.save_jobs(jobs)

        # Permanently blacklist job in JobLedger so it NEVER reappears
        try:
            self.ledger.record_job(job, status="rejected_by_aryan", decision="SKIP", rejection_reason=reason)
            self.ledger.add_to_rejected(resolved_key, reason=reason, title=job.get("title", ""))
        except Exception as e:
            logger.warning(f"Ledger blacklist rejection note: {e}")

        # Update Notion proposal status if staged on Notion
        notion_pid = job.get("draft", {}).get("notion_page_id")
        if notion_pid:
            try:
                from .notion_publisher import update_proposal_status
                update_proposal_status(notion_pid, "skipped", job.get("title", ""))
            except Exception as e:
                logger.debug(f"Notion status update in reject_draft note: {e}")

        # Record negative client pattern in continuous learner
        try:
            self.learner.record_rejection(job, reason=reason)
        except Exception as e:
            logger.debug(f"Learner rejection note: {e}")

        return {"ok": True, "job_id": job_id, "status": "rejected_by_aryan"}

    def reject_proposal(self, job_id: str, reason: str = "Rejected") -> Dict[str, Any]:
        """Alias for reject_draft."""
        return self.reject_draft(job_id, reason)
