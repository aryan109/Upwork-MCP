"""
Unit tests for Telegram Notifier and Notion Publisher integration.
"""
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aryan_implementation.engine.telegram_notifier import (
    get_telegram_credentials,
    save_telegram_credentials,
    send_telegram_message,
    send_proposal_alert,
    send_client_alert,
    send_connects_alert,
    send_daily_report_alert,
)
from aryan_implementation.engine.notion_publisher import (
    get_notion_token,
    NotionPublisher,
    NOTION_MASTER_PAGE_ID,
    NOTION_DAILY_REPORTS_PAGE_ID,
    NOTION_MARKET_INTEL_PAGE_ID,
)


def test_telegram_credentials_fallback():
    # When neither env var is present and files empty, returns None, None or existing creds
    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""}):
        token, chat_id = get_telegram_credentials()
        # Should execute safely without raising exceptions
        assert isinstance(token, (str, type(None)))
        assert isinstance(chat_id, (str, type(None)))


def test_telegram_message_dispatch_mocked():
    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123456:ABC-DEF", "TELEGRAM_CHAT_ID": "987654321"}):
        with patch("urllib.request.urlopen") as mock_url:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.__enter__.return_value = mock_resp
            mock_url.return_value = mock_resp

            ok = send_telegram_message("Hello Test Message")
            assert ok is True
            assert mock_url.called


def test_telegram_alert_helpers():
    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123456:ABC-DEF", "TELEGRAM_CHAT_ID": "987654321"}):
        with patch("urllib.request.urlopen") as mock_url:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.__enter__.return_value = mock_resp
            mock_url.return_value = mock_resp

            # Proposal alert
            assert send_proposal_alert("Test AI Job", 95.0, "~123456", budget_info="$1000", reasons=["high_match"]) is True

            # Client alert
            assert send_client_alert("Test Client", "Can you start today?") is True

            # Connects alert
            assert send_connects_alert(12) is True

            # Daily report alert
            assert send_daily_report_alert("Sample daily report", "2026-10-06", 2) is True


def test_notion_token_resolution():
    token = get_notion_token()
    # Must resolve token from gemini config or env
    assert token is not None
    assert len(token) > 10


def test_notion_publisher_markdown_mocked():
    publisher = NotionPublisher(token="test_notion_token")
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_url.return_value = mock_resp

        assert publisher.update_page_markdown(NOTION_DAILY_REPORTS_PAGE_ID, "# Daily Test") is True
        assert publisher.sync_master_hub() is True


def test_telegram_interactive_proposal_send(tmp_path):
    from aryan_implementation.engine.telegram_bot import send_interactive_proposal
    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123456:ABC-DEF", "TELEGRAM_CHAT_ID": "987654321"}):
        with patch("urllib.request.urlopen") as mock_url:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = b'{"ok": true, "result": {"message_id": 101}}'
            mock_resp.__enter__.return_value = mock_resp
            mock_url.return_value = mock_resp

            job = {"job_id": "~01sample", "title": "Claude Engineer", "type": "fixed"}
            score_res = {"score": 92.0, "reasons": ["spend_high"]}
            draft = {"proposed_terms": {"type": "fixed", "charge_rate": 1000, "boost_connects": 6}}
            ok = send_interactive_proposal(job, score_res, draft)
            assert ok is True


