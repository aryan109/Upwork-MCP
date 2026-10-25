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
    # 1. Older than 1 hour (>1.0h first-mover window)
    job_old = {
        "title": "n8n automation",
        "posted_age_hours": 1.5,
        "proposals_count": 3,
        "activityStat": {"jobActivity": {"totalInvitedToInterview": 0}},
    }
    disq, d_id, reason = check_disqualifiers(job_old)
    assert disq is True
    assert d_id == "D8"
    assert "first-mover window" in str(reason)

    # 2. High competition (>= 20 proposals) even if < 1h old
    job_crowded = {
        "title": "n8n automation",
        "posted_age_hours": 0.4,
        "proposals_count": 22,
        "activityStat": {"jobActivity": {"totalInvitedToInterview": 0}},
    }
    disq2, d_id2, reason2 = check_disqualifiers(job_crowded)
    assert disq2 is True
    assert d_id2 == "D8"
    assert "High competition" in str(reason2)

    # 3. Client already interviewing or sent invites
    job_interviewing = {
        "title": "n8n automation",
        "posted_age_hours": 0.3,
        "proposals_count": 4,
        "activityStat": {"jobActivity": {"totalInvitedToInterview": 1, "invitesSent": 1}},
    }
    disq3, d_id3, reason3 = check_disqualifiers(job_interviewing)
    assert disq3 is True
    assert d_id3 == "D8"
    assert "already interviewing" in str(reason3)


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


def test_disqualifier_d11_already_filled() -> None:
    # 1. Filled job: 1 to hire, 1 already hired
    job_filled = {
        "title": "AI Solutions Engineer: Take Our AI Prototype to Production",
        "contractTerms": {"personsToHire": 1},
        "activityStat": {
            "jobActivity": {"totalHired": 1, "totalInvitedToInterview": 0}
        },
    }
    disq, d_id, reason = check_disqualifiers(job_filled)
    assert disq is True
    assert d_id == "D11"
    assert "Job already filled" in reason
    assert "(1/1 hired)" in reason

    # 2. Multi-hire job still open: 3 to hire, 1 hired, 0 interviewing in first-mover window
    job_multi = {
        "title": "AI Solutions Engineer",
        "posted_age_hours": 0.4,
        "proposals_count": 4,
        "contractTerms": {"personsToHire": 3},
        "activityStat": {
            "jobActivity": {"totalHired": 1, "totalInvitedToInterview": 0}
        },
    }
    disq, _, _ = check_disqualifiers(job_multi)
    assert disq is False

    # 3. Unfilled job: 1 to hire, 0 hired, 0 interviewing in first-mover window
    job_unfilled = {
        "title": "AI Solutions Engineer",
        "posted_age_hours": 0.25,
        "proposals_count": 2,
        "contractTerms": {"personsToHire": 1},
        "activityStat": {
            "jobActivity": {"totalHired": 0, "totalInvitedToInterview": 0}
        },
    }
    disq, _, _ = check_disqualifiers(job_unfilled)
    assert disq is False


