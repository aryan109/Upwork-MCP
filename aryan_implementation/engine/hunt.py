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

from .config import (
    MAX_COMPETITION_PROPOSALS,
    MAX_DETAIL_FETCHES_PER_PASS,
    MAX_FIRST_MOVER_AGE_HOURS,
    MAX_SEARCHES_PER_PASS,
    PAYLOADS_DIR,
)
from .job_ledger import JobLedger, extract_job_timestamps, is_test_job
from .mcp_client import UpworkMCPClient
from .state_manager import StateManager
from .vet import CAPABILITY_DISQUALIFIERS, check_disqualifiers, normalize_job_record, parse_number, score_job

logger = logging.getLogger("upwork_engine")


class JobHunter:
    """Discovers and deduplicates Upwork jobs across campaigns."""

    def __init__(self, mcp_client: UpworkMCPClient, state_mgr: StateManager):
        self.mcp = mcp_client
        self.state_mgr = state_mgr
        self.ledger = JobLedger(self.state_mgr.state_dir)

    def run_hunt(
        self,
        run_id: str,
        max_searches: int = MAX_SEARCHES_PER_PASS,
        max_details: int = MAX_DETAIL_FETCHES_PER_PASS,
        include_best_match: bool = False,
        time_budget_s: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Execute a full discovery pass across active campaigns with time budget enforcement."""
        import time
        t_start = time.time()
        state = self.state_mgr.load_state()
        campaigns_data = self.state_mgr.load_campaigns()
        campaigns = campaigns_data.get("campaigns", [])
        existing_jobs = self.state_mgr.load_jobs()

        # Check kill switch
        kill_switch_active = state.get("kill_switch", False)
        now_utc = datetime.now(timezone.utc)

        searches_used = 0
        searches_ok = 0
        searches_failed = 0
        error_classes: List[str] = []
        discovered_candidates: Dict[str, Dict[str, Any]] = {}
        mismatches_observed: List[str] = []

        # Sort campaigns by global.priority_order, then campaign.priority, then id
        priority_order = campaigns_data.get("global", {}).get("priority_order") or []
        order_index = {cid: i for i, cid in enumerate(priority_order)}
        active_campaigns = [c for c in campaigns if c.get("active", True)]
        active_campaigns.sort(
            key=lambda x: (
                order_index.get(x.get("id"), 999),
                x.get("priority", 999),
                x.get("id", ""),
            )
        )

        search_tasks: List[Tuple[str, str, Dict[str, Any]]] = []
        # 1. Profile-matched smart_search feeds focused on most recent verified-payment posts
        lead_camp = active_campaigns[0].get("id", "claude-implementation") if active_campaigns else "claude-implementation"
        search_tasks.append((
            lead_camp,
            "smart_search",
            {"mode": "most_recent", "days_posted": 1, "verified_payment_only": True},
        ))
        if include_best_match:
            search_tasks.append((
                lead_camp,
                "smart_search",
                {"mode": "best_match", "days_posted": 1, "verified_payment_only": True},
            ))

        # 2. Campaign keyword & title searches via action="search" with low-competition (<20 proposals) & full details
        for camp in active_campaigns:
            camp_id = camp.get("id", "default")
            for tf in camp.get("title_filters", []) or []:
                search_tasks.append((
                    camp_id,
                    "search",
                    {
                        "title": tf,
                        "proposals_max": MAX_COMPETITION_PROPOSALS - 1,
                        "include_full_details": True,
                    },
                ))
            for q in camp.get("queries", []):
                search_tasks.append((
                    camp_id,
                    "search",
                    {
                        "query": q,
                        "sort": "recency",
                        "proposals_max": MAX_COMPETITION_PROPOSALS - 1,
                        "include_full_details": True,
                    },
                ))

        cursor = int(state.get("search_cursor") or 0)
        n_tasks = len(search_tasks)
        if n_tasks:
            cursor = cursor % n_tasks
            rotated = search_tasks[cursor:] + search_tasks[:cursor]
        else:
            rotated = []

        per_campaign_searches: Dict[str, int] = {}

        def _budget_exhausted() -> bool:
            if time_budget_s and (time.time() - t_start) >= (0.8 * time_budget_s):
                logger.info("Time budget reached 80%; stopping discovery searches early.")
                return True
            return False

        for camp_id, action, params in rotated:
            if searches_used >= max_searches or _budget_exhausted():
                break
            res = self.mcp.call_tool(
                "find_jobs",
                action,
                params,
                run_id=run_id,
                campaign=camp_id,
                state=state,
            )
            searches_used += 1
            per_campaign_searches[camp_id] = per_campaign_searches.get(camp_id, 0) + 1

            if res.get("ok"):
                searches_ok += 1
                data = res.get("data", {})
                if not isinstance(data, dict):
                    data = {}
                ignored = data.get("filters_ignored", [])
                if ignored:
                    mismatches_observed.extend(ignored)
                jobs_found = data.get("jobs", [])
                if not isinstance(jobs_found, list):
                    jobs_found = []
                for raw_j in jobs_found:
                    if not isinstance(raw_j, dict):
                        continue
                    jid = raw_j.get("job_id") or raw_j.get("id")
                    if not jid:
                        continue
                    j = normalize_job_record(raw_j)
                    j["job_id"] = jid
                    jtitle = j.get("title", "")
                    if is_test_job(jid, jtitle):
                        continue
                    if self.ledger.is_blacklisted(jid):
                        continue
                    if jid not in discovered_candidates:
                        j["matched_campaign"] = camp_id
                        discovered_candidates[jid] = j
            else:
                searches_failed += 1
                if res.get("error_class"):
                    error_classes.append(res["error_class"])

        if n_tasks:
            state["search_cursor"] = (cursor + searches_used) % n_tasks
        logger.info(
            "Search coverage: tasks=%s cursor=%s used=%s per_campaign=%s",
            n_tasks,
            cursor,
            searches_used,
            per_campaign_searches,
        )

        # 2. Dedup & Strict First-Mover Pre-filtering (<1h old, <20 proposals, 0 interviewing)
        survivors: List[Tuple[str, Dict[str, Any]]] = []
        new_count = 0
        refreshed_count = 0
        pre_filtered_count = 0

        for jid, job_summary in discovered_candidates.items():
            # Permanent ledger check: skip if blacklisted, already drafted, or already submitted
            if not self.ledger.can_process_for_proposal(jid):
                pre_filtered_count += 1
                continue

            if jid in existing_jobs:
                existing = existing_jobs[jid]
                status = existing.get("status")
                # Never re-fetch or re-draft proposals for existing jobs
                if status in ("drafted", "in_review", "submitted", "rejected_by_aryan", "rejected", "ai_rejected", "skipped", "discovered", "scored"):
                    continue
                continue

            # Cheap list-level pre-filter
            title = str(job_summary.get("title", "")).lower()
            if job_summary.get("applied") is True:
                pre_filtered_count += 1
                continue

            # Strict 1-Hour First-Mover Window pre-filter (drop old noise immediately before detail fetch)
            posted_age_h = job_summary.get("posted_age_hours")
            if posted_age_h is not None:
                try:
                    if float(posted_age_h) > MAX_FIRST_MOVER_AGE_HOURS:
                        pre_filtered_count += 1
                        continue
                except (ValueError, TypeError):
                    pass

            # Strict Low-Competition pre-filter (<20 proposals)
            prop_cnt = int(job_summary.get("proposals_count") or 0)
            prop_tier_l = str(job_summary.get("proposals_tier") or "").lower()
            if prop_cnt >= MAX_COMPETITION_PROPOSALS or any(
                t in prop_tier_l for t in ("20 to 50", "20-50", "50+", "more than 50")
            ):
                pre_filtered_count += 1
                continue

            # Obvious capability gate check on title
            if any(re.search(pat, title) for pat in CAPABILITY_DISQUALIFIERS):
                pre_filtered_count += 1
                continue

            # Low budget check using normalized fields
            jtype = str(job_summary.get("type") or job_summary.get("job_type") or "").lower()
            budget = job_summary.get("budget_fixed")
            hourly_max = job_summary.get("hourly_max")

            if jtype == "fixed" and budget is not None:
                try:
                    if float(budget) < 100.0:
                        pre_filtered_count += 1
                        continue
                except (ValueError, TypeError):
                    pass
            if jtype == "hourly" and hourly_max is not None:
                try:
                    if float(hourly_max) < 25.0:
                        pre_filtered_count += 1
                        continue
                except (ValueError, TypeError):
                    pass

            # Excluded terms
            excluded = ["cold email", "deliverability", "gohighlevel", "clay", "apollo", "smartlead", "instantly"]
            if any(term in title for term in excluded):
                pre_filtered_count += 1
                continue

            survivors.append((jid, job_summary))
            new_count += 1

        # Sort survivors so high-quality clients (verified, high spend, frequent posters) & freshest posts get detail fetches first
        def _survivor_priority(item: Tuple[str, Dict[str, Any]]) -> Tuple[int, float, int, float]:
            _, s = item
            c = s.get("client_record") if isinstance(s.get("client_record"), dict) else (s.get("client") if isinstance(s.get("client"), dict) else {})
            verified = 1 if c.get("payment_verified") else 0
            spent = float(parse_number(c.get("total_spent"), 0.0) or 0.0)
            posted = int(c.get("jobs_posted") or c.get("total_posted_jobs") or 0)
            age_h = float(s.get("posted_age_hours") if s.get("posted_age_hours") is not None else 0.5)
            return (-verified, -spent, -posted, age_h)

        survivors.sort(key=_survivor_priority)

        # 3. Detail fetching capped at max_details (always fetch details for fresh <1h candidates to get full client stars/reviews/activityStat)
        details_fetched = 0
        final_discovered_records: List[Dict[str, Any]] = []

        for idx, (jid, summary) in enumerate(survivors):
            has_full_summary = bool(summary.get("description") and (summary.get("client") or summary.get("client_record")))
            need_detail_call = True
            if has_full_summary:
                is_disq_pre, _, _ = check_disqualifiers(summary)
                if is_disq_pre:
                    need_detail_call = False
                else:
                    pre_score = score_job(summary).get("score", 0.0)
                    if pre_score < 50.0:
                        need_detail_call = False

            if need_detail_call and details_fetched < max_details and not _budget_exhausted():
                detail_res = self.mcp.call_tool("find_jobs", "get", {"job_id": jid}, run_id=run_id, state=state)
                if detail_res.get("ok"):
                    detail_data = detail_res.get("data", {})
                    if isinstance(detail_data, dict) and detail_data.get("status") != "error" and "error_code" not in detail_data:
                        details_fetched += 1
                        if detail_data.get("connects_balance") is not None:
                            try:
                                state["connects_balance"] = int(detail_data["connects_balance"])
                            except (ValueError, TypeError):
                                pass
                        # Save valid raw payload to payloads dir
                        try:
                            payload_path = PAYLOADS_DIR / f"{jid.replace('~', '_')}.json"
                            with open(payload_path, "w", encoding="utf-8") as pf:
                                json.dump(detail_data, pf, indent=2, ensure_ascii=False)
                        except Exception as e:
                            logger.warning(f"Could not persist raw payload: {e}")
                        merged = normalize_job_record(summary, detail_data)
                    else:
                        merged = normalize_job_record(summary)
                elif has_full_summary:
                    merged = normalize_job_record(summary)
                else:
                    continue
            elif has_full_summary:
                merged = normalize_job_record(summary)
            else:
                if idx >= max_details or _budget_exhausted():
                    break
                continue

            merged["job_id"] = jid

            # Extract and persist accurate Upwork timestamps
            posted_at, scraped_at, age_mins = extract_job_timestamps(merged)
            merged["posted_at"] = posted_at
            merged["scraped_at"] = scraped_at
            merged["first_seen_at"] = merged.get("first_seen_at") or scraped_at
            merged["last_checked_at"] = now_utc.isoformat()
            merged["age_when_scraped_minutes"] = age_mins
            if age_mins is not None:
                merged["posted_age_hours"] = round(float(age_mins) / 60.0, 2)
            merged["status"] = "discovered"
            merged["campaign"] = summary.get("matched_campaign", "claude-implementation")

            # Record into master ledger
            self.ledger.record_job(merged, status="discovered")

            existing_jobs[jid] = merged
            final_discovered_records.append(merged)

        # 4. Save updated jobs and state
        self.state_mgr.save_jobs(existing_jobs)
        state["last_run_at"] = now_utc.isoformat()
        state["last_run_id"] = run_id
        state["runs_today"] = state.get("runs_today", 0) + 1
        self.state_mgr.save_state(state)

        auth_ok = (not getattr(self.mcp, "auth_failed", False)) and ("auth" not in error_classes)
        healthy = auth_ok and (searches_ok > 0)

        return {
            "run_id": run_id,
            "searches_used": searches_used,
            "searches_ok": searches_ok,
            "searches_failed": searches_failed,
            "auth_ok": auth_ok,
            "healthy": healthy,
            "error_classes": list(set(error_classes)),
            "duration_s": round(time.time() - t_start, 2),
            "candidates_found": len(discovered_candidates),
            "new": new_count,
            "refreshed": refreshed_count,
            "pre_filtered": pre_filtered_count,
            "detail_fetched": details_fetched,
            "records_ready_for_vet": [r["job_id"] for r in final_discovered_records],
            "mismatches": list(set(mismatches_observed)),
            "kill_switch_active": kill_switch_active,
        }
