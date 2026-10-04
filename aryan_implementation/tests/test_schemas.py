"""
Unit tests validating JSON schemas and seed configuration files.
"""
from __future__ import annotations

import json
from pathlib import Path
import jsonschema
import pytest

from aryan_implementation.engine.config import (
    TEMPLATES_DIR,
    JOBS_SCHEMA_PATH,
    STATE_SCHEMA_PATH,
    CAMPAIGNS_SCHEMA_PATH,
    CAMPAIGNS_EXAMPLE_PATH,
    SCORING_EXAMPLE_PATH,
)


def test_campaigns_schema_and_example() -> None:
    with open(CAMPAIGNS_SCHEMA_PATH, "r", encoding="utf-8") as sf:
        schema = json.load(sf)
    with open(CAMPAIGNS_EXAMPLE_PATH, "r", encoding="utf-8") as ef:
        example = json.load(ef)
    jsonschema.validate(instance=example, schema=schema)


def test_state_schema() -> None:
    with open(STATE_SCHEMA_PATH, "r", encoding="utf-8") as sf:
        schema = json.load(sf)

    sample_state = {
        "last_run_at": "2026-10-04T12:00:00Z",
        "last_run_id": "run_001",
        "runs_today": 2,
        "applies_today": 1,
        "applies_today_by_campaign": {
            "claude-implementation": 1,
            "mcp-integrations": 0,
        },
        "connects_balance": 110,
        "connects_spent_month": 16,
        "connects_budget_month": 250,
        "badge_on": False,
        "scoring_version": "1.0",
        "campaigns_version": "1.0.0",
        "incidents": [],
        "kill_switch": False,
        "mcp_tool_count_observed": 48,
    }
    jsonschema.validate(instance=sample_state, schema=schema)


def test_jobs_schema() -> None:
    with open(JOBS_SCHEMA_PATH, "r", encoding="utf-8") as sf:
        schema = json.load(sf)

    sample_job = {
        "job_id": "~01sample123",
        "first_seen_at": "2026-10-04T10:00:00Z",
        "last_checked_at": "2026-10-04T10:30:00Z",
        "campaign": "claude-implementation",
        "title": "Claude AI Integration Workflow",
        "url": "https://www.upwork.com/jobs/~01sample123",
        "description_excerpt": "Building a custom workflow connecting Claude Code to internal APIs.",
        "type": "fixed",
        "budget_fixed": 600,
        "duration": "1 to 3 months",
        "connects_cost": 16,
        "client": {
            "country": "United States",
            "total_spent": 5000,
            "hire_rate": 75,
            "rating": 4.9,
            "payment_verified": True,
        },
        "activity": {
            "invitesSent": 1,
            "interviewing": 1,
            "hired": 0,
        },
        "score": 82.5,
        "decision": "APPLY",
        "status": "discovered",
    }
    jsonschema.validate(instance=sample_job, schema=schema)