def test_worked_example_1_claude_implementation_expert() -> None:
    # Example 1 adapted for <1h First-Mover window (<20 proposals, 0 interviews)
    job = {
        "title": "Claude Implementation Expert",
        "description": "Need Claude Code integrated into our business workflow to automate operations.",
        "type": "hourly",
        "hourly_max": 40,
        "duration": "> 3 months",
        "proposals_count": 6,
        "posted_age_hours": 0.35,
        "connects_cost": 16,
        "client_record": {
            "total_spent": 430000,
            "hire_rate_percent": 75,
            "rating": 4.9,
            "reviews_count": 28,
            "jobs_posted": 40,
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
    # Example 5 adapted for <1h First-Mover window
    job = {
        "title": "n8n Automation Expert for HubSpot Slack Gmail",
        "description": "Automate data pipeline between Typeform, HubSpot and Slack with clear error boundaries.",
        "type": "hourly",
        "hourly_max": 45,
        "duration": "< 1 month",
        "proposals_count": 3,
        "posted_age_hours": 0.4,
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


def test_normalize_upwork_mcp_nested_schema_prevents_false_d6() -> None:
    from aryan_implementation.engine.vet import normalize_job_record

    summary = {
        "job_id": "2114233276906784853",
        "title": "AI Platform Integration & Account Risk Research Engineer (Claude)",
        "type": "fixed",
        "budget": "5,000.00",
        "posted_age_hours": 0.25,
        "client": {
            "country": "United States",
            "feedback_score": 5.0,
            "reviews_count": 12,
            "jobs_posted": 23,
            "jobs_with_hires": 15,
            "spend_total": 4492.42,
            "verification_status": "VERIFIED",
        },
    }
    detail = {
        "status": "ok",
        "connects_balance": 74,
        "client_record": {
            "country": "United States",
            "feedback_score": 5.0,
            "reviews_count": 12,
            "jobs_posted": 23,
            "jobs_with_hires": 15,
            "spend_total": 4492.42,
        },
        "data": {
            "marketplaceJobPosting": {
                "content": {
                    "title": "<untrusted_data>AI Platform Integration & Account Risk Research Engineer (Claude)</untrusted_data>",
                    "description": "<untrusted_data>We need an engineer to build our Claude API integration, webhook pipeline, and production monitoring dashboard.</untrusted_data>",
                },
                "activityStat": {
                    "jobActivity": {
                        "totalApplicants": 7,
                        "totalHired": 0,
                        "totalInvitedToInterview": 0,
                    }
                },
                "contractTerms": {
                    "contractType": "FIXED",
                    "personsToHire": 1,
                    "fixedPriceContractTerms": {"amount": {"displayValue": "5,000.00"}},
                },
            }
        },
    }

    norm = normalize_job_record(summary, detail)
    assert norm["budget_fixed"] == 5000.0
    assert norm["client_record"]["payment_verified"] is True
    assert norm["client_record"]["total_spent"] == 4492.42
    assert norm["client_record"]["hire_rate_percent"] > 60.0
    assert "<untrusted_data>" not in norm["description"]

    disq, d_id, _ = check_disqualifiers(norm)
    assert disq is False, f"Unexpectedly disqualified by {d_id}"

    res = score_job(norm, campaign_threshold=70)
    assert res["decision"] == "APPLY"
    assert res["score"] >= 85.0


def test_concise_job_from_high_quality_client_scores_apply() -> None:
    # Concise <100 char job post from an elite client (4.95 stars, 18 reviews, 30 jobs posted, $28k spent) posted 12 mins ago
    job = {
        "title": "Need Python & AI Automation Developer for Internal Workflow",
        "description": "Looking for an experienced developer to connect our CRM with LLM APIs ASAP.",
        "type": "hourly",
        "budget": "50.00–85.00/hr",
        "posted_age_hours": 0.2,
        "proposals_tier": "Less than 5",
        "client_record": {
            "feedback_score": 4.95,
            "reviews_count": 18,
            "jobs_posted": 30,
            "jobs_with_hires": 24,
            "spend_total": 28500.0,
            "verification_status": "VERIFIED",
        },
        "activityStat": {
            "jobActivity": {
                "totalApplicants": 3,
                "totalHired": 0,
                "totalInvitedToInterview": 0,
                "invitesSent": 0,
            }
        },
    }
    disq, d_id, _ = check_disqualifiers(job)
    assert disq is False, f"Unexpectedly disqualified by {d_id}"
    res = score_job(job, campaign_threshold=70)
    assert res["decision"] == "APPLY"
    assert res["score"] >= 85.0
    assert "elite_client_bonus" in res["reasons"]
    assert "first_mover_prime" in res["reasons"]


def test_three_hour_reporting_cadence() -> None:
    from datetime import datetime, timezone, timedelta
    from aryan_implementation.engine.hourly_runner import is_three_hour_report_due

    now = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
    assert is_three_hour_report_due({}, now) is True
    assert is_three_hour_report_due({"last_3h_report_at": (now - timedelta(hours=2, minutes=50)).isoformat()}, now) is False
    assert is_three_hour_report_due({"last_3h_report_at": (now - timedelta(hours=3, minutes=1)).isoformat()}, now) is True


def test_d4_allows_legitimate_telegram_whatsapp_automation_jobs() -> None:
    job = {
        "title": "Build n8n AI Agent with Telegram and WhatsApp Business API notifications",
        "description": "Connect our FastAPI backend to WhatsApp Business API and a Telegram bot for automated customer support.",
        "type": "hourly",
        "budget": "40.00–75.00/hr",
        "client": {
            "spend_total": 12000.0,
            "verification_status": "VERIFIED",
            "jobs_posted": 10,
            "jobs_with_hires": 8,
            "feedback_score": 4.95,
        },
    }
    disq, d_id, _ = check_disqualifiers(job)
    assert disq is False, f"Legitimate bot integration job falsely disqualified by {d_id}"


def test_execute_with_audit_detects_mcp_error_payloads(tmp_path) -> None:
    from aryan_implementation.engine.logger import execute_with_audit

    def failing_tool(tool_name, payload):
        return {
            "status": "error",
            "error_code": "CLIENT",
            "reason": "days_posted cannot be combined with from_date/to_date",
        }

    res = execute_with_audit(
        func=failing_tool,
        tool="find_jobs",
        action="smart_search",
        params={"mode": "most_recent"},
        run_id="test_run",
        log_path=tmp_path / "runs.jsonl",
    )
    assert res["ok"] is False
    assert res["error_class"] == "validation"

