"""
Nightly rebake analytics and outcome reconciliation engine for Aryan Upwork pipeline.
Implements the 22:30 IST rebake runbook and ledger reconciliation per agent_instructions/evening_rebake.md.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .mcp_client import UpworkMCPClient
from .state_manager import StateManager

logger = logging.getLogger("upwork_engine")


class RebakeEngine:
    """Performs evening rebake, outcome tracking, ledger reconciliation and digest generation."""

    def __init__(self, mcp_client: UpworkMCPClient, state_mgr: StateManager):
        self.mcp = mcp_client
        self.state_mgr = state_mgr

    def run_rebake(self, run_id: str) -> Dict[str, Any]:
        """Execute the full nightly rebake loop."""
        state = self.state_mgr.load_state()
        jobs = self.state_mgr.load_jobs()
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Proposal status reconciliation
        props_res = self.mcp.call_tool("list_freelancer_proposals", "list", {}, run_id=run_id, state=state)
        proposals_data = props_res.get("data", {}).get("proposals", []) if props_res.get("ok") else []
        proposals_map = {p.get("job_reference") or p.get("job_id"): p for p in proposals_data}

        updated_outcomes = 0
        for jid, job in jobs.items():
            if job.get("status") in ("submitted", "viewed", "interview", "offer"):
                prop = proposals_map.get(jid)
                if prop:
                    new_status = prop.get("status", job["status"])
                    if new_status != job["status"]:
                        job["status"] = new_status
                        job.setdefault("outcome", {})[f"{new_status}_at"] = now_iso
                        updated_outcomes += 1

        # 2. Check Invitations
        invites_res = self.mcp.call_tool("list_freelancer_proposals", "invitations", {}, run_id=run_id, state=state)
        invites = invites_res.get("data", {}).get("invitations", []) if invites_res.get("ok") else []

        # 3. Freelancer Dashboard Telemetry
        dash_res = self.mcp.call_tool("get_freelancer_dashboard", "check", {}, run_id=run_id, state=state)
        dash = dash_res.get("data", {}) if dash_res.get("ok") else {}

        # 4. Connects Ledger Check
        balance_res = self.mcp.call_tool("get_profile", "connects_balance", {}, run_id=run_id, state=state)
        actual_balance = balance_res.get("data", {}).get("balance", state.get("connects_balance", 0)) if balance_res.get("ok") else state.get("connects_balance", 0)

        expected_balance = state.get("connects_balance", 0)
        ledger_delta = abs(actual_balance - expected_balance)
        ledger_incident = None
        if ledger_delta > 2:
            ledger_incident = f"Connects ledger drift: expected {expected_balance}, observed {actual_balance} (delta={ledger_delta})"
            incidents = state.setdefault("incidents", [])
            incidents.append({
                "at": now_iso,
                "type": "ledger",
                "detail": ledger_incident,
                "resolved": False,
            })

        # Update balance to true observed
        state["connects_balance"] = actual_balance

        # 5. Funnel aggregates
        submitted_jobs = [j for j in jobs.values() if j.get("status") in ("submitted", "viewed", "interview", "hired", "offer")]
        drafted_jobs = [j for j in jobs.values() if j.get("status") in ("drafted", "in_review")]
        rejected_jobs = [j for j in jobs.values() if j.get("status") == "rejected_by_aryan"]

        # Calculate score band metrics
        band_80_plus = sum(1 for j in submitted_jobs if j.get("score", 0) >= 80)
        band_70_79 = sum(1 for j in submitted_jobs if 70 <= j.get("score", 0) < 80)
        band_below_70 = sum(1 for j in submitted_jobs if j.get("score", 0) < 70)

        # 6. Incident and kill switch audit
        incidents = state.get("incidents", [])
        unresolved = [inc for inc in incidents if not inc.get("resolved", False)]
        if len(unresolved) >= 3:
            state["kill_switch"] = True

        # Save state and jobs
        self.state_mgr.save_jobs(jobs)
        self.state_mgr.save_state(state)

        # 7. Generate 10-line Daily Digest
        digest_lines = [
            f"=== NIGHTLY REBAKE DIGEST [{now_iso[:10]}] ===",
            f"Connects Balance: {actual_balance} (Monthly Spent: {state.get('connects_spent_month', 0)} / Budget: {state.get('connects_budget_month', 250)})",
            f"Today Runs: {state.get('runs_today', 0)} | Updated Outcomes: {updated_outcomes}",
            f"Funnel: {len(drafted_jobs)} in review | {len(submitted_jobs)} submitted | {len(rejected_jobs)} rejected by Aryan",
            f"Score Bands: 80+ ({band_80_plus}) | 70-79 ({band_70_79}) | <70 ({band_below_70})",
            f"Pending Invitations: {len(invites)} (requires human action)",
            f"Profile Telemetry: {dash.get('profile_views', 0)} views | {dash.get('proposals_sent', 0)} sent",
            f"Incidents: {len(unresolved)} unresolved | Kill Switch: {'ACTIVE' if state.get('kill_switch') else 'OFF'}",
            f"Ledger Status: {'DRIFT DETECTED: ' + ledger_incident if ledger_incident else 'OK'}",
            "===========================================",
        ]
        digest = "\n".join(digest_lines)

        return {
            "run_id": run_id,
            "ts": now_iso,
            "actual_balance": actual_balance,
            "updated_outcomes": updated_outcomes,
            "pending_invites": len(invites),
            "unresolved_incidents": len(unresolved),
            "kill_switch": state.get("kill_switch", False),
            "digest": digest,
        }
