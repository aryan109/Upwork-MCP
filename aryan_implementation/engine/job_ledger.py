"""
Job Ledger, Persistent Deduplication & Timestamp Engine for Aryan Upwork Acquisition Pipeline.
Ensures:
1. Every scraped job has exact `posted_at`, `scraped_at`, and `age_minutes` recorded.
2. Complete persistent deduplication across all passes and container lifecycles.
3. Strict Rejection Blacklist: Once a job is rejected (by human or AI/rubric), it NEVER reappears.
4. Total Test Isolation: Completely filters out synthetic/mock test jobs and test messages.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .config import STATE_DIR

logger = logging.getLogger("job_ledger")

# Known synthetic test prefixes and patterns
TEST_JOB_PREFIXES = ("~01test", "~01sample", "test_", "mock_")
TEST_TITLE_PATTERNS = [
    r"\[test\]",
    r"^test\b",
    r"sample claude job",
    r"^mock\b",
]


def extract_job_timestamps(job_data: Dict[str, Any]) -> Tuple[Optional[str], str, Optional[float]]:
    """
    Extracts and standardizes:
    - posted_at: When the client actually published/posted the job on Upwork (UTC ISO)
    - scraped_at: Exact timestamp when our system scraped/ingested it (UTC ISO)
    - age_minutes: Elapsed minutes between posted_at and scraped_at
    """
    now_utc = datetime.now(timezone.utc)
    scraped_at = job_data.get("scraped_at") or job_data.get("first_seen_at") or now_utc.isoformat()

    posted_at: Optional[str] = None
    age_minutes: Optional[float] = None

    # 1. Check known Upwork date/time fields in order of specificity
    candidate_keys = [
        "postedOn",
        "createdOn",
        "publishDate",
        "published_date",
        "publishedDateTime",
        "created_time",
        "published_at",
        "date_posted",
        "created_at",
        "publish_date",
        "dateCreated",
    ]

    for key in candidate_keys:
        val = job_data.get(key)
        if val:
            if isinstance(val, (int, float)):
                # Unix timestamp (seconds or milliseconds)
                try:
                    ts = float(val)
                    if ts > 1e11:  # Milliseconds
                        ts /= 1000.0
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    posted_at = dt.isoformat()
                    break
                except Exception:
                    pass
            elif isinstance(val, str) and len(val.strip()) > 0:
                val_str = val.strip()
                # Check if ISO format
                try:
                    dt = datetime.fromisoformat(val_str.replace("Z", "+00:00"))
                    posted_at = dt.isoformat()
                    break
                except Exception:
                    pass

                # Check relative time strings like "Posted 15 minutes ago", "2 hours ago", "yesterday"
                dt_rel = parse_relative_time(val_str, now_utc)
                if dt_rel:
                    posted_at = dt_rel.isoformat()
                    break

    # 2. Check snippet or description text for "Posted X ago" if not found
    if not posted_at:
        desc_or_snippet = f"{job_data.get('snippet', '')} {job_data.get('description', '')}"
        m = re.search(r"(?:posted|created)\s+(\d+\s+(?:minute|hour|day|week)s?\s+ago|yesterday)", desc_or_snippet, re.IGNORECASE)
        if m:
            dt_rel = parse_relative_time(m.group(1), now_utc)
            if dt_rel:
                posted_at = dt_rel.isoformat()

    # 3. Fallback: if Upwork gave no timestamp, use scraped_at as estimate
    if not posted_at:
        posted_at = scraped_at
        age_minutes = 0.0
    else:
        try:
            p_dt = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
            s_dt = datetime.fromisoformat(scraped_at.replace("Z", "+00:00"))
            age_minutes = round(max(0.0, (s_dt - p_dt).total_seconds() / 60.0), 1)
        except Exception:
            age_minutes = 0.0

    return posted_at, scraped_at, age_minutes


def parse_relative_time(text: str, reference_dt: datetime) -> Optional[datetime]:
    """Parse relative time strings into UTC datetime."""
    text_clean = text.lower().strip()
    if "just now" in text_clean or "moments ago" in text_clean:
        return reference_dt
    if "yesterday" in text_clean:
        return reference_dt - timedelta(days=1)

    m = re.search(r"(\d+)\s+(minute|hour|day|week)s?\s+ago", text_clean)
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        if unit == "minute":
            return reference_dt - timedelta(minutes=amount)
        elif unit == "hour":
            return reference_dt - timedelta(hours=amount)
        elif unit == "day":
            return reference_dt - timedelta(days=amount)
        elif unit == "week":
            return reference_dt - timedelta(weeks=amount)
    return None


def is_test_job(job_id: str, title: str = "") -> bool:
    """Return True if job is an internal test/mock/synthetic artifact."""
    if not job_id:
        return True
    clean_id = job_id.lower().strip()
    clean_title = (title or "").lower().strip()

    if any(clean_id.startswith(p) for p in TEST_JOB_PREFIXES):
        return True
    if "test_submission" in clean_id or "sample_claude" in clean_id:
        return True
    if any(re.search(pat, clean_title) for pat in TEST_TITLE_PATTERNS):
        return True

    return False


class JobLedger:
    """
    Central immutable ledger tracking every job seen, scraped, scored, or rejected.
    Prevents duplicate proposals, resurrecting old jobs, and test job leakage.
    """

    def __init__(self, state_dir: Optional[Union[str, Path]] = None):
        self.state_dir = Path(state_dir) if state_dir else STATE_DIR
        self.ledger_file = self.state_dir / "job_ledger.json"
        self.rejected_file = self.state_dir / "rejected_jobs.json"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def load_ledger(self) -> Dict[str, Dict[str, Any]]:
        """Load the master job index."""
        if not self.ledger_file.exists():
            return {}
        try:
            with open(self.ledger_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error loading job_ledger.json: {e}")
            return {}

    def save_ledger(self, ledger: Dict[str, Dict[str, Any]]) -> None:
        """Atomically persist the job index."""
        tmp = self.ledger_file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(ledger, f, indent=2, ensure_ascii=False)
        tmp.replace(self.ledger_file)

    def load_rejected_ids(self) -> Set[str]:
        """Load set of all permanently rejected job IDs."""
        if not self.rejected_file.exists():
            return set()
        try:
            with open(self.rejected_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return set(data)
                elif isinstance(data, dict):
                    return set(data.keys())
                return set()
        except Exception as e:
            logger.warning(f"Error loading rejected_jobs.json: {e}")
            return set()

    def add_to_rejected(self, job_id: str, reason: str = "Rejected", title: str = "") -> None:
        """Permanently record a job as rejected. It will NEVER be scraped or proposed to again."""
        if is_test_job(job_id, title):
            return

        rejected_dict: Dict[str, Any] = {}
        if self.rejected_file.exists():
            try:
                with open(self.rejected_file, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    if isinstance(raw, dict):
                        rejected_dict = raw
                    elif isinstance(raw, list):
                        rejected_dict = {jid: {"reason": "Historical rejection"} for jid in raw}
            except Exception:
                rejected_dict = {}

        now_utc = datetime.now(timezone.utc).isoformat()
        rejected_dict[job_id] = {
            "rejected_at": now_utc,
            "reason": reason,
            "title": title,
        }

        tmp = self.rejected_file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rejected_dict, f, indent=2, ensure_ascii=False)
        tmp.replace(self.rejected_file)

        # Also update in ledger
        ledger = self.load_ledger()
        if job_id in ledger:
            ledger[job_id]["status"] = "rejected"
            ledger[job_id]["rejection_reason"] = reason
            ledger[job_id]["rejected_at"] = now_utc
            self.save_ledger(ledger)

        logger.info(f"Permanently blacklisted rejected job {job_id} ({reason})")

    def is_blacklisted(self, job_id: str) -> bool:
        """Check if job was previously rejected or disqualified."""
        if is_test_job(job_id):
            return True
        rejected_ids = self.load_rejected_ids()
        if job_id in rejected_ids or job_id.lstrip("~") in rejected_ids or f"~{job_id}" in rejected_ids:
            return True

        ledger = self.load_ledger()
        rec = ledger.get(job_id) or ledger.get(job_id.lstrip("~")) or ledger.get(f"~{job_id}")
        if rec and rec.get("status") in ("rejected", "rejected_by_aryan", "ai_rejected", "skipped"):
            return True

        return False

    def can_process_for_proposal(self, job_id: str) -> bool:
        """Check if job is eligible for proposal generation (not blacklisted, not already drafted/submitted)."""
        if self.is_blacklisted(job_id):
            return False

        ledger = self.load_ledger()
        rec = ledger.get(job_id) or ledger.get(job_id.lstrip("~")) or ledger.get(f"~{job_id}")
        if rec:
            status = rec.get("status")
            if status in ("drafted", "in_review", "submitted", "rejected", "rejected_by_aryan", "ai_rejected", "skipped"):
                return False

        return True

    def record_job(
        self,
        job_data: Dict[str, Any],
        status: str = "discovered",
        decision: Optional[str] = None,
        score: Optional[float] = None,
        rejection_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record or update a job in the master ledger with exact timestamps."""
        job_id = job_data.get("job_id") or job_data.get("id") or ""
        title = job_data.get("title") or "Unknown"

        if is_test_job(job_id, title):
            logger.debug(f"Ignoring test job {job_id} from ledger")
            return job_data

        posted_at, scraped_at, age_mins = extract_job_timestamps(job_data)
        now_utc = datetime.now(timezone.utc).isoformat()

        ledger = self.load_ledger()
        existing = ledger.get(job_id, {})

        entry = {
            "job_id": job_id,
            "title": title,
            "posted_at": existing.get("posted_at") or posted_at,
            "scraped_at": existing.get("scraped_at") or scraped_at,
            "age_when_scraped_minutes": existing.get("age_when_scraped_minutes") or age_mins,
            "last_seen_at": now_utc,
            "status": status if status != "discovered" else existing.get("status", "discovered"),
            "decision": decision or existing.get("decision"),
            "score": score if score is not None else existing.get("score"),
            "rejection_reason": rejection_reason or existing.get("rejection_reason"),
            "campaign": job_data.get("campaign") or job_data.get("matched_campaign") or existing.get("campaign"),
            "budget": job_data.get("budget_fixed") or job_data.get("budget"),
            "hourly_rate": job_data.get("hourly_max") or job_data.get("hourly_budget"),
            "client_country": (job_data.get("client_record") or {}).get("country") if isinstance(job_data.get("client_record"), dict) else None,
        }

        # If rejected, mark rejected timestamp
        if status in ("rejected", "rejected_by_aryan", "ai_rejected", "skipped"):
            entry["rejected_at"] = now_utc
            self.add_to_rejected(job_id, reason=rejection_reason or "Disqualified", title=title)

        ledger[job_id] = entry
        self.save_ledger(ledger)

        # Update fields onto job_data copy
        job_data["posted_at"] = entry["posted_at"]
        job_data["scraped_at"] = entry["scraped_at"]
        job_data["age_when_scraped_minutes"] = entry["age_when_scraped_minutes"]
        job_data["status"] = entry["status"]

        return entry
