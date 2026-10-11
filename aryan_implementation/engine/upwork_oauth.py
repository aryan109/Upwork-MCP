"""
Upwork OAuth Token Lifecycle Manager.
Implements rotating OAuth2 refresh token chains, early refresh (at 12h age),
local IDE token file synchronization, and secure storage in secrets/upwork_oauth.json.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .config import ENGINE_DIR

logger = logging.getLogger("upwork_engine")

UPWORK_TOKEN_URL = "https://www.upwork.com/api/v3/oauth2/token"
SECRETS_DIR = ENGINE_DIR / "secrets"
OAUTH_SECRETS_PATH = SECRETS_DIR / "upwork_oauth.json"


def get_ide_token_path() -> Optional[Path]:
    """Find the local Antigravity IDE token file if present on this machine."""
    candidates = [
        Path(os.environ.get("USERPROFILE", "")) / ".gemini" / "antigravity" / "mcp_oauth_tokens.json",
        Path(os.environ.get("USERPROFILE", "")) / ".gemini" / "antigravity-ide" / "mcp_oauth_tokens.json",
        Path(os.environ.get("HOME", "")) / ".gemini" / "antigravity" / "mcp_oauth_tokens.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


class UpworkOAuthManager:
    """Manages the Upwork OAuth tokens, refresh rotation, and IDE synchronization."""

    def __init__(
        self,
        secrets_path: Optional[Path] = None,
        backend: Optional[Any] = None,
    ):
        self.secrets_path = secrets_path or (ENGINE_DIR / "secrets" / "upwork_oauth.json")
        self.backend = backend

    def _read_backend_json(self, path: str) -> Optional[Dict[str, Any]]:
        """Read JSON from backend, unpacking the (data, sha) tuple from StateBackend.read_json."""
        if not self.backend:
            return None
        try:
            result = self.backend.read_json(path)
            if isinstance(result, tuple):
                data = result[0]
            else:
                data = result
            if isinstance(data, dict) and data:
                return data
        except Exception as e:
            logger.debug(f"Failed to read {path} from backend: {e}")
        return None

    def load_token_data(self) -> Dict[str, Any]:
        """Load OAuth secrets from backend or local filesystem."""
        data = self._read_backend_json("secrets/upwork_oauth.json")
        if data:
            return data

        if self.secrets_path.exists():
            try:
                with open(self.secrets_path, "r", encoding="utf-8") as f:
                    disk = json.load(f)
                if isinstance(disk, dict) and disk.get("access_token"):
                    return disk
            except Exception as e:
                logger.warning(f"Error loading {self.secrets_path}: {e}")

        # Never mix the engine-owned chain with the IDE login.
        existing_owner = ""
        if data:
            existing_owner = str(data.get("owner") or "")
        if existing_owner == "engine":
            logger.error("Engine-owned OAuth secrets missing from store; refusing IDE reseed.")
            return {}

        return self.reseed_from_ide_file()

    def save_token_data(self, data: Dict[str, Any]) -> bool:
        """Save OAuth secrets to backend and/or local filesystem."""
        saved = False
        data["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Save to backend if available
        if self.backend:
            try:
                ok, _ = self.backend.write_json(
                    "secrets/upwork_oauth.json",
                    data,
                    message="update upwork oauth secrets",
                )
                saved = bool(ok)
            except Exception as e:
                logger.warning(f"Error saving oauth token to backend: {e}")

        # Save to local file
        try:
            self.secrets_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.secrets_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            tmp.replace(self.secrets_path)
            saved = True
        except Exception as e:
            logger.warning(f"Error saving to {self.secrets_path}: {e}")

        return saved

    def reseed_from_ide_file(self) -> Dict[str, Any]:
        """Reseed engine OAuth secrets from IDE token file if available."""
        ide_path = get_ide_token_path()
        if not ide_path or not ide_path.exists():
            return {}

        try:
            with open(ide_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            entry = d.get("https://mcp.upwork.com/mcp", {})
            tok = entry.get("token", {})
            if not tok.get("access_token"):
                return {}

            data = {
                "access_token": tok.get("access_token"),
                "refresh_token": tok.get("refresh_token"),
                "expiry": tok.get("expiry"),
                "token_url": entry.get("token_url", UPWORK_TOKEN_URL),
                "client_id": entry.get("client_id", ""),
                "client_secret": entry.get("client_secret", ""),
                "token_type": tok.get("token_type", "Bearer"),
                "updated_by": "ide_sync",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self.save_token_data(data)
            logger.info("Successfully seeded Upwork OAuth tokens from IDE token file.")
            return data
        except Exception as e:
            logger.warning(f"Error reseeding from IDE token file: {e}")
            return {}

    def sync_to_ide_file(self, data: Dict[str, Any]) -> bool:
        """Write rotated tokens back to the IDE token file so IDE doesn't lose access."""
        if data.get("owner") == "engine":
            logger.info("Skipping IDE token sync for engine-owned OAuth chain.")
            return False
        ide_path = get_ide_token_path()
        if not ide_path or not ide_path.exists():
            return False

        try:
            with open(ide_path, "r", encoding="utf-8") as f:
                d = json.load(f)

            key = "https://mcp.upwork.com/mcp"
            if key not in d:
                return False

            e = d[key]
            t = e.setdefault("token", {})
            t["access_token"] = data.get("access_token")
            if data.get("refresh_token"):
                t["refresh_token"] = data.get("refresh_token")
            if data.get("expiry"):
                t["expiry"] = data.get("expiry")
            if data.get("token_type"):
                t["token_type"] = data.get("token_type")

            tmp = ide_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, indent=2)
            tmp.replace(ide_path)
            logger.info(f"IDE token file synchronized at {ide_path}")
            return True
        except Exception as e:
            logger.warning(f"Failed to synchronize to IDE token file: {e}")
            return False

    def is_token_stale(self, token_data: Dict[str, Any], refresh_after_hours: float = 12.0) -> bool:
        """
        Check if the access token needs refreshing.
        Refreshes early (after 12h of issuance or within 2h of expiry)
        to prevent a missed tick from encountering expiration.
        """
        if not token_data or not token_data.get("access_token"):
            return True

        # Check expiry string if present
        expiry_str = token_data.get("expiry")
        now = datetime.now(timezone.utc)
        if expiry_str:
            try:
                # Parse ISO timestamp
                clean_exp = expiry_str.replace("Z", "+00:00")
                exp_dt = datetime.fromisoformat(clean_exp)
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                # If less than 4 hours remain before expiry, it is stale
                if (exp_dt - now).total_seconds() < 4 * 3600:
                    return True
            except Exception:
                pass

        # Check updated_at age (older than 12 hours)
        updated_str = token_data.get("updated_at")
        if updated_str:
            try:
                clean_up = updated_str.replace("Z", "+00:00")
                up_dt = datetime.fromisoformat(clean_up)
                if up_dt.tzinfo is None:
                    up_dt = up_dt.replace(tzinfo=timezone.utc)
                if (now - up_dt).total_seconds() > refresh_after_hours * 3600:
                    return True
            except Exception:
                pass

        return False

    def _can_refresh(self, token_data: Dict[str, Any], lease_held: bool = False) -> Tuple[bool, str]:
        """Engine-owned tokens may only be rotated by the Railway lease holder."""
        from .tier import current_tier

        owner = str(token_data.get("owner") or "ide")
        tier = current_tier()
        if owner == "engine" and tier != "railway":
            return False, f"engine token refresh blocked on tier={tier}"
        if owner == "engine" and not lease_held:
            return False, "engine token refresh requires hunter lease"
        return True, f"tier={tier} owner={owner} lease_held={lease_held}"

    def refresh(self, force: bool = False, lease_held: bool = False) -> Dict[str, Any]:
        """
        Execute OAuth2 refresh POST request, rotate the refresh token,
        save results, and sync with local IDE (IDE-owned chains only).
        """
        try:
            token_data = self.load_token_data()
            allowed, reason = self._can_refresh(token_data, lease_held=lease_held or force)
            if token_data.get("owner") == "engine" and not allowed:
                logger.warning("OAuth refresh skipped: %s", reason)
                return {"ok": False, "error": "refresh_blocked", "detail": reason}

            refresh_token = token_data.get("refresh_token")
            client_id = token_data.get("client_id")
            token_url = token_data.get("token_url", UPWORK_TOKEN_URL)
            owner = token_data.get("owner", "ide")
            logger.info(
                "Executing Upwork OAuth token refresh owner=%s force=%s %s updated_at=%s",
                owner,
                force,
                reason,
                token_data.get("updated_at"),
            )

            if not refresh_token or not client_id:
                logger.error("OAuth refresh aborted: missing refresh_token or client_id")
                return {"ok": False, "error": "missing_credentials"}

            form = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
            }
            if token_data.get("client_secret"):
                form["client_secret"] = token_data["client_secret"]

            body = urllib.parse.urlencode(form).encode("utf-8")
            req = urllib.request.Request(
                token_url,
                data=body,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                    "User-Agent": "Antigravity/1.0 (Windows)",
                },
                method="POST",
            )

            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    resp = json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as err:
                err_body = err.read().decode("utf-8", errors="replace")[:500]
                logger.error(f"Upwork OAuth refresh HTTP {err.code}: {err_body}")
                return {"ok": False, "http_code": err.code, "error": err_body}

            new_at = resp.get("access_token")
            new_rt = resp.get("refresh_token")
            expires_in = int(resp.get("expires_in") or 86400)
            if not new_at:
                logger.error("No access_token in Upwork refresh response")
                return {"ok": False, "error": "no_access_token"}

            now_utc = datetime.now(timezone.utc)
            exp_dt = now_utc + timedelta(seconds=expires_in)
            token_data["access_token"] = new_at
            if new_rt:
                token_data["refresh_token"] = new_rt
            token_data["expiry"] = exp_dt.isoformat()
            token_data["token_type"] = resp.get("token_type", "Bearer")
            token_data["updated_at"] = now_utc.isoformat()
            token_data["updated_by"] = "engine_refresh"
            token_data.pop("force_refresh_once", None)

            self.save_token_data(token_data)
            self.sync_to_ide_file(token_data)
            os.environ["UPWORK_ACCESS_TOKEN"] = new_at
            logger.info("Upwork OAuth refresh succeeded. New expiry: %s", token_data["expiry"])
            return {"ok": True, "token_data": token_data}
        except Exception as e:
            logger.error("OAuth refresh failed with exception: %s", e, exc_info=True)
            return {"ok": False, "error": str(e)}

    def get_valid_access_token(self, lease_held: bool = False) -> str:
        """
        Retrieve a valid access token.
        If the token is stale and lease_held is True, refreshes it.
        Engine-owned tokens are only refreshed on the Railway tier.
        """
        token_data = self.load_token_data()
        force_once = bool(token_data.get("force_refresh_once"))
        stale = self.is_token_stale(token_data) or force_once

        if stale and lease_held:
            logger.info(
                "Access token needs refresh (stale=%s force_once=%s owner=%s expiry=%s)",
                self.is_token_stale(token_data),
                force_once,
                token_data.get("owner"),
                token_data.get("expiry"),
            )
            res = self.refresh(force=force_once, lease_held=lease_held)
            if res.get("ok"):
                token_data = res.get("token_data", token_data)
            elif res.get("error") == "refresh_blocked":
                logger.info("Engine token refresh deferred to Railway; using current access token")
            elif token_data.get("owner") == "engine":
                logger.error("Engine token refresh failed: %s", res.get("error"))

        token = token_data.get("access_token") or ""
        if not token:
            logger.warning("No access_token in secrets; refusing UPWORK_ACCESS_TOKEN env fallback for engine chain")
            if token_data.get("owner") != "engine":
                token = os.environ.get("UPWORK_ACCESS_TOKEN", "")
        return token


_default_oauth_manager: Optional[UpworkOAuthManager] = None


def get_oauth_manager() -> UpworkOAuthManager:
    """Get or create singleton UpworkOAuthManager."""
    global _default_oauth_manager
    if _default_oauth_manager is None:
        _default_oauth_manager = UpworkOAuthManager()
    return _default_oauth_manager


def get_valid_access_token(lease_held: bool = False) -> str:
    """Convenience helper to retrieve active access token."""
    return get_oauth_manager().get_valid_access_token(lease_held=lease_held)
