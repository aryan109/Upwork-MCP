"""
Vercel Serverless Endpoint: Dynamic Web Dashboard & Report API
GET /api/report (also serves /report rewrite)
Query Params:
  - ?format=json (optional: returns JSON metrics instead of HTML dashboard)
  - ?date=YYYY-MM-DD (optional: target date)
"""
from http.server import BaseHTTPRequestHandler
import html
import json
import logging
import os
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

# Ensure repo root and /tmp state dir are set
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("ENGINE_TIER", "vercel")
os.environ.setdefault("UPWORK_ENGINE_DIR", "/tmp/upwork_engine")

from aryan_implementation.engine.config import STATE_DIR
from aryan_implementation.engine.state_manager import StateManager
from aryan_implementation.engine.web_report import (
    compile_daily_report_metrics,
    render_html_dashboard,
)

logger = logging.getLogger("vercel_report")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        target_date = qs.get("date", [None])[0]
        fmt = (qs.get("format", ["html"])[0] or "html").lower()

        # Synchronize from shared state store if possible
        try:
            sm = StateManager(STATE_DIR)
            sm.pull()
        except Exception as pull_err:
            logger.warning(f"Report state pull note: {pull_err}")

        try:
            metrics = compile_daily_report_metrics(STATE_DIR, target_date=target_date)

            if fmt == "json":
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(metrics, indent=2, ensure_ascii=False).encode("utf-8"))
            else:
                html_body = render_html_dashboard(metrics)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html_body.encode("utf-8"))

        except Exception as e:
            logger.exception("Failed to render report dashboard")
            self.send_response(500)
            if fmt == "json":
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            else:
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    f"<!DOCTYPE html><html><body><h1>500 Internal Error</h1><p>{html.escape(str(e))}</p></body></html>".encode("utf-8")
                )

    def log_message(self, format, *args):
        return
