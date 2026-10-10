"""
24/7 Autonomous Cloud Service Runner for Railway / Production.
Combines:
1. HTTP Health Check Server (binds to $PORT for Railway healthchecks)
2. Interactive Telegram Bot Listener (1-click inline button approvals & commands)
3. Hourly Autonomous Hunter Loop (discovery, vetting, D1-D11 safeguards)
4. Daily Notion & Market Intelligence Sync
"""
import html
import http.server
import json
import logging
import os
import sys
import threading
import time
import urllib.parse
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


from aryan_implementation.engine.web_report import (
    compile_daily_report_metrics,
    render_html_dashboard,
)


class HealthCheckHandler(http.server.BaseHTTPRequestHandler):
    """
    Production HTTP Server for Railway:
    - Responds to Railway health checks at /health
    - Serves dynamic interactive Daily Report Web Dashboard at / and /report
    - Serves JSON API at /api/daily-report and /api/status
    """

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query_params = urllib.parse.parse_qs(parsed.query)

        # 1. Railway Health Check
        if path in ("/health",):
            reasons = []
            now_utc = datetime.now(timezone.utc)
            try:
                state_mgr = StateManager(STATE_DIR)
                state = state_mgr.load_state()

                if state.get("kill_switch"):
                    reasons.append("kill_switch_active")

                last_success = state.get("last_success_at")
                if last_success:
                    try:
                        succ_dt = datetime.fromisoformat(last_success.replace("Z", "+00:00"))
                        if (now_utc - succ_dt).total_seconds() > 2 * 3600:
                            reasons.append("hunter_silent: last successful pass > 2h old")
                    except Exception:
                        pass
                else:
                    reasons.append("hunter_silent: no successful pass recorded")

                last_pass = state.get("last_pass_record", {})
                if last_pass and not last_pass.get("auth_ok", True):
                    reasons.append("auth_failed: OAuth rejected")
            except Exception as e:
                reasons.append(f"state_read_error: {e}")

            status_code = 503 if reasons else 200
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            status = {
                "status": "unhealthy" if reasons else "healthy",
                "service": "Aryan Upwork Autonomous Pipeline",
                "reasons": reasons,
                "timestamp": now_utc.isoformat(),
            }
            self.wfile.write(json.dumps(status).encode("utf-8"))
            return

        # 2. Daily Report JSON API
        elif path in ("/api/daily-report", "/api/report"):
            try:
                date_param = query_params.get("date", [None])[0]
                metrics = compile_daily_report_metrics(STATE_DIR, target_date=date_param)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(metrics, indent=2, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                logger.error(f"Error serving report JSON: {e}", exc_info=True)
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        # 3. Dynamic Interactive HTML Daily Report Dashboard
        elif path in ("/", "/report", "/daily-report"):
            try:
                date_param = query_params.get("date", [None])[0]
                metrics = compile_daily_report_metrics(STATE_DIR, target_date=date_param)
                html_content = render_html_dashboard(metrics)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html_content.encode("utf-8"))
            except Exception as e:
                logger.error(f"Error serving report HTML dashboard: {e}", exc_info=True)
                self.send_response(500)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"<h1>500 Internal Error</h1><p>{html.escape(str(e))}</p>".encode("utf-8"))
            return

        # 4. Pipeline Status JSON
        elif path in ("/api/status", "/status"):
            try:
                sm = StateManager(STATE_DIR)
                st = sm.load_state()
                jb = sm.load_jobs()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "connects_balance": st.get("connects_balance", 110),
                    "kill_switch": st.get("kill_switch", False),
                    "total_jobs": len(jb),
                    "staged_proposals": sum(1 for j in jb.values() if j.get("status") in ("drafted", "preview_ready")),
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                }, indent=2).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
            return

        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def log_message(self, format, *args):
        # Silence verbose access logs
        return


LAST_TICK_COMPLETED_AT = time.time()


