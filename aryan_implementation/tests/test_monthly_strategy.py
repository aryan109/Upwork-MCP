"""
Unit tests for the Monthly Strategy Engine and dynamic Proposal Guide loader.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aryan_implementation.engine.draft import ProposalDrafter
from aryan_implementation.engine.monthly_strategy_engine import MonthlyStrategyEngine


def test_load_system_prompt_from_guide():
    """Verify that ProposalDrafter loads the master system prompt dynamically from Markdown."""
    prompt = ProposalDrafter.load_system_prompt_from_guide()
    assert isinstance(prompt, str)
    assert len(prompt) > 100
    assert "Aryan" in prompt
    assert "130-190 words" in prompt or "130 and 190 words" in prompt


def test_analyze_30day_market_trends(tmp_path):
    """Verify 30-day market trend aggregation from state records."""
    engine = MonthlyStrategyEngine(state_dir=tmp_path)
    trends = engine.analyze_30day_market_trends(days=30)
    assert "top_technologies" in trends
    assert "top_archetypes" in trends
    assert "pricing_telemetry" in trends
    assert "avg_hourly_ceiling" in trends["pricing_telemetry"]
    assert "avg_fixed_budget" in trends["pricing_telemetry"]


def test_update_proposal_rules_markdown(tmp_path):
    """Verify safe markdown updating of proposal rules without breaking invariants."""
    guide_file = tmp_path / "UPWORK_PROPOSAL_CRAFTING_GUIDE.md"
    initial_content = """---
name: upwork-proposal-crafting-skill
last_updated: "2026-10-01"
---

# Guide

## 6. Dynamic Market Evolution Changelog

> *This section is maintained automatically by the Monthly Strategy Engine.*

- **v1.0.0 (2026-10-07)**: Baseline release.
"""
    guide_file.write_text(initial_content, encoding="utf-8")

    engine = MonthlyStrategyEngine(state_dir=tmp_path)
    engine.guide_file = guide_file
    engine.skill_file = tmp_path / "SKILL.md"  # won't exist, will be skipped safely

    strategy = {
        "market_summary": "Surge in Claude Code and MCP workflows.",
        "recommended_proof_focus": "Production agent system on MCP server.",
        "recommended_risk_focus": "Silent webhook failure and unhandled retries.",
        "trending_keywords_to_mirror": ["MCP", "Claude Code"],
        "changelog_entry": "Calibrated proof priorities to emphasize MCP tool safety.",
    }

    updated = engine.update_proposal_rules_markdown(strategy)
    assert updated is True

    new_content = guide_file.read_text(encoding="utf-8")
    assert "Monthly Strategy Calibration" in new_content
    assert "Calibrated proof priorities to emphasize MCP tool safety." in new_content
    assert "v1.0.0 (2026-10-07)" in new_content  # preserved baseline


@patch("aryan_implementation.engine.monthly_strategy_engine.send_telegram_message")
def test_run_monthly_pass_mocked(mock_tg, tmp_path):
    """Verify full monthly pass execution with mocked notification."""
    engine = MonthlyStrategyEngine(state_dir=tmp_path)
    res = engine.run_monthly_pass()
    assert res["status"] == "success"
    assert "trends" in res
    assert "strategy" in res


def test_sanitize_no_em_dash_and_zero_em_dash_guarantee():
    """Verify em dashes, en dashes, and double hyphens are stripped from all proposals and answers."""
    from aryan_implementation.engine.draft import (
        EM_DASH_CHARS,
        ProposalDrafter,
        extract_required_opener,
        sanitize_no_em_dash,
    )

    dirty_text = "We build autonomous agents — using Claude Code – and $19–$35/hr pricing -- with zero silent failures!"
    cleaned = sanitize_no_em_dash(dirty_text)
    for ch in EM_DASH_CHARS:
        assert ch not in cleaned
    assert "--" not in cleaned
    assert "$19-$35" in cleaned

    desc = 'HOW TO APPLY: Start your proposal with the words "Glenso agent" so I know you read this.'
    assert extract_required_opener(desc) == "Glenso agent"

    cl, answers = ProposalDrafter._post_process_llm_output(
        "I built a similar pipeline — connecting Apollo and Instantly – for outbound sales!",
        [{"question": "Rate — per hour?", "answer": "My rate is $65/hr — available immediately -- for Phase 1!"}],
        desc,
    )
    assert cl.startswith("Glenso agent.")
    assert cl.endswith("Aryan")
    assert "—" not in cl and "–" not in cl and "--" not in cl and "!" not in cl
    assert "—" not in answers[0]["question"]
    assert "—" not in answers[0]["answer"] and "--" not in answers[0]["answer"]

    drafter = ProposalDrafter()
    check_bad = drafter.self_check_draft(
        cl,
        [{"question": "Q1", "answer": "Contains forbidden — em dash"}],
        {"boost_connects": 6},
    )
    assert check_bad["checks"]["no_em_dash"] is False
    assert check_bad["passed"] is False


@patch("aryan_implementation.engine.telegram_bot.telegram_api_call")
def test_telegram_view_draft_and_approve_callback_buttons(mock_tg_api, tmp_path):
    """Verify Telegram 'View Draft' and 'Approve & Submit' inline buttons work end-to-end."""
    from aryan_implementation.engine.mcp_client import UpworkMCPClient
    from aryan_implementation.engine.state_manager import StateManager
    from aryan_implementation.engine.telegram_bot import TelegramBotListener

    mock_tg_api.return_value = {"ok": True}
    state_mgr = StateManager(tmp_path)
    state_mgr.init_state_directory()
    mcp = UpworkMCPClient(mock_mode=True)

    jid = "2114366496356934763"
    state_mgr.save_jobs({
        jid: {
            "job_id": jid,
            "title": "Build AI Agent <Claude & MCP> — Fast",
            "status": "drafted",
            "type": "hourly",
            "score": 96.2,
            "draft": {
                "cover_letter": "Glenso agent.\n\nWe handle <schema> & webhooks — cleanly.\n\nAryan",
                "answers": [{"question": "Timeline — Phase 1?", "answer": "2-4 days <tested> — zero downtime."}],
                "terms": {"type": "hourly", "hourly_bid": 65.0, "boost_connects": 6},
            },
        }
    })

    listener = TelegramBotListener(mcp_client=mcp, state_mgr=state_mgr)

    # 1. Test "View Draft" button click
    listener.handle_callback_query({
        "id": "cb_view_1",
        "data": f"view:{jid}",
        "message": {"message_id": 101, "chat": {"id": 999}},
    })
    send_calls = [c for c in mock_tg_api.call_args_list if c[0][0] == "sendMessage"]
    assert len(send_calls) == 1
    sent_payload = send_calls[0][0][1]
    assert "Cover Letter Preview" in sent_payload["text"]
    assert "—" not in sent_payload["text"]
    assert "&lt;schema&gt;" in sent_payload["text"]
    assert "reply_markup" in sent_payload

    # 2. Test "Approve & Submit" button click
    mock_tg_api.reset_mock()
    listener.handle_callback_query({
        "id": "cb_approve_1",
        "data": f"approve:{jid}",
        "message": {"message_id": 101, "chat": {"id": 999}},
    })
    edit_calls = [c for c in mock_tg_api.call_args_list if c[0][0] == "editMessageText"]
    assert len(edit_calls) == 1
    assert "PROPOSAL SUBMITTED ON UPWORK" in edit_calls[0][0][1]["text"]

    updated_jobs = state_mgr.load_jobs()
    assert updated_jobs[jid]["status"] == "submitted"