def test_telegram_bot_callback_actions(tmp_path):
    from aryan_implementation.engine.telegram_bot import TelegramBotListener
    from aryan_implementation.engine.mcp_client import UpworkMCPClient
    from aryan_implementation.engine.state_manager import StateManager

    state_mgr = StateManager(tmp_path)
    state_mgr.init_state_directory(force=True)
    jobs = state_mgr.load_jobs()
    sample_job = {
        "job_id": "~01sample",
        "title": "Claude AI Engineer",
        "status": "drafted",
        "score": 90.0,
        "draft": {
            "cover_letter": "I can build your Claude system.",
            "terms": {"type": "fixed", "charged_amount": 1000},
            "answers": [{"question": "Experience?", "answer": "5 years"}],
        },
    }
    jobs["~01sample"] = sample_job
    state_mgr.save_jobs(jobs)

    mcp = UpworkMCPClient(mock_mode=True)
    listener = TelegramBotListener(mcp, state_mgr)

    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123456:ABC-DEF", "TELEGRAM_CHAT_ID": "987654321"}):
        with patch("urllib.request.urlopen") as mock_url:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = b'{"ok": true}'
            mock_resp.__enter__.return_value = mock_resp
            mock_url.return_value = mock_resp

            # Test View action
            cb_view = {
                "id": "cb_1",
                "data": "view:~01sample",
                "message": {"message_id": 50, "chat": {"id": 987654321}},
            }
            listener.handle_callback_query(cb_view)

            # Test Approve action
            cb_approve = {
                "id": "cb_2",
                "data": "approve:~01sample",
                "message": {"message_id": 50, "chat": {"id": 987654321}},
            }
            listener.handle_callback_query(cb_approve)
            saved_jobs = state_mgr.load_jobs()
            assert saved_jobs["~01sample"]["status"] == "submitted"

            # Test Reject action on another job
            jobs["~02sample"] = {"job_id": "~02sample", "title": "Other Job", "status": "drafted"}
            state_mgr.save_jobs(jobs)
            cb_reject = {
                "id": "cb_3",
                "data": "reject:~02sample",
                "message": {"message_id": 51, "chat": {"id": 987654321}},
            }
            listener.handle_callback_query(cb_reject)
            saved_jobs_2 = state_mgr.load_jobs()
            assert "rejected" in saved_jobs_2["~02sample"]["status"]


def test_telegram_polling_409_streak_and_recovery(tmp_path):
    import io
    import urllib.error
    from aryan_implementation.engine.state_manager import StateManager
    from aryan_implementation.engine.mcp_client import UpworkMCPClient
    from aryan_implementation.engine.telegram_bot import TelegramBotListener

    state_mgr = StateManager(tmp_path)
    state_mgr.init_state_directory(force=True)
    state = state_mgr.load_state()
    state["inbound_mode"] = "polling"
    state_mgr.save_state(state)
    mcp = UpworkMCPClient(mock_mode=True)
    listener = TelegramBotListener(mcp, state_mgr)

    err_409_body = json.dumps({"ok": False, "error_code": 409, "description": "Conflict: terminated by other getUpdates request"}).encode()

    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123456:ABC-DEF", "TELEGRAM_CHAT_ID": "987654321"}):
        with patch("aryan_implementation.engine.alerts.AlertManager.raise_alert") as mock_raise, \
             patch("aryan_implementation.engine.alerts.AlertManager.resolve_alert") as mock_resolve:

            # 1st 409 error: streak 1, does NOT raise W9
            with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("url", 409, "Conflict", {}, io.BytesIO(err_409_body))):
                listener.poll_updates()
                assert listener.consecutive_409_count == 1
                mock_raise.assert_not_called()

            # 2nd 409 error: streak 2, does NOT raise W9
            with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("url", 409, "Conflict", {}, io.BytesIO(err_409_body))):
                listener.poll_updates()
                assert listener.consecutive_409_count == 2
                mock_raise.assert_not_called()

            # 3rd 409 error: streak 3, DOES raise W9
            with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("url", 409, "Conflict", {}, io.BytesIO(err_409_body))):
                listener.poll_updates()
                assert listener.consecutive_409_count == 3
                mock_raise.assert_called_once()
                args, kwargs = mock_raise.call_args
                assert args[0] == "W9"
                assert "Conflict: terminated by other getUpdates request" in args[1]

            # Next poll succeeds: resets streak and resolves W9
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"ok": true, "result": []}'
            mock_resp.__enter__.return_value = mock_resp
            with patch("urllib.request.urlopen", return_value=mock_resp):
                listener.poll_updates()
                assert listener.consecutive_409_count == 0
                mock_resolve.assert_called_once()
                r_args, _ = mock_resolve.call_args
                assert r_args[0] == "W9"


