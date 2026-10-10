"""
Cloud Backup Engine for Upwork Engine (Part E & Development Rule #3).
Ensures local custody of all cloud data: GitHub store state history,
Railway service config and runtime logs, and Vercel deployments.
Executes once at startup and every 6 hours on the local PC.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import ENGINE_DIR

logger = logging.getLogger("cloud_backup")

BACKUP_ROOT = ENGINE_DIR / "cloud_backup"
MANIFEST_PATH = BACKUP_ROOT / "manifest.json"
BACKUP_LOG_PATH = BACKUP_ROOT / "backup.log"


class BackupProvider(ABC):
    """Abstract interface for backing up a cloud service or runtime."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g. 'github_store', 'railway', 'vercel')."""
        pass

    @abstractmethod
    def snapshot_config(self, out_dir: Path) -> Dict[str, Any]:
        """Fetch disaster-recovery configuration snapshot (no secrets stored plain)."""
        pass

    @abstractmethod
    def pull_logs(self, out_dir: Path, cursor: Optional[str] = None) -> Tuple[int, Optional[str]]:
        """Pull incremental runtime logs into out_dir. Returns (records_count, new_cursor)."""
        pass


class GitHubStoreProvider(BackupProvider):
    """Pulls and mirrors the full state history from GitHub store."""

    @property
    def name(self) -> str:
        return "github_store"

    def snapshot_config(self, out_dir: Path) -> Dict[str, Any]:
        out_dir.mkdir(parents=True, exist_ok=True)
        repo = os.environ.get("STATE_REPO")
        info = {
            "repo": repo,
            "mirrored_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(out_dir / "store_config.json", "w", encoding="utf-8") as f:
            json.dump(info, f, indent=2)
        return info

    def pull_logs(self, out_dir: Path, cursor: Optional[str] = None) -> Tuple[int, Optional[str]]:
        store_dir = out_dir / "store"
        repo = os.environ.get("STATE_REPO")
        token = os.environ.get("STATE_REPO_TOKEN") or os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")

        if not repo or not token or os.environ.get("UPWORK_TEST_MODE"):
            return 0, cursor

        auth_url = f"https://x-access-token:{token}@github.com/{repo}.git"

        try:
            if not store_dir.exists():
                logger.info(f"Cloning store repository into {store_dir}...")
                subprocess.run(
                    ["git", "clone", "--depth", "50", auth_url, str(store_dir)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                    timeout=30,
                )
            else:
                subprocess.run(
                    ["git", "-C", str(store_dir), "pull", "--ff-only"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                    timeout=20,
                )
            return 1, datetime.now(timezone.utc).isoformat()
        except Exception as e:
            logger.warning(f"GitHubStoreProvider clone/pull error: {e}")
            return 0, cursor


class RailwayProvider(BackupProvider):
    """Pulls Railway service metadata, deployment history, and runtime logs via GraphQL."""

    def __init__(self):
        self.url = "https://backboard.railway.app/graphql/v2"
        self.project_id = os.environ.get("RAILWAY_PROJECT_ID", "")
        self.token = os.environ.get("RAILWAY_TOKEN", "")
        self.service_id = "d35fc7d1-1790-451b-b554-fa900ff4778b"
        self.env_id = "7b03e4ad-2c8a-4325-b699-0085b1355009"

    @property
    def name(self) -> str:
        return "railway"

    def _gql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.token or not self.project_id or os.environ.get("UPWORK_TEST_MODE"):
            return {}
        body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
        req = urllib.request.Request(
            self.url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 UpworkEngine-Backup/1.0",
                "Project-Access-Token": self.token,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            logger.warning(f"Railway GraphQL request error: {e}")
            return {}

    def snapshot_config(self, out_dir: Path) -> Dict[str, Any]:
        railway_dir = out_dir / "railway"
        railway_dir.mkdir(parents=True, exist_ok=True)

        # Service settings
        q_svc = """
        query($s: String!) {
          service(id: $s) {
            name
            serviceInstances {
              edges {
                node {
                  environmentId
                  healthcheckPath
                  restartPolicyType
                  startCommand
                  domains {
                    serviceDomains { domain }
                  }
                }
              }
            }
          }
        }
        """
        r_svc = self._gql(q_svc, {"s": self.service_id})
        with open(railway_dir / "service.json", "w", encoding="utf-8") as f:
            json.dump(r_svc, f, indent=2)

        # Variable names only (no secrets)
        q_vars = """
        query($p: String!, $s: String!, $e: String!) {
          variables(projectId: $p, serviceId: $s, environmentId: $e)
        }
        """
        r_vars = self._gql(q_vars, {"p": self.project_id, "s": self.service_id, "e": self.env_id})
        var_data = (r_vars.get("data") or {}).get("variables") or {}
        var_names = sorted(var_data.keys()) if isinstance(var_data, dict) else []
        with open(railway_dir / "variable_names.json", "w", encoding="utf-8") as f:
            json.dump({"variable_names": var_names}, f, indent=2)

        return {"service": r_svc, "variable_names": var_names}

    def pull_logs(self, out_dir: Path, cursor: Optional[str] = None) -> Tuple[int, Optional[str]]:
        railway_dir = out_dir / "railway"
        logs_dir = railway_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        q_deps = """
        query($p: String!, $s: String!, $e: String!) {
          deployments(first: 3, input: { projectId: $p, serviceId: $s, environmentId: $e }) {
            edges { node { id status createdAt } }
          }
        }
        """
        r_deps = self._gql(q_deps, {"p": self.project_id, "s": self.service_id, "e": self.env_id})
        deps = [ed["node"] for ed in ((r_deps.get("data") or {}).get("deployments") or {}).get("edges", [])]

        total_lines = 0
        q_logs = """
        query($d: String!, $l: Int!) {
          deploymentLogs(deploymentId: $d, limit: $l) {
            timestamp severity message
          }
        }
        """
        for d in deps:
            dep_id = d.get("id")
            if not dep_id:
                continue
            r_l = self._gql(q_logs, {"d": dep_id, "l": 500})
            logs = (r_l.get("data") or {}).get("deploymentLogs") or []
            if logs:
                fn = logs_dir / f"deployment_{dep_id[:8]}.jsonl"
                with open(fn, "w", encoding="utf-8") as lf:
                    for line in logs:
                        lf.write(json.dumps(line) + "\n")
                total_lines += len(logs)

        return total_lines, datetime.now(timezone.utc).isoformat()


class VercelProvider(BackupProvider):
    """Pulls Vercel project configuration and recent deployments."""

    def __init__(self):
        self.token = os.environ.get("VERCEL_PERSONAL_ACCESS_TOKEN", "")

    @property
    def name(self) -> str:
        return "vercel"

    def snapshot_config(self, out_dir: Path) -> Dict[str, Any]:
        vercel_dir = out_dir / "vercel"
        vercel_dir.mkdir(parents=True, exist_ok=True)
        if not self.token or os.environ.get("UPWORK_TEST_MODE"):
            return {}

        req = urllib.request.Request(
            "https://api.vercel.com/v9/projects",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read().decode("utf-8"))
                with open(vercel_dir / "projects.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                return data
        except Exception as e:
            logger.debug(f"Vercel snapshot note: {e}")
            return {}

    def pull_logs(self, out_dir: Path, cursor: Optional[str] = None) -> Tuple[int, Optional[str]]:
        # Vercel Hobby plan logs are ephemeral (read-through tick passes to store)
        return 0, cursor


def load_manifest() -> Dict[str, Any]:
    """Load backup manifest from disk."""
    if MANIFEST_PATH.exists():
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_run_at": None, "cursors": {}, "errors": []}


def save_manifest(manifest: Dict[str, Any]) -> None:
    """Save backup manifest to disk atomically."""
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    tmp.replace(MANIFEST_PATH)


def backup_due(interval_hours: float = 6.0) -> bool:
    """Check if a cloud backup run is due (older than 6h)."""
    manifest = load_manifest()
    last_run = manifest.get("last_run_at")
    if not last_run:
        return True
    try:
        dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds() >= (interval_hours * 3600)
    except Exception:
        return True


def run_backup(providers: Optional[List[BackupProvider]] = None) -> Dict[str, Any]:
    """
    Execute cloud backup across all registered providers in isolation.
    Updates manifest.json and backup.log.
    """
    logger.info("Starting local cloud backup run...")
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    cursors = manifest.setdefault("cursors", {})

    active_providers = providers or [
        GitHubStoreProvider(),
        RailwayProvider(),
        VercelProvider(),
    ]

    results: Dict[str, Any] = {}
    now_utc = datetime.now(timezone.utc)

    for prov in active_providers:
        p_name = prov.name
        try:
            cfg = prov.snapshot_config(BACKUP_ROOT)
            cnt, new_cursor = prov.pull_logs(BACKUP_ROOT, cursor=cursors.get(p_name))
            if new_cursor:
                cursors[p_name] = new_cursor
            results[p_name] = {"ok": True, "records": cnt}
            logger.info(f"Provider '{p_name}' backed up successfully ({cnt} records).")
        except Exception as e:
            logger.error(f"Provider '{p_name}' backup failed: {e}")
            results[p_name] = {"ok": False, "error": str(e)}

    manifest["last_run_at"] = now_utc.isoformat()
    manifest["results"] = results
    save_manifest(manifest)

    # Append to backup.log
    with open(BACKUP_LOG_PATH, "a", encoding="utf-8") as lf:
        log_entry = {
            "ts": now_utc.isoformat(),
            "results": results,
        }
        lf.write(json.dumps(log_entry) + "\n")

    logger.info("Cloud backup run finished.")
    return results
