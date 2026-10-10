"""
Initializes the private GitHub store repository 'upwork-engine-state'
and bootstraps initial directory layout per RESILIENCE_ANALYSIS_AND_PLAN.md.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Load .env
env_file = REPO_ROOT / ".env"
ENV = {}
if env_file.exists():
    for line in open(env_file, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            ENV[k.strip()] = v.strip().strip("'\"")

TOKEN = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN") or ENV.get("GITHUB_PERSONAL_ACCESS_TOKEN")
REPO_NAME = os.environ.get("STATE_REPO_NAME", "upwork-engine-state")


def req(url: str, method: str = "GET", data: dict = None) -> tuple:
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "UpworkEngine-StoreInit/1.0",
    }
    body = json.dumps(data).encode("utf-8") if data is not None else None
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_json = json.loads(e.read().decode("utf-8"))
        except Exception:
            err_json = {"error": str(e)}
        return e.code, err_data if 'err_data' in locals() else err_json
    except Exception as e:
        return 599, {"error": str(e)}


def main():
    if not TOKEN:
        print("ERROR: GITHUB_PERSONAL_ACCESS_TOKEN not found in environment or .env")
        sys.exit(1)

    print("Checking authenticated GitHub user...")
    status, user_data = req("https://api.github.com/user")
    if status != 200:
        print(f"Failed to authenticate with GitHub API (HTTP {status}): {user_data}")
        sys.exit(1)

    username = user_data.get("login")
    full_repo = f"{username}/{REPO_NAME}"
    print(f"Authenticated as: {username}. Target repository: {full_repo}")

    # Check if repo exists
    status, repo_info = req(f"https://api.github.com/repos/{full_repo}")
    if status == 404:
        print(f"Creating private repository: {full_repo}...")
        create_payload = {
            "name": REPO_NAME,
            "private": True,
            "description": "Shared state and audit store for Upwork Autonomous Engine",
            "auto_init": True,
        }
        status, repo_info = req("https://api.github.com/user/repos", method="POST", data=create_payload)
        if status not in (200, 201):
            print(f"Failed to create repository (HTTP {status}): {repo_info}")
            sys.exit(1)
        print("Repository successfully created.")
    elif status == 200:
        print(f"Repository {full_repo} already exists.")
    else:
        print(f"Unexpected response checking repository (HTTP {status}): {repo_info}")
        sys.exit(1)

    # Initialize layout files
    files_to_create = {
        "state.json": json.dumps({
            "runs_today": 0,
            "kill_switch": False,
            "incidents": [],
            "inbound_mode": "polling:railway",
            "scoring_version": "1.0",
            "campaigns_version": "1.0.0",
        }, indent=2),
        "lease.json": json.dumps({
            "resource": "hunter",
            "holder": None,
            "acquired_at": None,
            "expires_at": None,
        }, indent=2),
        "alerts.json": json.dumps({"active": {}, "history": []}, indent=2),
        "jobs/open.json": json.dumps({}, indent=2),
        "jobs/rejected.json": json.dumps({}, indent=2),
        "heartbeats/.gitkeep": "",
        "passes/.gitkeep": "",
        "logs/.gitkeep": "",
        "secrets/.gitkeep": "",
    }

    print("\nEnsuring repository structure...")
    for path, content in files_to_create.items():
        status, existing = req(f"https://api.github.com/repos/{full_repo}/contents/{path}")
        if status == 404:
            payload = {
                "message": f"init {path}",
                "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
                "branch": "main",
            }
            s, res = req(f"https://api.github.com/repos/{full_repo}/contents/{path}", method="PUT", data=payload)
            if s in (200, 201):
                print(f"  + Created: {path}")
            else:
                print(f"  ! Failed creating {path}: {res}")
        else:
            print(f"  ✓ Exists: {path}")

    print(f"\nGitHub State Store is ready: https://github.com/{full_repo}")
    print(f"Configure on tiers: STATE_REPO={full_repo}")


if __name__ == "__main__":
    main()
