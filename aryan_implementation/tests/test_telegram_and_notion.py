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

