"""
Campaign and scoring configuration editor with schema validation and versioned backups.
Implements skills/upwork-campaign-editor.
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import BACKUP_DIR
from .state_manager import StateManager
from .vet import score_job, check_disqualifiers

logger = logging.getLogger("upwork_engine")


class CampaignEditor:
    """Manages deterministic, versioned edits to campaign configurations."""

    def __init__(self, state_mgr: StateManager):
        self.state_mgr = state_mgr

    def update_campaign(
        self,
        campaign_id: str,
        updates: Dict[str, Any],
        changelog: str = "",
    ) -> Dict[str, Any]:
        """Update a campaign's fields with backup and schema validation."""
        campaigns_data = self.state_mgr.load_campaigns()
        campaigns = campaigns_data.get("campaigns", [])

        target_campaign = None
        for camp in campaigns:
            if camp.get("id") == campaign_id:
                target_campaign = camp
                break

        if not target_campaign:
            return {"ok": False, "message": f"Campaign '{campaign_id}' not found"}

        # 1. Create versioned backup
        now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_file = BACKUP_DIR / f"campaigns_{now_str}.json"
        with open(backup_file, "w", encoding="utf-8") as bf:
            json.dump(campaigns_data, bf, indent=2, ensure_ascii=False)

        # 2. Apply updates
        for k, v in updates.items():
            target_campaign[k] = v
        target_campaign["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Update global version / changelog
        if changelog:
            campaigns_data.setdefault("changelog", []).append({
                "ts": datetime.now(timezone.utc).isoformat(),
                "campaign_id": campaign_id,
                "notes": changelog,
            })

        # 3. Validate against schema
        try:
            self.state_mgr.validate_campaigns(campaigns_data)
        except Exception as e:
            return {"ok": False, "message": f"Validation failed: {e}", "backup": str(backup_file)}

        # 4. Save
        self.state_mgr.save_campaigns(campaigns_data)
        return {
            "ok": True,
            "campaign_id": campaign_id,
            "backup_file": str(backup_file),
            "updated_campaign": target_campaign,
        }

    def dry_run_scoring_changes(self, new_scoring_data: Dict[str, Any]) -> Dict[str, Any]:
        """Run candidate scoring changes against historical jobs in state store."""
        jobs = self.state_mgr.load_jobs()
        if not jobs:
            return {"ok": True, "message": "No historical jobs in state store to evaluate"}

        old_decisions = {"APPLY": 0, "REVIEW": 0, "SKIP": 0}
        new_decisions = {"APPLY": 0, "REVIEW": 0, "SKIP": 0}
        flips = []

        threshold = new_scoring_data.get("thresholds", {}).get("apply", 70)

        for jid, job in jobs.items():
            prior_dec = job.get("decision", "SKIP")
            old_decisions[prior_dec] = old_decisions.get(prior_dec, 0) + 1

            disq, d_id, _ = check_disqualifiers(job)
            if disq:
                new_dec = "SKIP"
            else:
                score_res = score_job(job, campaign_threshold=threshold)
                new_dec = score_res["decision"]

            new_decisions[new_dec] = new_decisions.get(new_dec, 0) + 1
            if prior_dec != new_dec:
                flips.append({
                    "job_id": jid,
                    "title": job.get("title", ""),
                    "from": prior_dec,
                    "to": new_dec,
                })

        return {
            "ok": True,
            "evaluated_jobs_count": len(jobs),
            "old_distribution": old_decisions,
            "new_distribution": new_decisions,
            "flips_count": len(flips),
            "flips_sample": flips[:10],
        }