def test_ensure_telegram_webhook_registration():
    from aryan_implementation.engine.telegram_notifier import (
        ensure_telegram_webhook,
        DEFAULT_TELEGRAM_WEBHOOK_URL,
    )

    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123456:ABC-DEF"}):
        # 1. When webhook is already set
        mock_info = MagicMock()
        mock_info.read.return_value = json.dumps({
            "ok": True,
            "result": {"url": DEFAULT_TELEGRAM_WEBHOOK_URL, "has_custom_certificate": False}
        }).encode()
        mock_info.__enter__.return_value = mock_info

        with patch("urllib.request.urlopen", return_value=mock_info):
            ok, msg = ensure_telegram_webhook()
            assert ok is True
            assert "already properly set" in msg

        # 2. When webhook is empty and needs registration
        mock_empty_info = MagicMock()
        mock_empty_info.read.return_value = json.dumps({
            "ok": True,
            "result": {"url": ""}
        }).encode()
        mock_empty_info.__enter__.return_value = mock_empty_info

        mock_set_ok = MagicMock()
        mock_set_ok.read.return_value = json.dumps({"ok": True, "result": True}).encode()
        mock_set_ok.__enter__.return_value = mock_set_ok

        with patch("urllib.request.urlopen", side_effect=[mock_empty_info, mock_set_ok]):
            ok, msg = ensure_telegram_webhook()
            assert ok is True
            assert "successfully registered" in msg


def test_parse_staged_markdown():
    from aryan_implementation.engine.notion_publisher import parse_staged_markdown

    sample_md = """# 📝 Proposal Review: Claude Gateway Engineer

> 💡 **Proposal Staging Desk**:
> Edit the Cover Letter below directly.

---

### Job Overview
- **Job ID**: `~12345`
- **Score**: `95.0 / 100`

---

## Cover Letter
Hi there,

I noticed your project requiring Claude API integration.
I have built high-throughput token proxies with Redis caching.

Looking forward to connecting: let us discuss your architecture.

Best,
Aryan

---

## Screening Answers

### Q: Have you deployed Anthropic models to production?

**Answer:**
Yes, multiple pipelines with prompt caching and fallback providers.

### Q: What is your timezone?

**Answer:**
IST, overlapping 4 hours with US mornings.
"""

    parsed = parse_staged_markdown(sample_md)
    assert "Claude API integration" in parsed["cover_letter"]
    assert "High-throughput" in parsed["cover_letter"] or "high-throughput" in parsed["cover_letter"]
    # Verify Zero Em-Dash rule
    assert "—" not in parsed["cover_letter"]
    assert "–" not in parsed["cover_letter"]

    answers = parsed["answers"]
    assert len(answers) == 2
    assert answers[0]["question"] == "Have you deployed Anthropic models to production?"
    assert "Yes, multiple pipelines" in answers[0]["answer"]
    assert answers[1]["question"] == "What is your timezone?"
    assert "IST" in answers[1]["answer"]


def test_notion_publish_and_fetch_staged_proposal():
    from aryan_implementation.engine.notion_publisher import (
        NotionPublisher,
        NOTION_STAGING_DESK_PAGE_ID,
    )

    pub = NotionPublisher(token="mock_notion_token")

    # 1. Mock page creation + markdown update
    mock_create_resp = MagicMock()
    mock_create_resp.status = 200
    mock_create_resp.read.return_value = json.dumps({"id": "mock_page_123"}).encode()
    mock_create_resp.__enter__.return_value = mock_create_resp

    mock_patch_resp = MagicMock()
    mock_patch_resp.status = 200
    mock_patch_resp.read.return_value = b"{}"
    mock_patch_resp.__enter__.return_value = mock_patch_resp

    job = {
        "job_id": "~98765",
        "title": "Fullstack AI Engineer",
        "draft": {
            "cover_letter": "Original drafted cover letter.",
            "answers": [{"question": "Can you start now?", "answer": "Yes"}],
            "terms": {"type": "hourly", "charged_amount": 75.0, "boost_connects": 8},
        },
    }
    score_res = {"score": 94.0, "reasons": ["spend_high", "verified_payment"]}

    with patch("urllib.request.urlopen", side_effect=[mock_create_resp, mock_patch_resp]):
        ok, page_id, page_url = pub.publish_staged_proposal(job, score_res)
        assert ok is True
        assert page_id == "mock_page_123"
        assert "mock_page_123" in page_url

    # 2. Mock fetch staged proposal
    mock_get_resp = MagicMock()
    mock_get_resp.status = 200
    mock_get_resp.read.return_value = json.dumps({
        "markdown": "## Cover Letter\n\nEdited cover letter from Aryan.\n\n## Screening Answers\n\n### Q: Can you start now?\n\n**Answer:**\nAbsolutely tomorrow morning."
    }).encode()
    mock_get_resp.__enter__.return_value = mock_get_resp

    with patch("urllib.request.urlopen", return_value=mock_get_resp):
        staged = pub.fetch_staged_proposal("mock_page_123")
        assert staged is not None
        assert staged["cover_letter"] == "Edited cover letter from Aryan."
        assert staged["answers"][0]["answer"] == "Absolutely tomorrow morning."

    # 3. Mock status update
    mock_status_resp = MagicMock()
    mock_status_resp.status = 200
    mock_status_resp.read.return_value = b"{}"
    mock_status_resp.__enter__.return_value = mock_status_resp

    with patch("urllib.request.urlopen", return_value=mock_status_resp):
        ok = pub.update_proposal_status("mock_page_123", "submitted", "Fullstack AI Engineer")
        assert ok is True


