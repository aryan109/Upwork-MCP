"""
Tests for AIJobAnalyzer and ClientLearningEngine.
Verifies deep analytical job vetting, continuous learning, and client risk filtering.
"""

import json
import pytest
from unittest.mock import patch
from aryan_implementation.engine.ai_client_learner import ClientLearningEngine
from aryan_implementation.engine.ai_job_analyzer import AIJobAnalyzer


@pytest.fixture
def tmp_learning_engine(tmp_path):
    return ClientLearningEngine(state_dir=tmp_path)


def test_client_learner_record_rejection_and_approval(tmp_learning_engine):
    bad_job = {
        "id": "job_bad_01",
        "title": "Need WordPress plugin cold caller",
        "client": {
            "id": "client_bad_999",
            "payment_verified": False,
        }
    }
    tmp_learning_engine.record_rejection(bad_job, reason="Scope creep and toxic price")
    
    data = tmp_learning_engine.load_learnings()
    assert "client_bad_999" in data["negative_patterns"]["rejected_client_hashes"]
    assert data["negative_patterns"]["total_rejected"] == 1
    assert data["negative_patterns"]["bad_client_reasons"]["Scope creep and toxic price"] == 1

    good_job = {
        "id": "job_good_01",
        "title": "Build LangChain Claude Agent",
        "client": {
            "id": "client_good_777",
            "payment_verified": True,
        }
    }
    tmp_learning_engine.record_approval(good_job)
    data = tmp_learning_engine.load_learnings()
    assert "client_good_777" in data["positive_patterns"]["approved_client_hashes"]
    assert data["positive_patterns"]["total_approved"] == 1

    context = tmp_learning_engine.get_learning_context()
    assert "CONTINUOUS CLIENT LEARNING" in context
    assert "Scope creep and toxic price" in context


def test_ai_job_analyzer_heuristic_fallback(tmp_path):
    analyzer = AIJobAnalyzer(state_dir=tmp_path)
    
    # When keys are None
    with patch.object(analyzer, "_get_api_keys", return_value=(None, None)):
        res = analyzer.analyze_job_fit(
            job={"title": "Small bugfix"},
            heuristic_score_data={"score": 85.0, "decision": "APPLY"}
        )
        assert res["evaluator"] == "heuristic_fallback"
        assert res["decision"] == "APPLY"
        assert res["fit_score"] == 85.0


def test_ai_job_analyzer_gemini_analysis(tmp_path):
    analyzer = AIJobAnalyzer(state_dir=tmp_path)

    mock_gemini_payload = {
        "decision": "APPLY",
        "fit_score": 95,
        "client_risk_level": "LOW",
        "toxic_client_flags": [],
        "scope_archetype": "High Margin Modern LLM/RAG Pipeline",
        "fit_reasoning": "High budget enterprise client looking for production LangChain architecture.",
        "key_winning_hook": "Architected similar multi-agent systems with deterministic token budgets."
    }

    job_data = {
        "id": "~01testjob123",
        "title": "Senior Python LangChain Engineer",
        "description": "Looking for an expert to build production LangChain agent pipelines.",
        "budget": 2500,
        "client": {
            "id": "verified_client_88",
            "payment_verified": True,
            "total_spent": 120000,
            "hire_rate": 85,
            "country": "United States"
        }
    }

    import io
    fake_response = io.BytesIO(json.dumps({
        "candidates": [{
            "content": {
                "parts": [{
                    "text": json.dumps(mock_gemini_payload)
                }]
            }
        }]
    }).encode("utf-8"))

    with patch.object(analyzer, "_get_api_keys", return_value=("fake_gemini_key", None)):
        with patch("urllib.request.urlopen", return_value=fake_response):
            result = analyzer.analyze_job_fit(job_data, {"score": 90.0, "decision": "APPLY"})
            assert result["decision"] == "APPLY"
            assert result["fit_score"] == 95
            assert result["client_risk_level"] == "LOW"
            assert "multi-agent" in result["key_winning_hook"]
            assert "gemini" in result["evaluator"]
