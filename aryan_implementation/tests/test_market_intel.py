"""
Unit and integration tests for Market Intelligence Engine and Hourly Hunter.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from aryan_implementation.engine.market_intel import (
    MarketIntelEngine,
    extract_tech_stack,
    categorize_archetype,
    extract_client_pain_point,
    generate_content_angles,
)
from aryan_implementation.engine.vet import check_disqualifiers
from aryan_implementation.engine.state_manager import StateManager
from aryan_implementation.engine.mcp_client import UpworkMCPClient
from aryan_implementation.engine.hourly_runner import run_single_pass


def test_tech_stack_extraction() -> None:
    text = (
        "We built an AI assistant for our B2B customers with Lovable and Cursor. "
        "Stack: React, Supabase, pgvector, and OpenAI API with automated evals."
    )
    stack = extract_tech_stack(text)
    assert "Lovable" in stack
    assert "Cursor" in stack
    assert "React" in stack
    assert "Supabase" in stack
    assert "pgvector" in stack
    assert "OpenAI" in stack
    assert "Evals" in stack


def test_categorize_archetype() -> None:
    arch = categorize_archetype(
        "AI Solutions Engineer: Take Our AI Prototype to Production (RAG, Evals)",
        "Fix chunking and hallucinations on customer documents",
    )
    assert "RAG" in arch or "Evaluation" in arch

    arch_mcp = categorize_archetype(
        "Build custom MCP server for Claude",
        "Connect internal tools using Model Context Protocol",
    )
    assert "MCP" in arch_mcp or "Agent" in arch_mcp


def test_content_angles_generation() -> None:
    angles = generate_content_angles(
        title="AI Solutions Engineer: Take Our AI Prototype to Production",
        pain_point="Cursor/Lovable prototype gives wrong answers with full confidence on real PDFs",
        tech_stack=["Cursor", "Lovable", "Supabase", "pgvector", "OpenAI"],
        archetype="RAG & Evaluation Pipeline (Prototype -> Production)",
        hired_fast=True,
    )
    assert "headline_hook" in angles
    assert "prototypes hallucinate" in angles["headline_hook"].lower()
    assert len(angles["outline"]) == 3
    assert "Loom" in angles["proof_asset_to_build"]
    assert "High Urgency Signal" in angles["velocity_note"]


def test_market_intel_record_and_digest(tmp_path: Path) -> None:
    intel_eng = MarketIntelEngine(state_dir=tmp_path)

    sample_job = {
        "job_id": "2107079311620473280",
        "title": "AI Solutions Engineer: Take Our AI Prototype to Production (RAG, Evals)",
        "description": "We built an AI assistant with Lovable and Cursor. On real documents it gives wrong answers with full confidence. We need an engineer to fix retrieval and add evals. Stack: React, Supabase, OpenAI API.",
        "type": "hourly",
        "budget_hourly_min": 50,
        "budget_hourly_max": 80,
        "contractTerms": {"personsToHire": 1},
        "activityStat": {
            "jobActivity": {"totalHired": 1, "invitesSent": 0}
        },
        "client_record": {
            "country": "Malta",
            "total_spent": 21700.0,
            "hire_rate_percent": 100,
        },
    }

    record = intel_eng.record_job(sample_job)
    assert record["status"] == "FILLED"
    assert record["total_hired"] == 1
    assert "Supabase" in record["tech_stack"]
    assert "#Supabase" in record["engagement_tags"]

    # Verify digest was created
    digest_path = tmp_path / "market_intelligence_digest.md"
    assert digest_path.exists()
    digest_text = digest_path.read_text(encoding="utf-8")
    assert "High-Velocity / Rapid-Hire Niches" in digest_text
    assert "AI Solutions Engineer" in digest_text
    assert "Malta" in digest_text


def test_hourly_runner_pass(tmp_path: Path) -> None:
    state_mgr = StateManager(tmp_path)
    state_mgr.init_state_directory()

    # Preload mock job that was already filled
    jobs = state_mgr.load_jobs()
    filled_job = {
        "job_id": "job_filled_fast",
        "title": "Urgent Claude MCP Integration",
        "description": "Need Claude Code integrated via MCP into internal workflows.",
        "type": "fixed",
        "budget_fixed": 1000,
        "status": "discovered",
        "persons_to_hire": 1,
        "activityStat": {"jobActivity": {"totalHired": 1}},
        "client_record": {"payment_verified": True, "total_spent": 5000},
    }
    jobs["job_filled_fast"] = filled_job
    state_mgr.save_jobs(jobs)

    mcp = UpworkMCPClient(mock_mode=True)
    summary = run_single_pass(state_mgr, mcp, max_searches=1, max_details=1)

    assert summary["already_filled_caught"] == 1
    # Check that job status was set to skipped with D11
    updated_jobs = state_mgr.load_jobs()
    assert updated_jobs["job_filled_fast"]["status"] == "skipped"
    assert "D11" in updated_jobs["job_filled_fast"]["disqualifiers"]
