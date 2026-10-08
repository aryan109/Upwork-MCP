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

    def prepare_submission(self, job_id: str, run_id: str) -> Dict[str, Any]:
        """
        Step 1 of Two-Step Confirmation:
        Calls manage_proposals create to generate a preview.
        Does NOT submit.
        """
        state = self.state_mgr.load_state()
        if state.get("kill_switch", False):
            return {"ok": False, "message": "Submission blocked: kill switch is active"}

        jobs = self.state_mgr.load_jobs()
        if job_id not in jobs:
            return {"ok": False, "message": f"Job {job_id} not found in state"}

        job = jobs[job_id]

        draft = job.get("draft")
        if not draft:
            return {"ok": False, "message": f"No draft exists for job {job_id}"}

        terms = draft.get("terms", {})
        params = {
            "job_reference": job_id,
            "cover_letter": draft.get("cover_letter"),
            "charged_amount": terms.get("charged_amount") or terms.get("hourly_bid"),
            "boost_connects": terms.get("boost_connects", 0),
            "answers": [a.get("answer") for a in draft.get("answers", [])],
        }

        # Step 1: create preview
        res = self.mcp.call_tool("manage_proposals", "create", params, run_id=run_id, state=state)
        if not res.get("ok"):
            return {"ok": False, "message": f"Failed to create preview: {res.get('message')}"}

        preview_id = res.get("data", {}).get("preview_id")
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
            "job_id": job_id,
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
        if job_id not in jobs:
            return {"ok": False, "message": f"Job {job_id} not found"}

        job = jobs[job_id]
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

        data = res.get("data", {})
        proposal_id = data.get("proposal_id", f"prop_{job_id}")
        connects_spent = data.get("connects_spent", 16)

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

        return {
            "ok": True,
            "proposal_id": proposal_id,
            "connects_spent": connects_spent,
            "status": "submitted",
        }

    def reject_draft(self, job_id: str, reason: str) -> Dict[str, Any]:
        """Mark a drafted proposal as rejected by Aryan."""
        jobs = self.state_mgr.load_jobs()
        if job_id not in jobs:
            return {"ok": False, "message": f"Job {job_id} not found"}

        job = jobs[job_id]
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
            self.ledger.add_to_rejected(job_id, reason=reason, title=job.get("title", ""))
        except Exception as e:
            logger.warning(f"Ledger blacklist rejection note: {e}")

        # Record negative client pattern in continuous learner
        try:
            self.learner.record_rejection(job, reason=reason)
        except Exception as e:
            logger.debug(f"Learner rejection note: {e}")

        return {"ok": True, "job_id": job_id, "status": "rejected_by_aryan"}

    def reject_proposal(self, job_id: str, reason: str = "Rejected") -> Dict[str, Any]:
        """Alias for reject_draft."""
        return self.reject_draft(job_id, reason)
