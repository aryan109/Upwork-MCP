"""
End-to-end integration and safety tests for Aryan Upwork MCP Acquisition Engine.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from aryan_implementation.engine.state_manager import StateManager
from aryan_implementation.engine.mcp_client import UpworkMCPClient
from aryan_implementation.engine.hunt import JobHunter
from aryan_implementation.engine.vet import check_disqualifiers, score_job
from aryan_implementation.engine.draft import ProposalDrafter
from aryan_implementation.engine.review_submit import ReviewSubmitManager
from aryan_implementation.engine.rebake import RebakeEngine
from aryan_implementation.engine.campaign_editor import CampaignEditor
from aryan_implementation.engine.logger import log_event, redact_data


def test_redact_sensitive_credentials() -> None:
    payload = {
        "access_token": "secret_oauth_token_123",
        "user": "aryan",
        "nested": {"api_key": "sk-123456", "note": "public note"},
    }
    redacted = redact_data(payload)
    assert redacted["access_token"] == "[REDACTED]"
    assert redacted["nested"]["api_key"] == "[REDACTED]"
    assert redacted["user"] == "aryan"
    assert redacted["nested"]["note"] == "public note"


def test_proposal_draft_and_self_check() -> None:
    drafter = ProposalDrafter()
    sample_job = {
        "title": "Claude MCP Server Developer",
        "description": "Connect Claude Code to custom internal database via MCP. Need fully automated workflows.",
        "type": "fixed",
        "budget_fixed": 800,
        "screening_questions": ["What is your experience with Claude?"],
    }
    score_data = {"score": 85.0, "rung_suggested": "sprint"}
    draft = drafter.generate_full_draft(sample_job, score_data)

    assert "cover_letter" in draft
    assert "answers" in draft
    assert len(draft["answers"]) == 1
    self_check = draft["self_check"]

    assert self_check["passed"] is True
    assert self_check["word_count"] >= 110
    assert self_check["checks"]["no_exclamation"] is True
    assert self_check["checks"]["no_em_dash"] is True
    assert self_check["checks"]["signed_aryan"] is True


def test_submission_safety_two_step_confirm(tmp_path: Path) -> None:
    # Use isolated temp state dir
    state_mgr = StateManager(tmp_path)
    state_mgr.init_state_directory()

    mcp = UpworkMCPClient(mock_mode=True)
    rev_mgr = ReviewSubmitManager(mcp, state_mgr)

    job_id = "~01test_submission_job"
    jobs = {
        job_id: {
            "job_id": job_id,
            "title": "AI Automation Specialist",
            "type": "fixed",
            "budget_fixed": 599,
            "status": "drafted",
            "draft": {
                "cover_letter": "I reviewed your requirements... Aryan",
                "terms": {"charged_amount": 599, "boost_connects": 6},
                "answers": [],
            },
        }
    }
    state_mgr.save_jobs(jobs)

    # Step 1: Prepare preview (does NOT submit)
    prep_res = rev_mgr.prepare_submission(job_id, run_id="test_run_1")
    assert prep_res["ok"] is True
    assert "preview_id" in prep_res
    preview_id = prep_res["preview_id"]

    # Verify job status changed to in_review, NOT submitted
    saved_jobs = state_mgr.load_jobs()
    assert saved_jobs[job_id]["status"] == "in_review"

    # Step 2 without human confirmation MUST fail
    failed_submit = rev_mgr.confirm_submission(
        job_id=job_id,
        preview_id=preview_id,
        human_confirmed=False,
        run_id="test_run_1",
    )
    assert failed_submit["ok"] is False
    assert "Human confirmation is required" in failed_submit["message"]

    # Step 2 with human confirmation succeeds
    success_submit = rev_mgr.confirm_submission(
        job_id=job_id,
        preview_id=preview_id,
        human_confirmed=True,
        run_id="test_run_1",
    )
    assert success_submit["ok"] is True
    assert success_submit["status"] == "submitted"
    assert success_submit["connects_spent"] > 0

    saved_jobs_after = state_mgr.load_jobs()
    assert saved_jobs_after[job_id]["status"] == "submitted"


def test_kill_switch_blocks_operations(tmp_path: Path) -> None:
    state_mgr = StateManager(tmp_path)
    state_mgr.init_state_directory()
    mcp = UpworkMCPClient(mock_mode=True)
    rev_mgr = ReviewSubmitManager(mcp, state_mgr)

    # Enable kill switch
    state_mgr.toggle_kill_switch(True, reason="Unit test emergency block")
    assert state_mgr.load_state()["kill_switch"] is True

    # Prepare submission should be blocked
    res = rev_mgr.prepare_submission("~01any_job", run_id="test_run")
    assert res["ok"] is False
    assert "kill switch is active" in res["message"]


def test_rebake_ledger_reconciliation(tmp_path: Path) -> None:
    state_mgr = StateManager(tmp_path)
    state_mgr.init_state_directory()

    mcp = UpworkMCPClient(mock_mode=True)
    # Set mock balance to 80 (delta > 2 from initial 110)
    mcp.set_mock_data("get_profile.connects_balance", {"balance": 80})

    rebake = RebakeEngine(mcp, state_mgr)
    res = rebake.run_rebake(run_id="rebake_test_run")

    assert res["actual_balance"] == 80
    assert "DIGEST" in res["digest"]

    # Ledger drift incident should be recorded
    state = state_mgr.load_state()
    incidents = state.get("incidents", [])
    assert any(i.get("type") == "ledger" for i in incidents)


def test_campaign_editor_versioned_backup(tmp_path: Path) -> None:
    state_mgr = StateManager(tmp_path)
    state_mgr.init_state_directory()

    editor = CampaignEditor(state_mgr)
    update_res = editor.update_campaign(
        campaign_id="claude-implementation",
        updates={"score_threshold": 75},
        changelog="Raised threshold to 75 for quality test",
    )

    assert update_res["ok"] is True
    assert Path(update_res["backup_file"]).exists()

    camps = state_mgr.load_campaigns()
    target = next(c for c in camps["campaigns"] if c["id"] == "claude-implementation")
    assert target["score_threshold"] == 75
