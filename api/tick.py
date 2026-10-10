"""
Vercel Serverless Endpoint: Unified Tick
POST /api/tick (also accepts GET)
Protected by X-Tick-Secret header (or ?secret= query parameter).
Executes a single time-budgeted tick on the Vercel tier.
"""
from http.server import BaseHTTPRequestHandler
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

from aryan_implementation.engine.tick import run_tick
from aryan_implementation.engine.tier import get_commit_sha

logger = logging.getLogger("vercel_tick")


class handler(BaseHTTPRequestHandler):
    def _authenticate(self) -> bool:
        expected_secret = os.environ.get("TICK_SECRET")
        if not expected_secret:
            # If no secret configured in environment, permit execution
            return True

        # Check X-Tick-Secret header
        header_secret = self.headers.get("X-Tick-Secret")
        if header_secret and header_secret.strip() == expected_secret.strip():
            return True

        # Check Authorization: Bearer <secret>
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            if token == expected_secret.strip():
                return True

        # Check query string ?secret=
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        param_secret = qs.get("secret", [None])[0]
        if param_secret and param_secret.strip() == expected_secret.strip():
            return True

        return False

    def _execute_tick(self):
        if not self._authenticate():
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": False,
                "error": "Unauthorized: invalid or missing tick secret",
                "tier": "vercel",
            }).encode("utf-8"))
            return

        # Vercel Hobby functions have a max duration limit (60s).
        # We enforce a 45-second time budget.
        time_budget = float(os.environ.get("TICK_TIME_BUDGET_S", "45.0"))

        try:
            summary = run_tick(tier="vercel", time_budget_s=time_budget)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            res = {
                "ok": True,
                "tier": "vercel",
                "commit": get_commit_sha(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": summary,
            }
            self.wfile.write(json.dumps(res, default=str).encode("utf-8"))
        except Exception as e:
            logger.exception("Vercel tick execution failed")
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": False,
                "tier": "vercel",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }).encode("utf-8"))

    def do_POST(self):
        self._execute_tick()

    def do_GET(self):
        self._execute_tick()

    def log_message(self, format, *args):
        return
