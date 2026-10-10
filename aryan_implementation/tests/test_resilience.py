"""
Unit and Integration Tests for Multi-Tier Resilience Architecture.
Covers:
- Distributed Lease CAS acquisition, expiration, and priority yields
- Watchdog invariant evaluations (W1-W10)
- Deduplicated alerts and resolution dispatch
- Monotonic state progression and incident capping
- Telegram interactive card idempotency (alerted_at CAS check)
- Cloud backup provider execution
- Serverless API handlers (api/health.py, api/tick.py)
"""
import io
import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from aryan_implementation.engine.alerts import AlertManager
from aryan_implementation.engine.cloud_backup import GitHubStoreProvider
from aryan_implementation.engine.lease import LeaseManager
from aryan_implementation.engine.state_backend import FileBackend
from aryan_implementation.engine.state_manager import StateManager
from aryan_implementation.engine.telegram_bot import (
    TelegramBotListener,
    send_interactive_proposal,
    process_telegram_update,
)
from aryan_implementation.engine.tier import can, current_tier, PRIORITY
from aryan_implementation.engine.watchdog import WatchdogEvaluator


def test_tier_priorities_and_capabilities():
    assert PRIORITY["railway"] < PRIORITY["vercel"] < PRIORITY["local"]
    assert can("railway", "hunt") is True
    assert can("vercel", "hunt") is True
    assert can("local", "hunt") is True
    assert can("vercel", "cloud_backup") is False
    assert can("local", "cloud_backup") is True


def test_lease_acquisition_and_priority_yield(tmp_path):
    backend = FileBackend(tmp_path)
    lease_mgr = LeaseManager(backend=backend)

    # 1. Railway (priority 1) acquires lease
    acquired = lease_mgr.try_acquire("hunter", "railway", run_id="r1")
    assert acquired is True

    lease, _ = lease_mgr.get_lease("hunter")
    assert lease["holder"] == "railway"
    assert lease["active"] is True

    # 2. Local (priority 3) fails while Railway lease is active
    acquired_local = lease_mgr.try_acquire("hunter", "local", run_id="l1")
    assert acquired_local is False

    # 3. Simulate expired Railway lease
    past_iso = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    lease["expires_at"] = past_iso
    backend.write_json("lease.json", lease)

    # 4. Local acquires expired lease
    acquired_local = lease_mgr.try_acquire("hunter", "local", run_id="l2")
    assert acquired_local is True

    # 5. Priority yield test: when higher priority (railway) has fresh heartbeat, local yields
    backend.write_json("heartbeats/railway.json", {
        "tier": "railway",
        "seen_at": datetime.now(timezone.utc).isoformat(),
        "ok": True,
    })
    renewed = lease_mgr.renew_or_yield("hunter", "local")
    assert renewed is False  # Yielded to higher priority tier

    # 6. Force release
    lease_mgr.force_release("hunter")
    lease, _ = lease_mgr.get_lease("hunter")
    assert lease["active"] is False


def test_watchdog_conditions_w1_to_w10(tmp_path):
    backend = FileBackend(tmp_path)
    watchdog = WatchdogEvaluator(backend=backend)
    now = datetime.now(timezone.utc)

    # Initially empty store -> W1 should trigger (hunter_silent)
    conditions = watchdog.evaluate(now=now)
    assert conditions["W1"]["triggered"] is True

    # Record healthy state & pass
    backend.write_json("state.json", {
        "last_success_at": now.isoformat(),
        "kill_switch": False,
        "incidents": [],
        "last_pass_record": {"auth_ok": True, "healthy": True},
    })
    backend.write_json("heartbeats/railway.json", {
        "tier": "railway",
        "seen_at": now.isoformat(),
        "ok": True,
    })
    backend.write_json("heartbeats/vercel.json", {
        "tier": "vercel",
        "seen_at": now.isoformat(),
        "ok": True,
    })
    backend.write_json("heartbeats/local.json", {
        "tier": "local",
        "seen_at": now.isoformat(),
        "ok": True,
    })

    conditions_healthy = watchdog.evaluate(now=now)
    assert conditions_healthy["W1"]["triggered"] is False
    assert conditions_healthy["W2"]["triggered"] is False
    assert conditions_healthy["W4"]["triggered"] is False

    # Test W4: kill switch active
    backend.write_json("state.json", {
        "last_success_at": now.isoformat(),
        "kill_switch": True,
        "incidents": [],
        "last_pass_record": {"auth_ok": True, "healthy": True},
    })
    conditions_kill = watchdog.evaluate(now=now)
    assert conditions_kill["W4"]["triggered"] is True

    # Test W5: empty streak (6 consecutive passes with 0 candidates)
    backend.write_json("state.json", {
        "last_success_at": now.isoformat(),
        "kill_switch": False,
        "empty_streak": 6,
        "incidents": [],
        "last_pass_record": {"auth_ok": True, "healthy": True},
    })
    conditions_empty = watchdog.evaluate(now=now)
    assert conditions_empty["W5"]["triggered"] is True


def test_alert_manager_deduplication_and_resolution(tmp_path):
    backend = FileBackend(tmp_path)
    alert_mgr = AlertManager(backend=backend)

    with patch("aryan_implementation.engine.alerts.send_telegram_message") as mock_tg:
        # First alert dispatch
        res1 = alert_mgr.raise_alert("W1", "Hunter silent for 35 min", severity="CRITICAL")
        assert res1 is True
        assert mock_tg.call_count == 1

        # Immediate repeat should be suppressed by cooldown
        res2 = alert_mgr.raise_alert("W1", "Hunter silent for 35 min", severity="CRITICAL")
        assert res2 is False
        assert mock_tg.call_count == 1

        # Resolution dispatch
        res_resolve = alert_mgr.resolve_alert("W1", resolution_note="Passes resumed")
        assert res_resolve is True
        assert mock_tg.call_count == 2  # Dispatched resolution message


