"""
Job discovery and candidate pre-filtering engine for Aryan Upwork pipeline.
Implements the discovery loop, deduplication, and detail fetch capping from skills/upwork-hunt.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from .config import MAX_SEARCHES_PER_PASS, MAX_DETAIL_FETCHES_PER_PASS, PAYLOADS_DIR
from .mcp_client import UpworkMCPClient
from .state_manager import StateManager
from .vet import CAPABILITY_DISQUALIFIERS

logger = logging.getLogger("upwork_engine")


class JobHunter:
    """Discovers and deduplicates Upwork jobs across campaigns."""

    def __init__(self, mcp_client: UpworkMCPClient, state_mgr: StateManager):
        self.mcp = mcp_client
        self.state_mgr = state_mgr

    def run_hunt(
        self,
        run_id: str,
        max_searches: int = MAX_SEARCHES_PER_PASS,
        max_details: int = MAX_DETAIL_FETCHES_PER_PASS,
        include_best_match: bool = False,
    ) -> Dict[str, Any]:
        """Execute a full discovery pass across active campaigns."""
        state = self.state_mgr.load_state()
        campaigns_data = self.state_mgr.load_campaigns()
        campaigns = campaigns_data.get("campaigns", [])
        existing_jobs = self.state_mgr.load_jobs()

        # Check kill switch
        kill_switch_active = state.get("kill_switch", False)

        # 1. Lookback window
        last_run_str = state.get("last_run_at")
        now_utc = datetime.now(timezone.utc)
        if last_run_str:
            try:
                last_dt = datetime.fromisoformat(last_run_str.replace("Z", "+00:00"))
                from_dt = max(now_utc - timedelta(hours=72), last_dt - timedelta(minutes=15))
            except Exception:
                from_dt = now_utc - timedelta(hours=24)
        else:
            from_dt = now_utc - timedelta(hours=24)
        from_date_iso = from_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        searches_used = 0
        discovered_candidates: Dict[str, Dict[str, Any]] = {}
        mismatches_observed: List[str] = []

        # Sort campaigns by priority
        active_campaigns = [c for c in campaigns if c.get("active", True)]
        active_campaigns.sort(key=lambda x: x.get("priority", 999))

        for camp in active_campaigns:
            if searches_used >= max_searches:
                break

            camp_id = camp.get("id", "default")
            queries = camp.get("queries", [])
            title_filters = camp.get("title_filters", [])

            # A. smart_search most_recent
            for q in queries:
                if searches_used >= max_searches:
                    break
                params = {
                    "mode": "most_recent",
                    "query": q,
                    "from_date": from_date_iso,
                    "days_posted": 1,
                }
                res = self.mcp.call_tool("find_jobs", "smart_search", params, run_id=run_id, campaign=camp_id, state=state)
                searches_used += 1

                if res.get("ok"):
                    data = res.get("data", {})
                    ignored = data.get("filters_ignored", [])
                    if ignored:
                        mismatches_observed.extend(ignored)
                    jobs_found = data.get("jobs", [])
                    for j in jobs_found:
                        jid = j.get("job_id") or j.get("id")
                        if jid and jid not in discovered_candidates:
                            j["matched_campaign"] = camp_id
                            discovered_candidates[jid] = j

            # B. Optional best_match (morning pass)
            if include_best_match:
                for q in queries[:2]:
                    if searches_used >= max_searches:
                        break
                    params = {"mode": "best_match", "query": q}
                    res = self.mcp.call_tool("find_jobs", "smart_search", params, run_id=run_id, campaign=camp_id, state=state)
                    searches_used += 1
                    if res.get("ok"):
                        jobs_found = res.get("data", {}).get("jobs", [])
                        for j in jobs_found:
                            jid = j.get("job_id") or j.get("id")
                            if jid and jid not in discovered_candidates:
                                j["matched_campaign"] = camp_id
                                discovered_candidates[jid] = j

            # C. title_filters with search
            for tf in title_filters:
                if searches_used >= max_searches:
                    break
                params = {
                    "title": tf,
                    "verified_payment_only": True,
                    "days_posted": 2,
                }
                res = self.mcp.call_tool("find_jobs", "search", params, run_id=run_id, campaign=camp_id, state=state)
                searches_used += 1
                if res.get("ok"):
                    jobs_found = res.get("data", {}).get("jobs", [])
                    for j in jobs_found:
                        jid = j.get("job_id") or j.get("id")
                        if jid and jid not in discovered_candidates:
                            j["matched_campaign"] = camp_id
                            discovered_candidates[jid] = j

        # 2. Dedup & Pre-filtering
        survivors: List[Tuple[str, Dict[str, Any]]] = []
        new_count = 0
        refreshed_count = 0
        pre_filtered_count = 0

        for jid, job_summary in discovered_candidates.items():
            if jid in existing_jobs:
                existing = existing_jobs[jid]
                # Check if eligible for refresh
                status = existing.get("status")
                last_checked = existing.get("last_checked_at")
                if status in ("discovered", "scored") and last_checked:
                    try:
                        last_dt = datetime.fromisoformat(last_checked.replace("Z", "+00:00"))
                        if now_utc - last_dt > timedelta(hours=6):
                            survivors.append((jid, job_summary))
                            refreshed_count += 1
                            continue
                    except Exception:
                        pass
                continue

            # Cheap list-level pre-filter
            title = str(job_summary.get("title", "")).lower()
            if job_summary.get("applied") is True:
                pre_filtered_count += 1
                continue

            # Obvious capability gate check
            if any(re.search(pat, title) for pat in CAPABILITY_DISQUALIFIERS):
                pre_filtered_count += 1
                continue

            # Low budget check
            budget = job_summary.get("budget_fixed") or job_summary.get("budget", {}).get("amount")
            hourly_max = job_summary.get("hourly_max") or job_summary.get("hourly_budget", {}).get("max")
            if budget is not None and float(budget) < 100.0:
                pre_filtered_count += 1
                continue
            if hourly_max is not None and float(hourly_max) < 25.0:
                pre_filtered_count += 1
                continue

            # Excluded terms
            excluded = ["cold email", "deliverability", "gohighlevel", "clay", "apollo", "smartlead", "instantly"]
            if any(term in title for term in excluded):
                pre_filtered_count += 1
                continue

            survivors.append((jid, job_summary))
            new_count += 1

        # 3. Detail fetching capped at max_details
        details_fetched = 0
        final_discovered_records: List[Dict[str, Any]] = []

        for jid, summary in survivors[:max_details]:
            detail_res = self.mcp.call_tool("find_jobs", "get", {"job_id": jid}, run_id=run_id, state=state)
            details_fetched += 1

            if detail_res.get("ok"):
                detail_data = detail_res.get("data", {})
                # Merge summary and detail
                merged = {**summary, **detail_data}
                merged["job_id"] = jid
                merged["first_seen_at"] = merged.get("first_seen_at") or now_utc.isoformat()
                merged["last_checked_at"] = now_utc.isoformat()
                merged["status"] = "discovered"
                merged["campaign"] = summary.get("matched_campaign", "claude-implementation")

                # Save raw payload to payloads dir
                try:
                    payload_path = PAYLOADS_DIR / f"{jid.replace('~', '_')}.json"
                    with open(payload_path, "w", encoding="utf-8") as pf:
                        json.dump(detail_data, pf, indent=2, ensure_ascii=False)
                except Exception as e:
                    logger.warning(f"Could not persist raw payload: {e}")

                existing_jobs[jid] = merged
                final_discovered_records.append(merged)

        # 4. Save updated jobs and state
        self.state_mgr.save_jobs(existing_jobs)
        state["last_run_at"] = now_utc.isoformat()
        state["last_run_id"] = run_id
        state["runs_today"] = state.get("runs_today", 0) + 1
        self.state_mgr.save_state(state)

        return {
            "run_id": run_id,
            "searches_used": searches_used,
            "candidates_found": len(discovered_candidates),
            "new": new_count,
            "refreshed": refreshed_count,
            "pre_filtered": pre_filtered_count,
            "detail_fetched": details_fetched,
            "records_ready_for_vet": [r["job_id"] for r in final_discovered_records],
            "mismatches": list(set(mismatches_observed)),
            "kill_switch_active": kill_switch_active,
        }
