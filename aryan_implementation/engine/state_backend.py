"""
Pluggable State Store Backend for Upwork Engine.
Supports local FileBackend (for tests and offline local caching)
and GitHubBackend (private repo Contents API with Compare-And-Swap retries).
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .config import ENGINE_DIR

logger = logging.getLogger("upwork_engine")


class StateBackend(ABC):
    """Abstract interface for distributed state storage."""

    @abstractmethod
    def read_file(self, path: str) -> Tuple[Optional[str], Optional[str]]:
        """Read a file. Returns (content, sha_or_version)."""
        pass

    @abstractmethod
    def write_file(
        self,
        path: str,
        content: str,
        message: str = "",
        sha: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Write a file using CAS. Returns (success, new_sha)."""
        pass

    def read_json(self, path: str) -> Tuple[Optional[Any], Optional[str]]:
        """Read and deserialize JSON. Returns (data, sha)."""
        content, sha = self.read_file(path)
        if content is None:
            return None, None
        try:
            return json.loads(content), sha
        except Exception as e:
            logger.error(f"Error parsing JSON from {path}: {e}")
            return None, sha

    def write_json(
        self,
        path: str,
        data: Any,
        message: str = "",
        sha: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Serialize and write JSON with CAS."""
        content = json.dumps(data, indent=2, ensure_ascii=False)
        return self.write_file(path, content, message=message, sha=sha)

    @abstractmethod
    def append_jsonl(self, path: str, record: Dict[str, Any], message: str = "") -> bool:
        """Append a JSON line to a file."""
        pass

    @abstractmethod
    def upload_blob(self, path: str, content_bytes: bytes, message: str = "") -> bool:
        """Upload binary data (e.g. gzipped logs)."""
        pass


class FileBackend(StateBackend):
    """Local filesystem implementation of StateBackend."""

    def __init__(self, root_dir: Union[str, Path]):
        self.root = Path(root_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, path: str) -> Path:
        clean = path.lstrip("/\\").replace("\\", "/")
        return self.root / clean

    def _sha(self, content_bytes: bytes) -> str:
        return hashlib.sha1(b"blob " + str(len(content_bytes)).encode() + b"\0" + content_bytes).hexdigest()

    def read_file(self, path: str) -> Tuple[Optional[str], Optional[str]]:
        fp = self._resolve(path)
        if not fp.exists():
            return None, None
        try:
            raw = fp.read_bytes()
            return raw.decode("utf-8"), self._sha(raw)
        except Exception as e:
            logger.warning(f"FileBackend read error ({path}): {e}")
            return None, None

    def write_file(
        self,
        path: str,
        content: str,
        message: str = "",
        sha: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        fp = self._resolve(path)
        raw = content.encode("utf-8")
        current_sha = self._sha(fp.read_bytes()) if fp.exists() else None

        if sha is not None and current_sha is not None and sha != current_sha:
            logger.warning(f"FileBackend CAS conflict on {path}: expected {sha}, found {current_sha}")
            return False, current_sha

        fp.parent.mkdir(parents=True, exist_ok=True)
        tmp = fp.with_suffix(".tmp")
        tmp.write_bytes(raw)
        tmp.replace(fp)
        return True, self._sha(raw)

    def append_jsonl(self, path: str, record: Dict[str, Any], message: str = "") -> bool:
        fp = self._resolve(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with open(fp, "a", encoding="utf-8") as f:
            f.write(line)
        return True

    def upload_blob(self, path: str, content_bytes: bytes, message: str = "") -> bool:
        fp = self._resolve(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        tmp = fp.with_suffix(".tmp")
        tmp.write_bytes(content_bytes)
        tmp.replace(fp)
        return True


class GitHubBackend(StateBackend):
    """
    GitHub Contents & Git Blob API implementation with Compare-And-Swap (CAS).
    Retries up to 3 times on HTTP 409 conflict.
    Caches reads locally in cache_dir to conserve rate limit.
    """

    def __init__(
        self,
        repo: str,
        token: str,
        branch: str = "main",
        cache_dir: Optional[Path] = None,
    ):
        self.repo = repo.strip("/")
        self.token = token.strip()
        self.branch = branch
        self.cache_dir = cache_dir or (ENGINE_DIR / "store_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.local_cache = FileBackend(self.cache_dir)
        self.api_base = f"https://api.github.com/repos/{self.repo}"

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "UpworkEngine-GitHubBackend/1.0",
        }

    def _req(
        self,
        url: str,
        method: str = "GET",
        data: Optional[Dict[str, Any]] = None,
        timeout: int = 10,
    ) -> Tuple[int, Dict[str, Any]]:
        body = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=body, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = json.loads(r.read().decode("utf-8"))
                return r.status, resp
        except urllib.error.HTTPError as e:
            try:
                err_data = json.loads(e.read().decode("utf-8"))
            except Exception:
                err_data = {"error": str(e)}
            return e.code, err_data
        except Exception as e:
            return 599, {"error": str(e)}

    def read_file(self, path: str) -> Tuple[Optional[str], Optional[str]]:
        clean_path = path.lstrip("/\\").replace("\\", "/")
        url = f"{self.api_base}/contents/{clean_path}?ref={self.branch}"
        status, data = self._req(url)

        if status == 200:
            content_b64 = data.get("content", "")
            sha = data.get("sha")
            raw_bytes = base64.b64decode(content_b64)
            text = raw_bytes.decode("utf-8", errors="replace")
            # Update local read cache
            self.local_cache.write_file(clean_path, text)
            return text, sha
        elif status == 404:
            return None, None
        else:
            logger.warning(f"GitHubBackend read_file HTTP {status} for {clean_path}. Falling back to cache.")
            return self.local_cache.read_file(clean_path)

    def write_file(
        self,
        path: str,
        content: str,
        message: str = "",
        sha: Optional[str] = None,
        retries: int = 3,
    ) -> Tuple[bool, Optional[str]]:
        clean_path = path.lstrip("/\\").replace("\\", "/")
        url = f"{self.api_base}/contents/{clean_path}"
        current_sha = sha

        for attempt in range(1, retries + 1):
            if current_sha is None:
                # Read latest sha
                _, latest_sha = self.read_file(clean_path)
                current_sha = latest_sha

            payload: Dict[str, Any] = {
                "message": message or f"update {clean_path}",
                "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
                "branch": self.branch,
            }
            if current_sha:
                payload["sha"] = current_sha

            status, resp = self._req(url, method="PUT", data=payload)
            if status in (200, 201):
                new_sha = resp.get("content", {}).get("sha")
                self.local_cache.write_file(clean_path, content)
                return True, new_sha
            elif status == 409:
                logger.warning(f"GitHub CAS conflict on {clean_path} (attempt {attempt}/{retries}). Re-reading...")
                _, current_sha = self.read_file(clean_path)
                time.sleep(0.5 * attempt)
            else:
                logger.error(f"GitHub write_file failed ({clean_path}) HTTP {status}: {resp}")
                break

        # Fallback: persist to local cache so data isn't lost
        self.local_cache.write_file(clean_path, content)
        return False, None

    def append_jsonl(self, path: str, record: Dict[str, Any], message: str = "") -> bool:
        clean_path = path.lstrip("/\\").replace("\\", "/")
        existing, sha = self.read_file(clean_path)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        new_content = (existing or "") + line
        ok, _ = self.write_file(clean_path, new_content, message=message or f"append to {clean_path}", sha=sha)
        return ok

    def upload_blob(self, path: str, content_bytes: bytes, message: str = "") -> bool:
        """Upload binary data via Git blob API and Contents API."""
        clean_path = path.lstrip("/\\").replace("\\", "/")
        payload = {
            "message": message or f"upload blob {clean_path}",
            "content": base64.b64encode(content_bytes).decode("utf-8"),
            "branch": self.branch,
        }
        _, sha = self.read_file(clean_path)
        if sha:
            payload["sha"] = sha
        url = f"{self.api_base}/contents/{clean_path}"
        status, _ = self._req(url, method="PUT", data=payload)
        return status in (200, 201)


def get_default_backend() -> StateBackend:
    """Instantiate the active backend depending on environment configuration."""
    repo = os.environ.get("STATE_REPO")
    token = os.environ.get("STATE_REPO_TOKEN") or os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")

    if not repo or not token:
        # Check PROJECT_ROOT / .env
        from .config import PROJECT_ROOT
        env_file = PROJECT_ROOT / ".env"
        if env_file.exists():
            for line in open(env_file, encoding="utf-8"):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k == "STATE_REPO" and not repo:
                        repo = v
                    elif k in ("STATE_REPO_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN") and not token:
                        token = v

    if repo and token and not os.environ.get("UPWORK_TEST_MODE"):
        try:
            return GitHubBackend(repo=repo, token=token)
        except Exception as e:
            logger.warning(f"Failed to initialize GitHubBackend: {e}. Falling back to FileBackend.")

    return FileBackend(ENGINE_DIR)
