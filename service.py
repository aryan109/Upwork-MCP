"""
24/7 Autonomous Cloud Service Runner for Railway / Production.
Combines:
1. HTTP Health Check Server (binds to $PORT for Railway healthchecks)
2. Interactive Telegram Bot Listener (1-click inline button approvals & commands)
3. Hourly Autonomous Hunter Loop (discovery, vetting, D1-D11 safeguards)
4. Daily Notion & Market Intelligence Sync
"""
import http.server
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure package is on sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from aryan_implementation.engine.config import STATE_DIR
from aryan_implementation.engine.daily_report import DailyReportEngine
from aryan_implementation.engine.hourly_runner import run_single_pass
from aryan_implementation.engine.mcp_client import UpworkMCPClient
from aryan_implementation.engine.notion_publisher import NotionPublisher
from aryan_implementation.engine.state_manager import StateManager
from aryan_implementation.engine.telegram_bot import TelegramBotListener
from aryan_implementation.engine.telegram_notifier import (
    get_telegram_credentials,
    send_telegram_message,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("upwork_service")


class HealthCheckHandler(http.server.BaseHTTPRequestHandler):
    """Simple HTTP server responding to Railway health checks."""

    def do_GET(self):
        if self.path in ("/", "/health"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            status = {
                "status": "healthy",
                "service": "Aryan Upwork Autonomous Pipeline",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            import json
            self.wfile.write(json.dumps(status).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Silence verbose access logs
        return


def start_http_server(port: int):
    server = http.server.HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    logger.info(f"Health check HTTP server listening on port {port}")
    server.serve_forever()


def hourly_hunter_worker(state_mgr: StateManager, mcp_client: UpworkMCPClient):
    """Background worker executing discovery loop (default: every 15 minutes)."""
    interval_secs = int(os.environ.get("HUNTER_INTERVAL_SECONDS", 900))
    interval_mins = interval_secs // 60
    logger.info(f"Hunter background loop started: scheduled every {interval_mins} mins ({interval_secs}s).")
    # Short initial sleep to allow bot initialization
    time.sleep(10)
    while True:
        try:
            logger.info("Starting scheduled high-velocity hunt pass...")
            summary = run_single_pass(state_mgr, mcp_client)
            staged = (summary.get("staged_proposals", summary.get("staged_total", 0))) if isinstance(summary, dict) else 0
            logger.info(f"Hunt pass finished: {staged} staged for review.")
        except Exception as e:
            logger.error(f"Error in hunter pass: {e}", exc_info=True)

        # Autonomous Monthly Strategy Check (runs once every 30 days)
        try:
            state = state_mgr.load_state()
            last_m_str = state.get("last_monthly_strategy_date")
            now_dt = datetime.now(timezone.utc)
            should_run_monthly = False
            if not last_m_str:
                should_run_monthly = True
            else:
                last_m_dt = datetime.strptime(last_m_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                if (now_dt - last_m_dt).days >= 30:
                    should_run_monthly = True

            if should_run_monthly:
                from aryan_implementation.engine.monthly_strategy_engine import MonthlyStrategyEngine
                m_eng = MonthlyStrategyEngine(state_mgr.state_dir)
                m_eng.run_monthly_pass()
        except Exception as m_err:
            logger.debug(f"Monthly strategy runner check note: {m_err}")

        # Sleep interval (default: 15 minutes / 900 seconds)
        time.sleep(interval_secs)


def main():
    port = int(os.environ.get("PORT", 8080))
    interval_secs = int(os.environ.get("HUNTER_INTERVAL_SECONDS", 900))
    interval_mins = interval_secs // 60

    # Initialize state
    state_mgr = StateManager(STATE_DIR)
    state_mgr.init_state_directory(force=False)
    mcp_client = UpworkMCPClient(mock_mode=False)

    token, chat_id = get_telegram_credentials()
    if token and chat_id:
        send_telegram_message(
            "🚀 <b>Upwork 24/7 Cloud Service Online!</b>\n\n"
            f"• ⚡ <b>{interval_mins}-Minute Rapid Discovery:</b> Active (competitive edge)\n"
            "• 🎯 <b>Interactive 1-Click Approvals:</b> Enabled\n"
            "• 📊 <b>Daily Intelligence & Notion Sync:</b> Active\n\n"
            "<i>Send /status or /queue anytime to interact with the engine.</i>",
            parse_mode="HTML",
        )

    # 1. Start HTTP Health check in daemon thread
    http_thread = threading.Thread(target=start_http_server, args=(port,), daemon=True)
    http_thread.start()

    # 2. Start Hourly Hunter in daemon thread
    hunter_thread = threading.Thread(
        target=hourly_hunter_worker,
        args=(state_mgr, mcp_client),
        daemon=True,
    )
    hunter_thread.start()

    # 3. Run Telegram Bot Listener on main thread
    bot = TelegramBotListener(mcp_client, state_mgr)
    logger.info("Starting Telegram Bot listener on main thread...")
    try:
        bot.run_forever(check_interval=2)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Service shutting down...")
        bot.stop()


if __name__ == "__main__":
    main()
