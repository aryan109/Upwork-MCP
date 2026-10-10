"""
Migrate local state directory history to the GitHub state store.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from aryan_implementation.engine.config import STATE_DIR, ENGINE_DIR
from aryan_implementation.engine.state_backend import get_default_backend, GitHubBackend

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("state_migration")


def main():
    backend = get_default_backend()
    logger.info(f"Target backend: {backend.__class__.__name__}")

    # 1. State
    local_state_file = STATE_DIR / "state.json"
    if local_state_file.exists():
        with open(local_state_file, "r", encoding="utf-8") as f:
            state_data = json.load(f)
        # Cap incidents at 50
        if "incidents" in state_data and len(state_data["incidents"]) > 50:
            state_data["incidents"] = state_data["incidents"][-50:]
        backend.write_json("state.json", state_data, message="migrate local state.json")
        logger.info("Migrated state.json")

    # 2. Jobs
    local_jobs_file = STATE_DIR / "jobs.json"
    if local_jobs_file.exists():
        with open(local_jobs_file, "r", encoding="utf-8") as f:
            jobs_data = json.load(f)
        if isinstance(jobs_data, list):
            jobs_data = {j["job_id"]: j for j in jobs_data if "job_id" in j}
        backend.write_json("jobs.json", jobs_data, message="migrate local jobs.json")
        logger.info(f"Migrated jobs.json ({len(jobs_data)} jobs)")

    # 3. Rejected
    local_rejected_file = STATE_DIR / "rejected_jobs.json"
    if local_rejected_file.exists():
        with open(local_rejected_file, "r", encoding="utf-8") as f:
            rej_data = json.load(f)
        backend.write_json("jobs/rejected.json", rej_data, message="migrate local rejected_jobs.json")
        logger.info("Migrated jobs/rejected.json")

    # 4. OAuth tokens
    oauth_file = ENGINE_DIR / "secrets" / "upwork_oauth.json"
    if oauth_file.exists():
        with open(oauth_file, "r", encoding="utf-8") as f:
            oauth_data = json.load(f)
        backend.write_json("secrets/upwork_oauth.json", oauth_data, message="migrate upwork_oauth.json")
        logger.info("Migrated secrets/upwork_oauth.json")

    logger.info("State migration complete.")


if __name__ == "__main__":
    main()