def test_telegram_approval_syncs_notion_edits(tmp_path):
    from aryan_implementation.engine.telegram_bot import TelegramBotListener
    from aryan_implementation.engine.mcp_client import UpworkMCPClient
    from aryan_implementation.engine.state_manager import StateManager

    state_mgr = StateManager(tmp_path)
    state_mgr.init_state_directory(force=True)

    job_id = "~112233"
    job = {
        "job_id": job_id,
        "title": "Cloud AI Pipeline Engineer",
        "status": "drafted",
        "score": 95.0,
        "draft": {
            "cover_letter": "Original machine-generated cover letter.",
            "answers": [{"question": "Available?", "answer": "Yes"}],
            "notion_page_id": "test_notion_page_abc",
            "notion_url": "https://app.notion.com/p/test_notion_page_abc",
            "terms": {"type": "fixed", "charged_amount": 1200.0, "boost_connects": 10},
        },
    }
    state_mgr.save_jobs({job_id: job})

    mcp_client = UpworkMCPClient(mock_mode=True)
    listener = TelegramBotListener(mcp_client=mcp_client, state_mgr=state_mgr)

    # Mock Notion returning Aryan's updated text
    mock_notion_get = MagicMock()
    mock_notion_get.status = 200
    mock_notion_get.read.return_value = json.dumps({
        "markdown": "## Cover Letter\n\nAryan's personalized and refined cover letter.\n\n## Screening Answers\n\n### Q: Available?\n\n**Answer:**\nReady immediately for full-time."
    }).encode()
    mock_notion_get.__enter__.return_value = mock_notion_get

    cb_query = {
        "id": "cb_approve_notion_test",
        "data": f"approve:{job_id.lstrip('~')}",
        "message": {"chat": {"id": 12345}, "message_id": 999},
    }

    with patch("urllib.request.urlopen", return_value=mock_notion_get):
        with patch("aryan_implementation.engine.telegram_bot.telegram_api_call") as mock_tg:
            mock_tg.return_value = {"ok": True}
            listener.handle_callback_query(cb_query)

    # Verify that the job was submitted with Aryan's Notion edits
    updated_jobs = state_mgr.load_jobs()
    updated_job = updated_jobs.get(job_id)
    assert updated_job is not None
    assert updated_job["status"] == "submitted"
    assert updated_job["draft"]["cover_letter"] == "Aryan's personalized and refined cover letter."
    assert updated_job["draft"]["answers"][0]["answer"] == "Ready immediately for full-time."

    # Verify that Telegram confirmation calls were made with links to Upwork and Notion
    edit_calls = [c for c in mock_tg.call_args_list if c[0][0] == "editMessageText"]
    send_calls = [c for c in mock_tg.call_args_list if c[0][0] == "sendMessage"]
    assert len(edit_calls) >= 1
    assert len(send_calls) >= 1

    edit_payload = edit_calls[0][0][1]
    assert "https://www.upwork.com/ab/proposals" in edit_payload["text"]
    assert "test_notion_page_abc" in edit_payload["text"]
    assert edit_payload.get("reply_markup") is not None

    send_payload = send_calls[0][0][1]
    assert "Proposal Successfully Submitted" in send_payload["text"]
    assert "https://www.upwork.com/ab/proposals" in send_payload["text"]
    assert "test_notion_page_abc" in send_payload["text"]





