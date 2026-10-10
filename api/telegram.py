"""
Vercel Serverless Endpoint: Telegram Webhook Handler
POST /api/telegram
Protected by optional secret header X-Telegram-Bot-Api-Secret-Token (matched against TELEGRAM_WEBHOOK_SECRET).
Processes inline button callbacks (Approve & Submit, View Draft, Reject) and slash commands (/status, /queue, etc.).
"""
from http.server import BaseHTTPRequestHandler
import json
import logging
import os
import sys
from pathlib import Path

# Ensure repo root and /tmp state dir are set
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("ENGINE_TIER", "vercel")
os.environ.setdefault("UPWORK_ENGINE_DIR", "/tmp/upwork_engine")

from aryan_implementation.engine.telegram_bot import process_telegram_update

logger = logging.getLogger("vercel_telegram")


class handler(BaseHTTPRequestHandler):
    def _authenticate(self) -> bool:
        expected_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
        if not expected_secret:
            return True

        header_token = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        return header_token.strip() == expected_secret.strip()

    def do_POST(self):
        if not self._authenticate():
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": "Unauthorized webhook token"}).encode("utf-8"))
            return

        try:
            content_len = int(self.headers.get("Content-Length", 0))
            body_bytes = self.rfile.read(content_len)
            update = json.loads(body_bytes.decode("utf-8"))
        except Exception as e:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": f"Malformed request body: {e}"}).encode("utf-8"))
            return

        try:
            result = process_telegram_update(update)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "result": result}).encode("utf-8"))
        except Exception as e:
            logger.exception("Error processing webhook update")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "active",
            "tier": "vercel",
            "service": "telegram_webhook",
        }).encode("utf-8"))

    def log_message(self, format, *args):
        return
