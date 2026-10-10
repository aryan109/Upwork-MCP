"""
Vercel Serverless Endpoint: Health Check
GET /api/health
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aryan_implementation.engine.tier import get_commit_sha


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        res = {
            "status": "healthy",
            "tier": "vercel",
            "commit": get_commit_sha(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.wfile.write(json.dumps(res).encode("utf-8"))

    def log_message(self, format, *args):
        return
