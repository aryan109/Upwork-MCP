"""Export jobs.json into the market-research TSV the analysis prompt expects."""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aryan_implementation.engine.config import STATE_DIR

OUT_DIR = Path(__file__).resolve().parent.parent / "research"
OUT_PATH = OUT_DIR / "upwork_ai_market_job_table.csv"

FIELDS = [
    "query",
    "sample_type",
    "posted_ago",
    "title",
    "url",
    "job_type",
    "budget_min",
    "budget_max",
    "connects",
    "proposals",
    "interviewing",
    "hires_on_post",
    "country",
    "spend",
    "client_hires",
    "verified",
    "hire_rate",
    "rating",
    "india_blocked",
    "snippet",
    "tech",
    "buyer_job",
    "filled",
    "campaign",
    "engine_decision",
    "engine_score",
    "engine_disqualifiers",
    "job_id",
    "vetted_at",
]


def _client(job: dict) -> dict:
    for key in ("client_record", "client", "client_info"):
        val = job.get(key)
        if isinstance(val, dict):
            return val
    return {}


def _num(value):
    if value is None or value == "":
        return ""
    if isinstance(value, (int, float)):
        return value
    text = str(value)
    cleaned = re.sub(r"[^0-9.]", "", text.replace(",", ""))
    if not cleaned:
        return ""
    try:
        return float(cleaned) if "." in cleaned else int(cleaned)
    except ValueError:
        return text


def _verified(client: dict) -> str:
    if client.get("payment_verified") is True:
        return "Y"
    status = str(client.get("verification_status") or client.get("status") or "").upper()
    if status in {"VERIFIED", "PAYMENT_VERIFIED", "TRUE"}:
        return "Y"
    if client.get("payment_verified") is False:
        return "N"
    if status in {"UNVERIFIED", "FALSE"}:
        return "N"
    return "UNKNOWN"


def _snippet(job: dict) -> str:
    raw = job.get("description") or job.get("description_snippet") or job.get("snippet") or ""
    raw = re.sub(r"</?untrusted_participant_content>", "", str(raw))
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw[:400]


def _budget(job: dict):
    jtype = job.get("type") or job.get("job_type") or ""
    if job.get("budget_hourly_min") is not None or job.get("budget_hourly_max") is not None:
        return "hourly", job.get("budget_hourly_min", ""), job.get("budget_hourly_max", "")
    if job.get("budget_fixed") is not None:
        return "fixed", job.get("budget_fixed"), job.get("budget_fixed")
    budget = job.get("budget")
    if isinstance(budget, dict):
        if budget.get("hourly_max") or budget.get("hourly_min"):
            return "hourly", budget.get("hourly_min", ""), budget.get("hourly_max", "")
        if budget.get("fixed_amount") is not None:
            return "fixed", budget.get("fixed_amount"), budget.get("fixed_amount")
    if isinstance(budget, str) and budget:
        nums = re.findall(r"[0-9]+(?:\.[0-9]+)?", budget.replace(",", ""))
        if "hr" in budget.lower() or "hour" in budget.lower():
            if len(nums) >= 2:
                return "hourly", nums[0], nums[1]
            if nums:
                return "hourly", nums[0], nums[0]
        if nums:
            return jtype or "fixed", nums[0], nums[-1]
    return jtype or "UNKNOWN", "", ""


def _tech(job: dict) -> str:
    skills = job.get("skills") or job.get("tech_stack") or []
    if isinstance(skills, list):
        return ", ".join(str(s) for s in skills[:12])
    return str(skills or "")


def row_from_job(jid: str, job: dict) -> dict:
    client = _client(job)
    jtype, bmin, bmax = _budget(job)
    verified = _verified(client)
    spend = _num(client.get("total_spent"))
    hires = _num(client.get("total_hires") or client.get("hires") or "")
    d6_like = verified == "N" and (spend in ("", 0, 0.0) or spend == "0") and (hires in ("", 0, 0.0))
    sample_type = "raw"
    if verified == "Y" and not d6_like:
        sample_type = "buyable"
    filled = "N"
    if job.get("total_hired") and job.get("persons_to_hire"):
        try:
            filled = "Y" if float(job["total_hired"]) >= float(job["persons_to_hire"]) else "N"
        except (TypeError, ValueError):
            filled = "UNKNOWN"
    if "D11" in (job.get("disqualifiers") or []):
        filled = "Y"
    url = job.get("url") or job.get("job_url") or ""
    if not url:
        uid = str(job.get("job_id") or job.get("id") or jid).lstrip("~")
        url = f"https://www.upwork.com/jobs/~{uid}"
    return {
        "query": job.get("campaign") or job.get("matched_campaign") or "",
        "sample_type": sample_type,
        "posted_ago": job.get("published_date") or job.get("created_date") or job.get("first_seen_at") or "",
        "title": job.get("title") or "",
        "url": url,
        "job_type": jtype,
        "budget_min": bmin,
        "budget_max": bmax,
        "connects": job.get("connects_cost") or job.get("connects") or "",
        "proposals": job.get("proposals_tier") or job.get("proposals") or "",
        "interviewing": job.get("interviewing") or job.get("client_interviews") or "",
        "hires_on_post": job.get("total_hired") if job.get("total_hired") is not None else "",
        "country": client.get("country") or "",
        "spend": spend,
        "client_hires": hires,
        "verified": verified,
        "hire_rate": client.get("hire_rate_percent") or client.get("hire_rate") or "",
        "rating": client.get("rating") or "",
        "india_blocked": "UNKNOWN",
        "snippet": _snippet(job),
        "tech": _tech(job),
        "buyer_job": "",
        "filled": filled,
        "campaign": job.get("campaign") or job.get("matched_campaign") or "",
        "engine_decision": job.get("decision") or job.get("status") or "",
        "engine_score": job.get("score") if job.get("score") is not None else "",
        "engine_disqualifiers": "|".join(job.get("disqualifiers") or []),
        "job_id": job.get("job_id") or job.get("id") or jid,
        "vetted_at": job.get("vetted_at") or job.get("rejected_at") or job.get("scraped_at") or job.get("first_seen_at") or "",
    }


def main() -> None:
    jobs_path = STATE_DIR / "jobs.json"
    jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
    if isinstance(jobs, list):
        jobs = {str(j.get("job_id") or i): j for i, j in enumerate(jobs)}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for jid, job in jobs.items():
        if not isinstance(job, dict):
            continue
        if str(jid).startswith("~01sample") or str(job.get("job_id", "")).startswith("~01sample"):
            continue
        rows.append(row_from_job(str(jid), job))
    rows.sort(key=lambda r: str(r.get("vetted_at") or r.get("posted_ago") or ""), reverse=True)
    with OUT_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUT_PATH}")
    print(f"Source ledger: {jobs_path}")


if __name__ == "__main__":
    main()
