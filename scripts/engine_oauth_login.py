"""
One-time engine-owned Upwork OAuth login.

Registers (or reuses) a public PKCE client, opens a browser for Aryan to
authorize, exchanges the code, and writes secrets/upwork_oauth.json to the
shared GitHub state store with owner="engine". Never prints token values.

Usage:
    python scripts/engine_oauth_login.py
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import logging
import os
import secrets
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aryan_implementation.engine.mcp_client import UpworkMCPClient
from aryan_implementation.engine.state_backend import get_default_backend
from aryan_implementation.engine.upwork_oauth import (
    UPWORK_TOKEN_URL,
    UpworkOAuthManager,
    get_ide_token_path,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("engine_oauth_login")

AUTHORIZE_URL = "https://www.upwork.com/ab/account-security/oauth2/authorize"
REGISTER_URLS = [
    "https://mcp.upwork.com/register",
    "https://www.upwork.com/register",
]
CALLBACK_HOST = "127.0.0.1"
CALLBACK_PORT = 8765
CLIENT_NAME = "aryan-upwork-engine"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _pkce_pair() -> Tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def _http_json(url: str, method: str = "GET", body: Optional[dict] = None, headers: Optional[dict] = None) -> Tuple[int, Any]:
    hdrs = {
        "Accept": "application/json",
        "User-Agent": "aryan-upwork-engine/1.0",
    }
    if headers:
        hdrs.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = {"raw": raw[:400]}
            return r.status, parsed
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", errors="replace")[:500]
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"raw": raw}
        return err.code, parsed


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    result: Dict[str, str] = {}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        if parsed.path.rstrip("/") != "/callback":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found")
            return
        if "error" in qs:
            _CallbackHandler.result = {
                "error": qs.get("error", ["unknown"])[0],
                "error_description": qs.get("error_description", [""])[0],
            }
        else:
            _CallbackHandler.result = {
                "code": qs.get("code", [""])[0],
                "state": qs.get("state", [""])[0],
            }
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h2>Upwork engine login complete.</h2>"
            b"<p>You can close this tab and return to the terminal.</p></body></html>"
        )

    def log_message(self, format, *args):
        return


def _register_public_client(redirect_uri: str) -> Optional[Dict[str, Any]]:
    payload = {
        "client_name": CLIENT_NAME,
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "application_type": "native",
    }
    for url in REGISTER_URLS:
        logger.info("Attempting dynamic client registration at %s", url)
        status, body = _http_json(url, method="POST", body=payload)
        if status in (200, 201) and isinstance(body, dict) and body.get("client_id"):
            logger.info("Registered public client (client_id length=%s)", len(body.get("client_id", "")))
            return body
        logger.warning("Registration at %s returned HTTP %s", url, status)
    return None


def _ide_client_id() -> str:
    path = get_ide_token_path()
    if not path or not path.exists():
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        entry = d.get("https://mcp.upwork.com/mcp", {})
        return str(entry.get("client_id") or "")
    except Exception as e:
        logger.warning("Could not read IDE client_id: %s", e)
        return ""


def _wait_for_code(redirect_uri: str, expected_state: str, timeout_s: int = 300) -> str:
    _CallbackHandler.result = {}
    server = http.server.HTTPServer((CALLBACK_HOST, CALLBACK_PORT), _CallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    logger.info("Waiting for browser callback on %s (timeout %ss)...", redirect_uri, timeout_s)
    thread.join(timeout=timeout_s)
    try:
        server.server_close()
    except Exception:
        pass
    result = _CallbackHandler.result
    if result.get("error"):
        raise RuntimeError(f"OAuth error: {result.get('error')} {result.get('error_description')}")
    if not result.get("code"):
        raise RuntimeError("No authorization code received. Did you complete the browser login?")
    if result.get("state") != expected_state:
        raise RuntimeError("OAuth state mismatch; aborting.")
    return result["code"]


def _exchange_code(
    client_id: str,
    code: str,
    redirect_uri: str,
    verifier: str,
    client_secret: str = "",
) -> Dict[str, Any]:
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": verifier,
    }
    if client_secret:
        form["client_secret"] = client_secret
    body = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(
        UPWORK_TOKEN_URL,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "aryan-upwork-engine/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"Token exchange HTTP {err.code}: {raw}") from err


def _verify_account(access_token: str) -> str:
    client = UpworkMCPClient(auth_token=access_token)
    res = client.call_raw("list_accounts", {})
    accounts = res.get("accounts", []) if isinstance(res, dict) else []
    names = [str(a.get("name") or "") for a in accounts if isinstance(a, dict)]
    logger.info("list_accounts names: %s", names)
    if not any("aryan" in n.lower() for n in names):
        raise RuntimeError(f"Authorized account is not Aryan. Names: {names}")
    return names[0]


def main() -> int:
    redirect_uri = f"http://{CALLBACK_HOST}:{CALLBACK_PORT}/callback"
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(24)

    registered = _register_public_client(redirect_uri)
    client_secret = ""
    if registered:
        client_id = registered["client_id"]
        client_secret = registered.get("client_secret") or ""
        logger.info("Using newly registered engine client.")
    else:
        client_id = _ide_client_id()
        if not client_id:
            logger.error("Dynamic registration failed and no IDE client_id is available.")
            return 1
        logger.info(
            "Dynamic registration rejected; falling back to IDE client_id "
            "(new grant = independent refresh-token chain)."
        )

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    auth_url = f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"
    logger.info("Opening browser for Upwork authorization...")
    webbrowser.open(auth_url)

    code = _wait_for_code(redirect_uri, state)
    logger.info("Authorization code received; exchanging for tokens...")
    token_resp = _exchange_code(client_id, code, redirect_uri, verifier, client_secret=client_secret)
    access_token = token_resp.get("access_token")
    refresh_token = token_resp.get("refresh_token")
    expires_in = int(token_resp.get("expires_in") or 86400)
    if not access_token or not refresh_token:
        logger.error("Token response missing access_token or refresh_token (keys=%s)", sorted(token_resp.keys()))
        return 1

    account_name = _verify_account(access_token)
    now_utc = datetime.now(timezone.utc)
    expiry = now_utc + timedelta(seconds=expires_in)
    payload = {
        "owner": "engine",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expiry": expiry.isoformat(),
        "token_url": UPWORK_TOKEN_URL,
        "client_id": client_id,
        "client_secret": client_secret,
        "token_type": token_resp.get("token_type", "Bearer"),
        "updated_by": "engine_oauth_login",
        "updated_at": now_utc.isoformat(),
        "force_refresh_once": True,
        "account_name": account_name,
    }

    backend = get_default_backend()
    mgr = UpworkOAuthManager(backend=backend)
    if not mgr.save_token_data(payload):
        logger.error("Failed to persist secrets/upwork_oauth.json")
        return 1
    logger.info(
        "Saved engine-owned OAuth secrets. owner=engine expiry=%s account=%s",
        payload["expiry"],
        account_name,
    )
    logger.info("Railway will consume force_refresh_once on its first hunt tick.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        logger.error("Login cancelled.")
        sys.exit(130)
    except Exception as e:
        logger.error("engine_oauth_login failed: %s", e, exc_info=True)
        sys.exit(1)
