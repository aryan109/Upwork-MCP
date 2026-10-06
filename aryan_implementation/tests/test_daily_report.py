"""
Unit tests for Notifier and Daily Comprehensive Report Engine.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from aryan_implementation.engine.notifier import (
    notify,
    notify_proposal_ready,
    notify_client_message_or_invite,
    notify_low_connects,
    notify_daily_report_ready,
)
from aryan_implementation.engine.daily_report import DailyReportEngine
from aryan_implementation.engine.state_manager import StateManager


from unittest.mock import patch


def test_notification_dispatch() -> None:
    # Test that notification dispatches without error and does not spam Telegram in tests
    with patch("aryan_implementation.engine.notifier.send_telegram_message", return_value=True):
        res = notify_proposal_ready("Test AI Solutions Engineer", 92.5, "~01test")
        assert isinstance(res, bool)

        res_invite = notify_client_message_or_invite("Client Malta", "Can you hop on a scoping call?")
        assert isinstance(res_invite, bool)

        res_connects = notify_low_connects(15)
        assert isinstance(res_connects, bool)


def test_daily_report_generation(tmp_path: Path) -> None:
    state_mgr = StateManager(tmp_path)
    state_mgr.init_state_directory()

    jobs = state_mgr.load_jobs()
    # Add an active and a skipped job
    jobs["sample_job_1"] = {
        "job_id": "sample_job_1",
        "title": "AI Solutions Engineer: Take Our AI Prototype to Production",
        "type": "hourly",
        "budget_hourly_max": 80,
        "status": "skipped",
        "decision": "SKIP",
        "disqualifiers": ["D11"],
        "total_hired": 1,
        "persons_to_hire": 1,
        "first_seen_at": "2026-10-06T00:00:00+00:00",
    }
    jobs["sample_job_2"] = {
        "job_id": "sample_job_2",
        "title": "Claude MCP Server Developer",
        "type": "fixed",
        "budget_fixed": 1200,
        "status": "drafted",
        "decision": "APPLY",
        "score": 95.0,
        "pricing_hint": "Propose 3-milestone implementation",
        "first_seen_at": "2026-10-06T01:00:00+00:00",
    }
    state_mgr.save_jobs(jobs)

    report_eng = DailyReportEngine(state_dir=tmp_path)
    res = report_eng.generate_daily_report(date_str="2026-10-06")

    assert res["date"] == "2026-10-06"
    assert res["staged_count"] == 1
    assert "Daily Upwork Intelligence & Action Report" in res["content"]
    assert "What's Happened" in res["content"]
    assert "What the Trend Is" in res["content"]
    assert "What You Need to Focus on Today" in res["content"]
    assert "How We Can Improve" in res["content"]
    assert "Connects Saved by D11" in res["content"]

    # Verify report file exists
    assert Path(res["report_path"]).exists()
    assert Path(res["archive_path"]).exists()