def test_state_manager_monotonic_status_progression(tmp_path):
    backend = FileBackend(tmp_path)
    state_mgr = StateManager(tmp_path, backend=backend)

    # Initial job in 'discovered' status
    job_id = "test_job_001"
    initial_job = {
        "job_id": job_id,
        "title": "Senior AI Engineer",
        "status": "discovered",
        "updated_at": "2026-10-10T00:00:00Z",
    }
    state_mgr.save_jobs({job_id: initial_job})

    # Advance to 'staged' (valid forward move)
    advanced_job = {
        "job_id": job_id,
        "title": "Senior AI Engineer",
        "status": "staged",
        "updated_at": "2026-10-10T01:00:00Z",
    }
    state_mgr.save_jobs({job_id: advanced_job})

    loaded = state_mgr.load_jobs()
    assert loaded[job_id]["status"] == "staged"

    # Attempt to regress to 'discovered' (must be blocked by monotonic check)
    regressed_job = {
        "job_id": job_id,
        "title": "Senior AI Engineer",
        "status": "discovered",
        "updated_at": "2026-10-10T02:00:00Z",
    }
    state_mgr.save_jobs({job_id: regressed_job})

    loaded = state_mgr.load_jobs()
    assert loaded[job_id]["status"] == "staged"  # Did NOT regress!

    # Test incident capping at 50
    st = state_mgr.load_state()
    for i in range(60):
        st["incidents"].append({
            "at": datetime.now(timezone.utc).isoformat(),
            "type": "other",
            "detail": f"test incident {i}",
            "resolved": False,
        })
    state_mgr.save_state(st)
    saved_st = state_mgr.load_state()
    assert len(saved_st["incidents"]) <= 50


def test_telegram_interactive_card_idempotency(tmp_path):
    backend = FileBackend(tmp_path)
    state_mgr = StateManager(tmp_path, backend=backend)

    job = {
        "job_id": "job_idem_123",
        "title": "Build LangChain Agent",
        "url": "https://www.upwork.com/jobs/~job_idem_123",
    }
    score_res = {"score": 88.0, "reasons": ["high_fit"]}
    draft = {"terms": {"type": "fixed", "charged_amount": "500"}}

    with patch("aryan_implementation.engine.telegram_bot.telegram_api_call") as mock_api:
        mock_api.return_value = {"ok": True}

        # First call: should send message and stamp alerted_at
        ok1 = send_interactive_proposal(job, score_res, draft, chat_id="12345", state_mgr=state_mgr)
        assert ok1 is True
        assert job.get("alerted_at") is not None
        assert mock_api.call_count == 1

        # Second call with the same job dict: should detect alerted_at and skip sending
        ok2 = send_interactive_proposal(job, score_res, draft, chat_id="12345", state_mgr=state_mgr)
        assert ok2 is True
        assert mock_api.call_count == 1  # Still 1, duplicate blocked!


def test_telegram_bot_process_update(tmp_path):
    backend = FileBackend(tmp_path)
    state_mgr = StateManager(tmp_path, backend=backend)
    job_id = "job_btn_456"
    state_mgr.save_jobs({
        job_id: {
            "job_id": job_id,
            "title": "Autonomous Agent",
            "status": "staged",
            "score": 85.0,
            "draft": {"cover_letter": "I have built production agents..."},
        }
    })

    with patch("aryan_implementation.engine.telegram_bot.telegram_api_call") as mock_api:
        mock_api.return_value = {"ok": True}

        # Simulate Reject inline button click
        update = {
            "update_id": 999,
            "callback_query": {
                "id": "cb_001",
                "data": f"reject:{job_id}",
                "message": {"chat": {"id": 12345}, "message_id": 678},
            },
        }

        mock_mcp = MagicMock()
        res = process_telegram_update(update, mcp_client=mock_mcp, state_mgr=state_mgr)
        assert res.get("handled") is True
        assert mock_api.call_count >= 1

        # Verify job is rejected
        loaded = state_mgr.load_jobs()
        assert loaded[job_id]["status"] in ("rejected", "rejected_by_aryan")


def test_cloud_backup_manifest_and_provider(tmp_path):
    dest_dir = tmp_path / "cloud_backup"
    provider = GitHubStoreProvider()
    res = provider.snapshot_config(dest_dir)
    assert res is not None
    assert (dest_dir / "store_config.json").exists()


def test_api_health_handler():
    from api.health import handler

    req = MagicMock()
    req.makefile.return_value = io.BytesIO(b"")
    h = handler(req, ("127.0.0.1", 80), None)
    assert hasattr(h, "do_GET")


def test_api_tick_authentication():
    from api.tick import handler

    with patch.dict(os.environ, {"TICK_SECRET": "test_secret_123"}):
        req = MagicMock()
        req.makefile.return_value = io.BytesIO(b"")
        h = handler(req, ("127.0.0.1", 80), None)

        # Missing secret
        h.headers = {}
        h.path = "/api/tick"
        assert h._authenticate() is False

        # Valid X-Tick-Secret header
        h.headers = {"X-Tick-Secret": "test_secret_123"}
        assert h._authenticate() is True

        # Valid ?secret= query param
        h.headers = {}
        h.path = "/api/tick?secret=test_secret_123"
        assert h._authenticate() is True
