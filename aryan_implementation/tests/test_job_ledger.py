"""
Unit tests for JobLedger, timestamp extraction, permanent deduplication, and test isolation.
"""
import pytest
from datetime import datetime, timezone, timedelta
from aryan_implementation.engine.job_ledger import (
    JobLedger,
    extract_job_timestamps,
    parse_relative_time,
    is_test_job,
)


def test_is_test_job_filtering():
    assert is_test_job("~01test_job", "Some job") is True
    assert is_test_job("~01sample_claude_job", "Claude engineer") is True
    assert is_test_job("test_submission_123", "AI Expert") is True
    assert is_test_job("2107552331799943401", "[TEST] Senior Python") is True
    assert is_test_job("2107552331799943401", "Sample Claude Job") is True
    
    # Real jobs must NOT be flagged as test
    assert is_test_job("2107552331799943401", "N8N Ai Agent Content Builder") is False
    assert is_test_job("~2107797818471303457", "WordPress Site Redesign and Claude Integration") is False


def test_extract_job_timestamps_iso_and_unix():
    now_utc = datetime.now(timezone.utc)
    one_hour_ago = now_utc - timedelta(hours=1)
    
    job_iso = {
        "job_id": "2107552331799943401",
        "createdOn": one_hour_ago.isoformat(),
        "scraped_at": now_utc.isoformat(),
    }
    posted, scraped, age = extract_job_timestamps(job_iso)
    assert posted is not None
    assert scraped == now_utc.isoformat()
    assert 55.0 <= age <= 65.0

    # Unix timestamp in milliseconds
    job_unix = {
        "job_id": "2107552331799943401",
        "postedOn": int(one_hour_ago.timestamp() * 1000),
        "scraped_at": now_utc.isoformat(),
    }
    posted_u, scraped_u, age_u = extract_job_timestamps(job_unix)
    assert posted_u is not None
    assert 55.0 <= age_u <= 65.0


def test_parse_relative_time():
    now = datetime(2026, 10, 8, 12, 0, 0, tzinfo=timezone.utc)
    t1 = parse_relative_time("Posted 15 minutes ago", now)
    assert t1 == now - timedelta(minutes=15)

    t2 = parse_relative_time("3 hours ago", now)
    assert t2 == now - timedelta(hours=3)

    t3 = parse_relative_time("yesterday", now)
    assert t3 == now - timedelta(days=1)


def test_job_ledger_permanent_deduplication_and_rejection(tmp_path):
    ledger = JobLedger(state_dir=tmp_path)
    real_jid = "2107552331799943401"
    
    # Initially can process
    assert ledger.can_process_for_proposal(real_jid) is True
    assert ledger.is_blacklisted(real_jid) is False

    # Record discovery
    job_data = {
        "job_id": real_jid,
        "title": "N8N Ai Agent Content Builder",
        "createdOn": "2026-10-08T04:00:00Z",
    }
    ledger.record_job(job_data, status="discovered")
    
    # Check timestamps persisted
    entry = ledger.load_ledger()[real_jid]
    assert entry["posted_at"] == "2026-10-08T04:00:00+00:00"
    assert entry["scraped_at"] is not None
    assert entry["status"] == "discovered"

    # Reject the job
    ledger.add_to_rejected(real_jid, reason="Client demanded free trial", title="N8N Ai Agent Content Builder")
    
    # Must now be permanently blacklisted
    assert ledger.is_blacklisted(real_jid) is True
    assert ledger.can_process_for_proposal(real_jid) is False
    assert real_jid in ledger.load_rejected_ids()

    # Even across a fresh ledger instance pointing to same dir
    ledger_fresh = JobLedger(state_dir=tmp_path)
    assert ledger_fresh.is_blacklisted(real_jid) is True
    assert ledger_fresh.can_process_for_proposal(real_jid) is False
