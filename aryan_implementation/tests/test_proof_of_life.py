"""Proof-of-life: once-per-IST-day persist, job funnel, and learnings."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from aryan_implementation.engine.state_backend import FileBackend
from aryan_implementation.engine.state_manager import StateManager
from aryan_implementation.engine.tick import (
    build_proof_of_life_message,
    is_proof_of_life_due,
    persist_proof_of_life_date,
    send_proof_of_life,
    summarize_jobs_for_proof,
)


def test_proof_of_life_due_once_after_nine_ist():
    before = datetime(2026, 10, 14, 3, 0, tzinfo=timezone.utc)  # 08:30 IST
    after = datetime(2026, 10, 14, 3, 30, tzinfo=timezone.utc)  # 09:00 IST
    assert is_proof_of_life_due({}, now_utc=before) is False
    assert is_proof_of_life_due({}, now_utc=after) is True
    assert is_proof_of_life_due({"last_proof_of_life_date": "2026-10-14"}, now_utc=after) is False
    assert is_proof_of_life_due({"last_proof_of_life_date": "2026-10-13"}, now_utc=after) is True


def test_summarize_jobs_counts_d6_and_learnings():
    now = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
    jobs = {
        "a": {
            "job_id": "a",
            "title": "Ghost n8n bot",
            "status": "skipped",
            "decision": "SKIP",
            "disqualifiers": ["D6"],
            "vetted_at": "2026-10-14T04:00:00+00:00",
        },
        "b": {
            "job_id": "b",
            "title": "Another ghost RAG",
            "status": "skipped",
            "decision": "SKIP",
            "disqualifiers": ["D6"],
            "vetted_at": "2026-10-14T05:00:00+00:00",
        },
        "c": {
            "job_id": "c",
            "title": "Claude MCP close miss",
            "status": "scored",
            "decision": "REVIEW",
            "score": 66.0,
            "vetted_at": "2026-10-14T06:00:00+00:00",
        },
    }
    funnel = summarize_jobs_for_proof(jobs, "2026-10-14", now_utc=now)
    assert funnel["analysed"] == 3
    assert funnel["apply"] == 0
    assert funnel["review"] == 0
    assert funnel["breakdown"]["D6"] == 2
    assert funnel["breakdown"]["SCORE_LOW"] == 1
    text = " ".join(funnel["learnings"])
    assert "D6" in text
    assert "not because queries are empty" in text
    assert "under 70" in text


def test_build_message_includes_processed_and_learnings():
    state = {
        "last_pass_record": {
            "healthy": True,
            "searches_ok": 37,
            "searches_failed": 0,
            "candidates": 16,
            "new": 4,
            "staged": 0,
        },
        "connects_balance": 118,
        "staged_proposals": [],
    }
    jobs = {
        "j1": {
            "title": "AI agent for CRM",
            "status": "skipped",
            "disqualifiers": ["D6"],
            "vetted_at": "2026-10-14T08:00:00+00:00",
        }
    }
    now = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
    msg = build_proof_of_life_message(
        state, "railway", jobs=jobs, token_age="11.2h", today_ist="2026-10-14", now_utc=now
    )
    assert "Jobs processed" in msg
    assert "Analysed <b>1</b>" in msg
    assert "Learnings:" in msg
    assert "D6" in msg
    assert "searches 37 ok" in msg


def test_send_proof_persists_date_so_second_tick_skips(tmp_path: Path):
    backend = FileBackend(tmp_path / "store")
    state_mgr = StateManager(tmp_path / "state", backend=backend)
    state_mgr.init_state_directory()
    st = state_mgr.load_state()
    st["last_pass_record"] = {
        "healthy": True,
        "searches_ok": 10,
        "searches_failed": 0,
        "candidates": 2,
        "new": 1,
        "staged": 0,
    }
    state_mgr.save_state(st)

    after_nine = datetime(2026, 10, 14, 8, 0, tzinfo=timezone.utc)  # 13:30 IST

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return after_nine if tz is None else after_nine.astimezone(tz)

    with patch("aryan_implementation.engine.tick.datetime", _FrozenDateTime):
        with patch("aryan_implementation.engine.telegram_notifier.send_telegram_message", return_value=True) as tg:
            assert is_proof_of_life_due(st, now_utc=after_nine) is True
            send_proof_of_life(st, "railway", backend, state_mgr=state_mgr, jobs={})
            assert tg.called
            reloaded = state_mgr.load_state()
            assert reloaded.get("last_proof_of_life_date") == "2026-10-14"
            assert is_proof_of_life_due(reloaded, now_utc=after_nine) is False


def test_persist_proof_writes_store(tmp_path: Path):
    backend = FileBackend(tmp_path / "store")
    state_mgr = StateManager(tmp_path / "state", backend=backend)
    state_mgr.init_state_directory()
    st = state_mgr.load_state()
    persist_proof_of_life_date(st, "2026-10-14", state_mgr=state_mgr)
    data, _ = backend.read_json("state.json")
    assert data["last_proof_of_life_date"] == "2026-10-14"
    assert state_mgr.load_state()["last_proof_of_life_date"] == "2026-10-14"
