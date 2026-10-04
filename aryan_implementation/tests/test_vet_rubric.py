"""
Unit tests for lead scoring rubric and disqualifier rules (06_LEAD_SCORING_RUBRIC.md).
"""
from __future__ import annotations

import pytest
from aryan_implementation.engine.vet import check_disqualifiers, score_job


def test_disqualifier_d1_already_applied() -> None:
    job = {"applied": True, "title": "Claude workflow"}
    disq, d_id, reason = check_disqualifiers(job)
    assert disq is True
    assert d_id == "D1"


def test_disqualifier_d2_location_restriction() -> None:
    job = {
        "title": "AI Agent Developer",
        "preferred_locations": {
            "location_required": True,
            "locations": ["United States", "Canada"],
        },
    }
    disq, d_id, reason = check_disqualifiers(job)
    assert disq is True
    assert d_id == "D2"


def test_disqualifier_d3_capability_gate() -> None:
    job = {"title": "Build a Unity game with AI and Solidity smart contracts"}
    disq, d_id, reason = check_disqualifiers(job)
    assert disq is True
    assert d_id == "D3"


def test_disqualifier_d4_policy_violation() -> None:
    job = {
        "title": "Python Developer",
        "description": "Contact me on Telegram to arrange payment outside Upwork.",
    }
    disq, d_id, reason = check_disqualifiers(job)
    assert disq is True
    assert d_id == "D4"


def test_disqualifier_d5_staffing_commission() -> None:
    job = {
        "title": "Sales Automation",
        "description": "Commission only role, no upfront pay, join our agency pool.",
    }
    disq, d_id, reason = check_disqualifiers(job)
    assert disq is True
    assert d_id == "D5"


def test_disqualifier_d6_three_zeros() -> None:
    job = {
        "title": "Build ChatGPT Wrapper",
        "client_record": {"payment_verified": False, "total_spent": 0},
        "activityStat": {"jobActivity": {"totalHired": 0}},
    }
    disq, d_id, reason = check_disqualifiers(job)
    assert disq is True
    assert d_id == "D6"


def test_disqualifier_d7_under_floors() -> None:
    # Fixed under $100
    job_fixed = {"type": "fixed", "budget_fixed": 50}
    disq, d_id, _ = check_disqualifiers(job_fixed)
    assert disq is True
    assert d_id == "D7"

    # Hourly ceiling under $25
    job_hourly = {"type": "hourly", "hourly_max": 20}
    disq, d_id, _ = check_disqualifiers(job_hourly)
    assert disq is True
    assert d_id == "D7"


def test_disqualifier_d8_stale_pile_on() -> None:
    job = {
        "title": "n8n automation",
        "posted_age_hours": 96,
        "proposals_count": 60,
        "activityStat": {"jobActivity": {"totalInvitedToInterview": 0}},
    }
    disq, d_id, _ = check_disqualifiers(job)
    assert disq is True
    assert d_id == "D8"


def test_disqualifier_d9_unpaid_test() -> None:
    job = {
        "title": "AI Assistant Developer",
        "description": "Requires completing an unpaid test task before any interview.",
    }
    disq, d_id, _ = check_disqualifiers(job)
    assert disq is True
    assert d_id == "D9"


def test_disqualifier_d10_conflict_client() -> None:
    job = {
        "title": "Claude Specialist",
        "client_record": {"hash": "client_abc_123", "payment_verified": True},
    }
    disq, d_id, _ = check_disqualifiers(job, open_clients={"client_abc_123"})
    assert disq is True
    assert d_id == "D10"


def test_worked_example_1_claude_implementation_expert() -> None:
    # Example 1 from 06_LEAD_SCORING_RUBRIC.md
    job = {
        "title": "Claude Implementation Expert",
        "description": "Need Claude Code integrated into our business workflow to automate operations.",
        "type": "hourly",
        "hourly_max": 40,
        "duration": "> 3 months",
        "proposals_count": 25,
        "posted_age_hours": 20,
        "connects_cost": 16,
        "client_record": {
            "total_spent": 430000,
            "hire_rate_percent": 75,
            "rating": 4.9,
            "avg_hourly_paid": 5.04,
            "payment_verified": True,
        },
        "activityStat": {
            "jobActivity": {"totalInvitedToInterview": 0, "totalHired": 0}
        },
        "screening_questions": ["Q1", "Q2"],
    }

    disq, _, _ = check_disqualifiers(job)
    assert disq is False

    res = score_job(job, campaign_threshold=70)
    assert res["score"] >= 70.0
    assert res["decision"] == "APPLY"
    assert "avg_paid_low" in res["reasons"]
    assert "fixed Sprint" in res["pricing_hint"]


def test_worked_example_5_n8n_automation() -> None:
    # Example 5 from 06_LEAD_SCORING_RUBRIC.md
    job = {
        "title": "n8n Automation Expert for HubSpot Slack Gmail",
        "description": "Automate data pipeline between Typeform, HubSpot and Slack with clear error boundaries.",
        "type": "hourly",
        "hourly_max": 45,
        "duration": "< 1 month",
        "proposals_count": 3,
        "posted_age_hours": 3,
        "connects_cost": 14,
        "client_record": {
            "total_spent": 3200,
            "hire_rate_percent": 60,
            "rating": 4.6,
            "avg_hourly_paid": 28,
            "payment_verified": True,
        },
        "activityStat": {
            "jobActivity": {"totalInvitedToInterview": 0, "totalHired": 0}
        },
        "screening_questions": ["Experience with n8n?"],
    }

    disq, _, _ = check_disqualifiers(job)
    assert disq is False

    res = score_job(job, campaign_threshold=70)
    assert res["score"] >= 75.0
    assert res["decision"] == "APPLY"
