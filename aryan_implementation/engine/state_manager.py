"""
State management and schema enforcement for the Upwork engine.
Manages atomic I/O, schemas validation, and state initialization.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import jsonschema

from .config import (
    STATE_DIR,
    ENGINE_DIR,
    PAYLOADS_DIR,
    BACKUP_DIR,
    JOBS_SCHEMA_PATH,
    STATE_SCHEMA_PATH,
    CAMPAIGNS_SCHEMA_PATH,
    CAMPAIGNS_EXAMPLE_PATH,
    SCORING_EXAMPLE_PATH,
    DEFAULT_MONTHLY_CONNECTS_BUDGET,
)

logger = logging.getLogger("upwork_engine")


class StateManager:
    """Manages reading, writing, and validating engine state outside the git repository."""

    def __init__(self, state_dir: Optional[Union[str, Path]] = None):
        self.state_dir = Path(state_dir) if state_dir else STATE_DIR
        self.jobs_file = self.state_dir / "jobs.json"
        self.state_file = self.state_dir / "state.json"
        self.campaigns_file = self.state_dir / "campaigns.json"
        self.scoring_file = self.state_dir / "scoring.json"

        # Schemas
        self._jobs_schema: Optional[Dict[str, Any]] = None
        self._state_schema: Optional[Dict[str, Any]] = None
        self._campaigns_schema: Optional[Dict[str, Any]] = None

    @property
    def jobs_schema(self) -> Dict[str, Any]:
        if self._jobs_schema is None:
            with open(JOBS_SCHEMA_PATH, "r", encoding="utf-8") as f:
                self._jobs_schema = json.load(f)
        return self._jobs_schema

    @property
    def state_schema(self) -> Dict[str, Any]:
        if self._state_schema is None:
            with open(STATE_SCHEMA_PATH, "r", encoding="utf-8") as f:
                self._state_schema = json.load(f)
        return self._state_schema

    @property
    def campaigns_schema(self) -> Dict[str, Any]:
        if self._campaigns_schema is None:
            with open(CAMPAIGNS_SCHEMA_PATH, "r", encoding="utf-8") as f:
                self._campaigns_schema = json.load(f)
        return self._campaigns_schema

    def init_state_directory(self, force: bool = False) -> Dict[str, Any]:
        """Bootstrap the private state directory from templates."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        PAYLOADS_DIR.mkdir(parents=True, exist_ok=True)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

        results = {}

        # 1. jobs.json
        if not self.jobs_file.exists() or force:
            initial_jobs: Dict[str, Any] = {}
            self._atomic_write(self.jobs_file, initial_jobs)
            results["jobs.json"] = "created"
        else:
            results["jobs.json"] = "already_exists"

        # 2. campaigns.json
        if not self.campaigns_file.exists() or force:
            with open(CAMPAIGNS_EXAMPLE_PATH, "r", encoding="utf-8") as f:
                campaigns_data = json.load(f)
            self.validate_campaigns(campaigns_data)
            self._atomic_write(self.campaigns_file, campaigns_data)
            results["campaigns.json"] = "created"
        else:
            results["campaigns.json"] = "already_exists"

        # 3. scoring.json
        if not self.scoring_file.exists() or force:
            with open(SCORING_EXAMPLE_PATH, "r", encoding="utf-8") as f:
                scoring_data = json.load(f)
            self._atomic_write(self.scoring_file, scoring_data)
            results["scoring.json"] = "created"
        else:
            results["scoring.json"] = "already_exists"

        # 4. state.json (singleton)
        if not self.state_file.exists() or force:
            initial_state = {
                "last_run_at": None,
                "last_run_id": None,
                "runs_today": 0,
                "applies_today": 0,
                "applies_today_by_campaign": {
                    "claude-implementation": 0,
                    "mcp-integrations": 0,
                    "rag-knowledge": 0,
                    "ai-agents": 0,
                    "n8n-automation": 0,
                    "integrations-repair": 0,
                    "ai-training-coaching": 0,
                },
                "connects_balance": 110,
                "connects_spent_month": 0,
                "connects_budget_month": DEFAULT_MONTHLY_CONNECTS_BUDGET,
                "badge_on": False,
                "scoring_version": "1.0",
                "campaigns_version": "1.0.0",
                "incidents": [],
                "kill_switch": False,
                "mcp_tool_count_observed": 0,
            }
            self.validate_state(initial_state)
            self._atomic_write(self.state_file, initial_state)
            results["state.json"] = "created"
        else:
            results["state.json"] = "already_exists"

        return results

    def _atomic_write(self, filepath: Path, data: Any) -> None:
        """Atomically write JSON data to file using a temporary file."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        temp_file = filepath.with_suffix(f".tmp.{os.getpid()}")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            shutil.move(str(temp_file), str(filepath))
        except Exception:
            if temp_file.exists():
                temp_file.unlink()
            raise

    # Validation methods
    def validate_job(self, job_record: Dict[str, Any]) -> None:
        """Validate an individual job record against jobs.schema.json."""
        jsonschema.validate(instance=job_record, schema=self.jobs_schema)

    def validate_state(self, state_data: Dict[str, Any]) -> None:
        """Validate singleton state data against state.schema.json."""
        jsonschema.validate(instance=state_data, schema=self.state_schema)

    def validate_campaigns(self, campaigns_data: Dict[str, Any]) -> None:
        """Validate campaigns against campaigns.schema.json."""
        jsonschema.validate(instance=campaigns_data, schema=self.campaigns_schema)

    # Load & Save
    def load_jobs(self) -> Dict[str, Dict[str, Any]]:
        if not self.jobs_file.exists():
            return {}
        with open(self.jobs_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            # Convert list of jobs to dict keyed by job_id
            return {job["job_id"]: job for job in data if "job_id" in job}
        return data

    def save_jobs(self, jobs: Dict[str, Dict[str, Any]]) -> None:
        self._atomic_write(self.jobs_file, jobs)

    def load_state(self) -> Dict[str, Any]:
        if not self.state_file.exists():
            self.init_state_directory()
        with open(self.state_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_state(self, state_data: Dict[str, Any]) -> None:
        self.validate_state(state_data)
        self._atomic_write(self.state_file, state_data)

    def load_campaigns(self) -> Dict[str, Any]:
        if not self.campaigns_file.exists():
            self.init_state_directory()
        with open(self.campaigns_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_campaigns(self, campaigns_data: Dict[str, Any]) -> None:
        self.validate_campaigns(campaigns_data)
        self._atomic_write(self.campaigns_file, campaigns_data)

    def load_scoring(self) -> Dict[str, Any]:
        if not self.scoring_file.exists():
            self.init_state_directory()
        with open(self.scoring_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_scoring(self, scoring_data: Dict[str, Any]) -> None:
        self._atomic_write(self.scoring_file, scoring_data)

    def toggle_kill_switch(self, enabled: bool, reason: str = "") -> bool:
        """Set or unset the kill switch."""
        state = self.load_state()
        state["kill_switch"] = enabled
        if reason:
            incidents = state.setdefault("incidents", [])
            incidents.append({
                "at": datetime.now(timezone.utc).isoformat(),
                "type": "other",
                "detail": f"kill_switch={enabled}: {reason}",
                "resolved": not enabled,
            })
        self.save_state(state)
        return enabled

    def add_incident(self, incident_type: str, detail: str) -> None:
        """Log an operational incident to state.json."""
        state = self.load_state()
        incidents = state.setdefault("incidents", [])
        incidents.append({
            "at": datetime.now(timezone.utc).isoformat(),
            "type": incident_type,
            "detail": detail,
            "resolved": False,
        })
        # If 3 or more unresolved incidents or any auth error, trip kill_switch
        unresolved = [inc for inc in incidents if not inc.get("resolved", False)]
        if len(unresolved) >= 3 or incident_type == "auth":
            state["kill_switch"] = True
        self.save_state(state)
