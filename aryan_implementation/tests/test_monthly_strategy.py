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