def start_http_server(port: int):
    server = http.server.HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    logger.info(f"Health check & Web Report HTTP server listening on port {port}")
    server.serve_forever()


def supervisor_worker(interval_secs: int):
    """Supervisor thread: exits process if a tick has not completed in 2x interval to trigger ALWAYS restart."""
    global LAST_TICK_COMPLETED_AT
    logger.info("Supervisor watchdog thread started.")
    time.sleep(60)  # Startup grace period
    while True:
        elapsed = time.time() - LAST_TICK_COMPLETED_AT
        max_allowed = (2 * interval_secs) + 120
        if elapsed > max_allowed:
            logger.critical(
                f"FATAL: Hunter tick stalled! No tick completed in {elapsed:.0f}s (threshold: {max_allowed}s). "
                f"Triggering immediate process termination (os._exit(1)) to allow Railway ALWAYS restart policy to revive container."
            )
            os._exit(1)
        time.sleep(15)


def hourly_hunter_worker(state_mgr: StateManager, mcp_client: UpworkMCPClient):
    """Background worker executing discovery loop via unified tick (default: every 15 minutes)."""
    global LAST_TICK_COMPLETED_AT
    from aryan_implementation.engine.tick import run_tick

    interval_secs = int(os.environ.get("HUNTER_INTERVAL_SECONDS", 900))
    interval_mins = interval_secs // 60
    logger.info(f"Hunter background loop started: scheduled every {interval_mins} mins ({interval_secs}s).")
    time.sleep(5)
    while True:
        try:
            logger.info("Starting scheduled high-velocity tick on Railway tier...")
            tick_res = run_tick(tier="railway")
            LAST_TICK_COMPLETED_AT = time.time()
            staged = (tick_res.get("pass_summary", {}).get("staged_proposals", 0)) if isinstance(tick_res, dict) else 0
            logger.info(f"Tick completed: role={tick_res.get('role', 'hunter')} healthy={tick_res.get('healthy')} staged={staged}")
        except Exception as e:
            logger.error(f"Error in tick pass: {e}", exc_info=True)

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

    from aryan_implementation.engine.tier import get_commit_sha
    commit_sha = get_commit_sha()
    pub_domain = os.environ.get("PUBLIC_DASHBOARD_URL", "https://upwork-engine-production-16dc.up.railway.app")

    token, chat_id = get_telegram_credentials()
    if token and chat_id:
        send_telegram_message(
            f"🚀 <b>Upwork 24/7 Cloud Service Online!</b>\n\n"
            f"• 🏷️ <b>Tier:</b> <code>railway</code> (commit <code>{commit_sha}</code>)\n"
            f"• ⚡ <b>Interval:</b> {interval_mins} mins (autonomous tick)\n"
            f"• 🌐 <b>Dashboard:</b> {pub_domain}\n"
            f"• 🎯 <b>Interactive 1-Click Approvals:</b> Enabled\n"
            f"• 📊 <b>Daily Intelligence & Notion Sync:</b> Active\n\n"
            f"<i>Send /status or /queue anytime to interact with the engine.</i>",
            parse_mode="HTML",
        )

    # 1. Start HTTP Health check in daemon thread
    http_thread = threading.Thread(target=start_http_server, args=(port,), daemon=True)
    http_thread.start()

    # 2. Start Supervisor watchdog in daemon thread
    supervisor_thread = threading.Thread(target=supervisor_worker, args=(interval_secs,), daemon=True)
    supervisor_thread.start()

    # 3. Start Hourly Hunter in daemon thread
    hunter_thread = threading.Thread(
        target=hourly_hunter_worker,
        args=(state_mgr, mcp_client),
        daemon=True,
    )
    hunter_thread.start()

    # 4. Run Telegram Bot Listener on main thread
    bot = TelegramBotListener(mcp_client, state_mgr)
    logger.info("Starting Telegram Bot listener on main thread...")
    try:
        bot.run_forever(check_interval=2)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Service shutting down...")
        bot.stop()


if __name__ == "__main__":
    main()
