"""
Lead scoring rubric and deterministic qualification engine for Aryan Upwork pipeline.
Implements the 0–100 weighted rubric and D1–D11 disqualifiers from 06_LEAD_SCORING_RUBRIC.md.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Set


CAPABILITY_DISQUALIFIERS = [
    r"\bios\b",
    r"\bandroid\b",
    r"\bunity(?:3d)?\b",
    r"\bunreal(?:\s+engine)?\b",
    r"\bsap\b",
    r"\bsalesforce apex\b",
    r"\bsolidity\b",
    r"\bblockchain\b",
    r"\bvideo edit",
    r"\bvoice over\b",
    r"\bdata entry\b",
    r"\bvirtual assistant\b",
    r"\bgraphic design\b",
    r"\blogo design\b",
    r"\bcopywriting\b",
    r"\bseo writing\b",
]

HARD_NON_AI_CAPABILITY_DISQUALIFIERS = [
    r"\bunity(?:3d)?\b",
    r"\bunreal(?:\s+engine)?\b",
    r"\bsap\b",
    r"\bsalesforce apex\b",
    r"\bsolidity\b",
    r"\bblockchain\b",
    r"\bvoice over\b",
    r"\blogo design\b",
]

POLICY_DISQUALIFIERS = [
    r"pay outside upwork",
    r"payment outside upwork",
    r"communicate outside upwork",
    r"(?:contact|message|reach|chat|dm|ping|pay|payment|communicate)\b[^.\n]{0,50}\b(?:telegram|whatsapp)\b",
    r"\b(?:telegram|whatsapp)\b[^.\n]{0,50}\b(?:outside upwork|off[- ]platform)\b",
    r"write my essay",
    r"academic paper",
    r"post fake review",
    r"scrape upwork",
    r"upwork scraper",
]

STAFFING_DISQUALIFIERS = [
    r"join our team of \d+",
    r"agency pool",
    r"commission only",
    r"commission-only",
    r"equity only",
    r"revenue share only",
    r"no upfront pay",
]

RED_FLAG_PATTERNS = [
    r"\bninja\b",
    r"\brockstar\b",
    r"\bguru\b",
    r"\bsimple task\b",
    r"\bshould take 1 hour\b",
    r"\bshould take an hour\b",
    r"\bunlimited revisions\b",
    r"\basap today\b",
    r"\burgent today\b",
    r"\beasy job\b",
    r"\bvery easy\b",
    r"\bi know exactly what i want and it'?s easy\b",
]


def parse_number(val: Any, default: Optional[float] = None) -> Optional[float]:
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return default
    # Extract numbers (supports ranges like "15.00–25.00/hr" by returning the upper bound)
    nums = [float(x.replace(",", "")) for x in re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", s)]
    if nums:
        return nums[-1]
    cleaned = re.sub(r"[^\d.]", "", s)
    try:
        return float(cleaned) if cleaned else default
    except (ValueError, TypeError):
        return default


def parse_money_range(val: Any) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """
    Parse Upwork budget/rate values like '5,000.00', '$7,346.41', '15.00–25.00/hr', '30.00/hr',
    or dict {'amount': 500} / {'min': 20, 'max': 40}.
    Returns (min_val, max_val, inferred_type).
    """
    if val is None:
        return None, None, None
    if isinstance(val, (int, float)):
        v = float(val)
        return v, v, "fixed"
    if isinstance(val, dict):
        amt = val.get("amount") if val.get("amount") is not None else (val.get("rawValue") if val.get("rawValue") is not None else val.get("displayValue"))
        if amt is not None:
            f, _, _ = parse_money_range(amt)
            return f, f, "fixed"
        mn = parse_number(val.get("min"))
        mx = parse_number(val.get("max"))
        return mn, (mx if mx is not None else mn), "hourly"
    s = str(val).strip()
    if not s:
        return None, None, None
    is_hourly = "/hr" in s.lower() or "hourly" in s.lower() or "–" in s or " - " in s
    nums = [float(x.replace(",", "")) for x in re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", s)]
    if not nums:
        return None, None, None
    if len(nums) >= 2:
        return nums[0], nums[1], "hourly"
    return nums[0], nums[0], ("hourly" if is_hourly else "fixed")


def clean_untrusted_tags(text: Any) -> str:
    """Strip <untrusted_participant_content> and <untrusted_data> wrapper tags injected by Upwork MCP."""
    if not text:
        return ""
    cleaned = re.sub(r"</?untrusted_[a-z_]+>", "", str(text))
    return cleaned.strip()


from aryan_implementation.engine.config import (
    MAX_COMPETITION_PROPOSALS,
    MAX_FIRST_MOVER_AGE_HOURS,
)
from aryan_implementation.engine.job_ledger import extract_job_timestamps


def normalize_job_record(job: Dict[str, Any], detail_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Normalize a job record across Upwork MCP `find_jobs.search`, `find_jobs.smart_search`,
    and `find_jobs.get` schemas so disqualifiers, scoring, AI vetting, and reporting
    always see unified fields (`description`, `client_record`, `activityStat`, `contractTerms`,
    `type`, `budget_fixed`, `hourly_min`, `hourly_max`, `posted_age_hours`, `proposals_count`).
    """
    if not isinstance(job, dict):
        return {}
    j: Dict[str, Any] = dict(job)

    if isinstance(detail_data, dict) and detail_data.get("status") != "error" and "error_code" not in detail_data:
        for k, v in detail_data.items():
            if k == "status":
                continue
            if v is not None:
                j[k] = v

    data_obj = j.get("data") if isinstance(j.get("data"), dict) else {}
    mjp = data_obj.get("marketplaceJobPosting") if isinstance(data_obj.get("marketplaceJobPosting"), dict) else {}

    # 1. Title & Description extraction + tag cleanup
    content = mjp.get("content") if isinstance(mjp.get("content"), dict) else {}
    raw_title = j.get("title") or content.get("title") or ""
    if raw_title:
        j["title"] = clean_untrusted_tags(raw_title)

    raw_desc = (
        content.get("description")
        or j.get("description")
        or j.get("description_snippet")
        or j.get("snippet")
        or ""
    )
    j["description"] = clean_untrusted_tags(raw_desc)
    if j.get("description_snippet"):
        j["description_snippet"] = clean_untrusted_tags(j["description_snippet"])

    if isinstance(j.get("screening_questions"), list):
        j["screening_questions"] = [
            clean_untrusted_tags(q.get("question") if isinstance(q, dict) else q)
            for q in j["screening_questions"]
            if q
        ]

    # 2. Promote activityStat and contractTerms from marketplaceJobPosting
    if mjp.get("activityStat") and not isinstance(j.get("activityStat"), dict):
        j["activityStat"] = mjp["activityStat"]
    if mjp.get("contractTerms") and not isinstance(j.get("contractTerms"), dict):
        j["contractTerms"] = mjp["contractTerms"]

    # Promote publishedDateTime / createdDateTime from marketplaceJobPosting if needed
    if not any(j.get(k) for k in ("published_date", "created_date", "posted_at", "published_at", "created_at")):
        pub_dt = mjp.get("publishedDateTime") or mjp.get("createdDateTime")
        if pub_dt:
            j["published_date"] = pub_dt

    # 3. Unify client & client_record
    c_sum = j.get("client") if isinstance(j.get("client"), dict) else {}
    c_rec = j.get("client_record") if isinstance(j.get("client_record"), dict) else {}
    c_pub = mjp.get("clientCompanyPublic") if isinstance(mjp.get("clientCompanyPublic"), dict) else {}

    if c_sum or c_rec or c_pub:
        has_spend_key = any(k in c_rec or k in c_sum for k in ("spend_total", "total_spent"))
        spent_raw = (
            c_rec.get("spend_total")
            if c_rec.get("spend_total") is not None
            else (c_sum.get("total_spent") if c_sum.get("total_spent") is not None else c_rec.get("total_spent"))
        )
        spent_val = parse_number(spent_raw, 0.0 if has_spend_key else None)

        hires_val = int(
            c_rec.get("jobs_with_hires")
            or c_rec.get("contracts_total")
            or c_sum.get("total_hires")
            or c_sum.get("jobs_with_hires")
            or 0
        )

        reviews_count_val = int(
            c_rec.get("reviews_count")
            or c_sum.get("reviews_count")
            or c_pub.get("reviewsCount")
            or 0
        )

        ver_status = str(c_sum.get("verification_status") or c_rec.get("verification_status") or "").upper()
        if "payment_verified" in c_rec:
            payment_verified = bool(c_rec["payment_verified"]) or ver_status == "VERIFIED"
        elif "payment_verified" in c_sum:
            payment_verified = bool(c_sum["payment_verified"]) or ver_status == "VERIFIED"
        else:
            payment_verified = ver_status == "VERIFIED"

        rating_val = (
            c_rec.get("feedback_score")
            if c_rec.get("feedback_score") is not None
            else (c_sum.get("rating") if c_sum.get("rating") is not None else c_rec.get("rating"))
        )
        if rating_val is None and c_sum.get("feedback_score") is not None:
            rating_val = c_sum.get("feedback_score")

        hire_rate_val = (
            c_rec.get("hire_rate_percent")
            if c_rec.get("hire_rate_percent") is not None
            else (c_sum.get("hire_rate_percent") if c_sum.get("hire_rate_percent") is not None else c_sum.get("hire_rate"))
        )
        jobs_posted_val = int(
            c_rec.get("jobs_posted")
            or c_sum.get("total_posted_jobs")
            or c_sum.get("jobs_posted")
            or c_rec.get("total_posted_jobs")
            or 0
        )
        if hire_rate_val is None and jobs_posted_val > 0 and hires_val >= 0:
            hire_rate_val = round(min(100.0, (hires_val / float(jobs_posted_val)) * 100.0), 1)
        country_val = (
            c_sum.get("country")
            or c_rec.get("country")
            or ((c_pub.get("country") or {}).get("name") if isinstance(c_pub.get("country"), dict) else None)
        )

        unified_client: Dict[str, Any] = {
            **c_sum,
            **c_rec,
            "payment_verified": payment_verified,
            "verification_status": "VERIFIED" if payment_verified else (ver_status or "UNKNOWN"),
            "jobs_with_hires": hires_val,
            "jobs_posted": jobs_posted_val,
            "total_posted_jobs": jobs_posted_val,
            "reviews_count": reviews_count_val,
        }
        if spent_val is not None:
            unified_client["total_spent"] = spent_val
        if rating_val is not None:
            unified_client["rating"] = rating_val
            unified_client["feedback_score"] = rating_val
        if hire_rate_val is not None:
            unified_client["hire_rate_percent"] = hire_rate_val
        if country_val:
            unified_client["country"] = country_val

        j["client_record"] = unified_client
        j["client"] = unified_client

    # 4. Normalize job type and budget / hourly rate fields
    ct = j.get("contractTerms") if isinstance(j.get("contractTerms"), dict) else {}
    raw_type = str(j.get("type") or j.get("job_type") or ct.get("contractType") or "").lower()
    b_min, b_max, inferred_type = parse_money_range(j.get("budget"))
    if raw_type in ("fixed", "hourly"):
        jtype = raw_type
    elif "fixed" in raw_type:
        jtype = "fixed"
    elif "hourly" in raw_type:
        jtype = "hourly"
    else:
        jtype = inferred_type or ""

    if jtype:
        j["type"] = jtype
        j["job_type"] = jtype

    if jtype == "fixed":
        fp_amt = ((ct.get("fixedPriceContractTerms") or {}).get("amount") or {}).get("rawValue")
        fb = parse_number(j.get("budget_fixed"))
        if fb is None:
            fb = parse_number(fp_amt) if fp_amt is not None else b_max
        if fb is not None:
            j["budget_fixed"] = fb
    elif jtype == "hourly":
        hm = parse_number(j.get("hourly_max") if j.get("hourly_max") is not None else j.get("hourly_budget"))
        if hm is None:
            hm = b_max
        if hm is not None:
            j["hourly_max"] = hm
        if b_min is not None and j.get("hourly_min") is None:
            j["hourly_min"] = b_min

    # 5. Normalize proposals_count from activityStat or proposals_tier
    act_stat = j.get("activityStat") if isinstance(j.get("activityStat"), dict) else {}
    activity = act_stat.get("jobActivity") if isinstance(act_stat.get("jobActivity"), dict) else (j.get("activity") if isinstance(j.get("activity"), dict) else {})
    if j.get("proposals_count") is None:
        tot_app = activity.get("totalApplicants")
        if tot_app is not None:
            try:
                j["proposals_count"] = int(tot_app)
            except (ValueError, TypeError):
                pass
        if j.get("proposals_count") is None and j.get("proposals_tier"):
            tier_l = str(j.get("proposals_tier") or "").lower()
            if "less than 5" in tier_l:
                j["proposals_count"] = 3
            elif "5 to 10" in tier_l or "5-10" in tier_l:
                j["proposals_count"] = 8
            elif "10 to 15" in tier_l or "10-15" in tier_l:
                j["proposals_count"] = 12
            elif "15 to 20" in tier_l or "15-20" in tier_l:
                j["proposals_count"] = 17
            elif "20 to 50" in tier_l or "20-50" in tier_l:
                j["proposals_count"] = 35
            elif "50+" in tier_l or "more than 50" in tier_l:
                j["proposals_count"] = 55

    # 6. Normalize posted_age_hours against real current UTC time whenever a timestamp exists
    has_ts = any(j.get(k) for k in ("published_date", "created_date", "posted_at", "published_at", "created_at"))
    if has_ts:
        _, _, age_mins = extract_job_timestamps(j)
        if age_mins is not None:
            j["age_when_scraped_minutes"] = age_mins
            j["posted_age_hours"] = round(float(age_mins) / 60.0, 2)
    elif j.get("posted_age_hours") is None and j.get("age_when_scraped_minutes") is not None:
        try:
            j["posted_age_hours"] = round(float(j["age_when_scraped_minutes"]) / 60.0, 2)
        except Exception:
            pass

    return j


def check_disqualifiers(
    job: Dict[str, Any],
    open_clients: Optional[Set[str]] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Check hard disqualifiers D1–D11.
    Returns (is_disqualified, disqualifier_id, reason_str).
    """
    job = normalize_job_record(job)
    title = str(job.get("title", "")).lower()
    desc = str(job.get("description", "")).lower()

    # D1: Already applied or cannot apply
    if job.get("applied") is True or job.get("can_apply") is False:
        return True, "D1", "Already applied or cannot apply"
    if job.get("is_invite") is True:
        return True, "D1", "Invitation exists (handled separately)"

    # D2: Location-restricted and India not eligible
    preferred_locs = job.get("preferred_locations") or {}
    loc_req = preferred_locs.get("location_required") or job.get("location_required", False)
    allowed_locs = preferred_locs.get("locations") or job.get("locations", [])
    if loc_req and allowed_locs:
        allowed_lower = [str(loc).lower() for loc in allowed_locs]
        if not any("india" in loc for loc in allowed_lower):
            return True, "D2", f"Location required and India not eligible: {allowed_locs}"

    # D3: Capability gate
    # Always check title; only check description for hard non-AI gates or when title has no AI/automation signal
    core_ai_title = any(
        k in title
        for k in ("claude", "mcp", "n8n", "rag", "agent", "llm", "automation", "openai", "langchain", "cursor", "lovable")
    )
    for pattern in CAPABILITY_DISQUALIFIERS:
        if re.search(pattern, title):
            return True, "D3", f"Capability gate triggered: {pattern}"
        if not core_ai_title or pattern in HARD_NON_AI_CAPABILITY_DISQUALIFIERS:
            if re.search(pattern, desc[:500]):
                return True, "D3", f"Capability gate triggered: {pattern}"

    # D4: Policy / ToS violation
    for pattern in POLICY_DISQUALIFIERS:
        if re.search(pattern, desc):
            return True, "D4", f"Policy violation pattern: {pattern}"

    # D5: Staffing / Commission-only
    for pattern in STAFFING_DISQUALIFIERS:
        if re.search(pattern, desc):
            return True, "D5", f"Staffing/commission pattern: {pattern}"

    # D6: Unverified payment AND $0 spend AND 0 hires
    client = job.get("client_record") if isinstance(job.get("client_record"), dict) else (job.get("client") if isinstance(job.get("client"), dict) else {})
    act_stat = job.get("activityStat") if isinstance(job.get("activityStat"), dict) else {}
    activity = act_stat.get("jobActivity") if isinstance(act_stat.get("jobActivity"), dict) else (job.get("activity") if isinstance(job.get("activity"), dict) else {})
    if client:
        verified = bool(client.get("payment_verified", False))
        total_spent = parse_number(client.get("total_spent"), 0.0) or 0.0
        client_hires = int(
            client.get("jobs_with_hires", 0)
            or client.get("contracts_total", 0)
            or activity.get("totalHired", 0)
            or 0
        )
        if not verified and total_spent == 0.0 and client_hires == 0:
            return True, "D6", "Payment unverified AND $0 spend AND 0 hires"

    # D7: Fixed budget < $100 or hourly max < $25
    job_type = str(job.get("type") or job.get("job_type") or "").lower()
    raw_b = job.get("budget_fixed") if job.get("budget_fixed") is not None else job.get("budget")
    budget_fixed = raw_b.get("amount") if isinstance(raw_b, dict) else raw_b

    raw_h = job.get("hourly_max") if job.get("hourly_max") is not None else job.get("hourly_budget")
    hourly_max = raw_h.get("max") if isinstance(raw_h, dict) else raw_h

    b_val = parse_number(budget_fixed)
    h_val = parse_number(hourly_max)

    if job_type == "fixed" and b_val is not None:
        if b_val < 100.0:
            return True, "D7", f"Fixed budget ${b_val} is under $100 floor"
    elif job_type == "hourly" and h_val is not None:
        if h_val < 25.0:
            return True, "D7", f"Hourly ceiling ${h_val}/hr is under $25 floor"

    # D11: Job already filled (totalHired >= personsToHire) — checked before D8 so filled jobs report D11
    contract_terms = job.get("contractTerms") or {}
    raw_pth = (
        job.get("persons_to_hire")
        or contract_terms.get("personsToHire")
        or job.get("personsToHire")
        or job.get("freelancers_to_hire")
        or 1
    )
    raw_hired = (
        activity.get("totalHired")
        or job.get("total_hired")
        or activity.get("hired")
        or 0
    )
    try:
        persons_to_hire = int(raw_pth)
    except (ValueError, TypeError):
        persons_to_hire = 1

    try:
        total_hired = int(raw_hired)
    except (ValueError, TypeError):
        total_hired = 0

    if persons_to_hire > 0 and total_hired >= persons_to_hire:
        return True, "D11", f"Job already filled ({total_hired}/{persons_to_hire} hired)"

    # D8: Strict First-Mover Advantage Gate:
    # 1. Must be posted within MAX_FIRST_MOVER_AGE_HOURS (1.0 hour)
    # 2. Must have fewer than MAX_COMPETITION_PROPOSALS (20 proposals)
    # 3. Client must NOT have already started interviewing or sending interview invites
    posted_age_hours = job.get("posted_age_hours")
    proposals_count = int(job.get("proposals_count") or 0)
    proposals_tier = str(job.get("proposals_tier") or "").lower()
    interviewing = int(activity.get("totalInvitedToInterview", 0) or activity.get("interviewing", 0) or 0)
    invites_sent = int(activity.get("invitesSent", 0) or job.get("invites_sent", 0) or 0)
    unanswered_invites = int(activity.get("unansweredInvites", 0) or 0)

    if posted_age_hours is not None and float(posted_age_hours) > MAX_FIRST_MOVER_AGE_HOURS:
        return True, "D8", f"Missed 1h first-mover window ({float(posted_age_hours):.2f}h old > {MAX_FIRST_MOVER_AGE_HOURS:.1f}h limit)"

    if proposals_count >= MAX_COMPETITION_PROPOSALS or any(
        t in proposals_tier for t in ("20 to 50", "20-50", "50+", "more than 50")
    ):
        return True, "D8", f"High competition ({proposals_count or proposals_tier} proposals >= {MAX_COMPETITION_PROPOSALS} limit)"

    if interviewing > 0 or invites_sent > 0 or unanswered_invites > 0:
        return (
            True,
            "D8",
            f"Client already interviewing or sent invites (interviewing={interviewing}, invites_sent={invites_sent})",
        )

    # D9: Free sample / unpaid test task > 1h
    if "free trial" in desc or "unpaid test" in desc or "sample task for free" in desc:
        return True, "D9", "Asks for free test task or trial before hire"

    # D10: Conflict with same client
    if client and open_clients:
        client_hash = client.get("hash") or client.get("id") or client.get("client_id")
        if client_hash and str(client_hash) in open_clients:
            return True, "D10", f"Conflict: open proposal or contract exists with client {client_hash}"

    return False, None, None


def score_job(
    job: Dict[str, Any],
    campaign_threshold: int = 70,
    scoring_version: str = "2.0-first-mover",
) -> Dict[str, Any]:
    """
    Computes weighted score (0–100) optimized for First-Mover Advantage (<1h) on
    High-Quality Client posts (high stars, high reviews/likes, frequent posting, strong spend/pay).
    """
    job = normalize_job_record(job)
    title = str(job.get("title", "")).lower()
    desc = str(job.get("description", "")).lower()
    skills_str = " ".join(str(s).lower() for s in (job.get("skills") or []))
    client = job.get("client_record") if isinstance(job.get("client_record"), dict) else (job.get("client") if isinstance(job.get("client"), dict) else {})
    act_stat = job.get("activityStat") if isinstance(job.get("activityStat"), dict) else {}
    activity = act_stat.get("jobActivity") if isinstance(act_stat.get("jobActivity"), dict) else (job.get("activity") if isinstance(job.get("activity"), dict) else {})

    reasons: List[str] = []
    breakdown: Dict[str, float] = {}

    # =========================================================================
    # Category A: Technical & Positioning Fit (20 pts)
    # =========================================================================
    # A1: Title / Core AI & Automation Fit (10 pts)
    strong_terms = [
        "claude", "claude code", "anthropic", "ai agent", "agentic", "n8n", "mcp",
        "model context protocol", "rag", "langchain", "langgraph", "crewai", "cursor",
        "lovable", "eval", "evals", "llm engineer", "ai engineer", "ai automation",
        "ai developer", "ai consultant", "ai solutions", "ai architect", "multi-agent",
        "voice ai", "ai integration", "llm", "openai", "gpt",
    ]
    adjacent_terms = [
        "automation", "integration", "chatbot", "make.com", "make", "zapier",
        "workflow", "api", "supabase", "pgvector", "python",
        "fastapi", "vector", "orchestrator", "assistant", "copilot", "ai",
        "full stack", "full-stack", "backend", "webhook", "scraping", "pipeline",
    ]
    if any(term in title for term in strong_terms):
        a1 = 10.0
        reasons.append("title_strong_match")
    elif any(term in title for term in adjacent_terms) or any(term in skills_str or term in desc[:600] for term in strong_terms):
        a1 = 8.5
        reasons.append("title_adjacent")
    elif any(term in skills_str or term in desc[:600] for term in adjacent_terms):
        a1 = 7.0
        reasons.append("title_adjacent")
    else:
        a1 = 0.0
        reasons.append("title_no_match")
    breakdown["A1_title_match"] = round(a1, 2)

    # A2: Business workflow clarity (4 pts)
    workflow_indicators = [
        "workflow", "automate", "automation", "sync", "pipeline", "connect", "hubspot",
        "slack", "notion", "crm", "lead", "production", "webhook", "api", "supabase",
        "postgres", "fastapi", "endpoint", "retrieval", "agent", "integration", "system",
    ]
    model_research = ["train a model", "fine-tuning llama", "research paper", "reproduce paper"]
    if any(term in desc for term in model_research):
        a2 = 1.0
    elif any(term in desc or term in title for term in workflow_indicators):
        a2 = 4.0
        reasons.append("workflow_clear")
    else:
        a2 = 3.0
    breakdown["A2_workflow_clarity"] = round(a2, 2)

    # A3: Offer ladder match (3 pts)
    if "audit" in title or "review" in title or "troubleshoot" in title or "fix" in title:
        a3 = 3.0
        reasons.append("rung_audit")
        rung_suggested = "audit"
    elif "sprint" in title or "quick" in title or "setup" in title or "set up" in title or "connect" in title:
        a3 = 3.0
        reasons.append("rung_sprint")
        rung_suggested = "sprint"
    elif "build" in title or "develop" in title or "system" in title or "engineer" in title or "specialist" in title or "architect" in title:
        a3 = 3.0
        reasons.append("rung_impl")
        rung_suggested = "implementation"
    else:
        a3 = 2.5
        rung_suggested = "sprint"
    breakdown["A3_rung_match"] = round(a3, 2)

    # A4: Proof match (3 pts)
    if any(k in title or k in desc for k in ["chatbot", "scraping", "warehouse", "mcp", "model context protocol", "n8n", "claude code", "supabase", "pgvector", "eval", "evals", "lovable", "cursor", "fastapi", "python"]):
        a4 = 3.0
        reasons.append("proof_direct")
    elif any(k in title or k in desc for k in ["rag", "agent", "integration", "claude", "openai", "automation", "webhook", "api"]):
        a4 = 2.2
        reasons.append("proof_adjacent")
    else:
        a4 = 0.5
        reasons.append("proof_none")
    breakdown["A4_proof_match"] = round(a4, 2)

    # =========================================================================
    # Category B: High-Quality Client Signal (35 pts)
    # Rewards high stars, high review/like counts, frequent job posting, high hire rate & spend
    # =========================================================================
    total_spent_val = client.get("total_spent")
    total_spent = parse_number(total_spent_val)
    jobs_posted = int(client.get("jobs_posted") or client.get("total_posted_jobs") or 0)
    jobs_with_hires = int(client.get("jobs_with_hires") or client.get("contracts_total") or 0)
    reviews_count = int(client.get("reviews_count") or 0)

    # B1: Total spent (10 pts)
    if total_spent is None:
        b1 = 5.0
        reasons.append("spend_unknown")
    else:
        if total_spent >= 25000:
            b1 = 10.0
            reasons.append("spend_high")
        elif total_spent >= 10000:
            b1 = 9.5
            reasons.append("spend_high")
        elif total_spent >= 2500:
            b1 = 8.5
            reasons.append("spend_high")
        elif total_spent >= 1000:
            b1 = 7.5
        elif total_spent >= 250:
            b1 = 5.5
        elif client.get("payment_verified", False):
            b1 = 4.0
            reasons.append("spend_zero_verified")
        else:
            b1 = 2.0
    breakdown["B1_total_spent"] = round(b1, 2)

    # B2: Posting frequency & hire rate (9 pts)
    hire_rate_val = client.get("hire_rate_percent") or client.get("hire_rate")
    hire_rate = parse_number(hire_rate_val)
    if (hire_rate is not None and hire_rate >= 70) or jobs_with_hires >= 10 or (jobs_posted >= 10 and jobs_with_hires >= 5):
        b2 = 9.0
        reasons.append("frequent_poster_high_hirer")
    elif (hire_rate is not None and hire_rate >= 45) or jobs_with_hires >= 3 or jobs_posted >= 5:
        b2 = 7.5
        if jobs_posted >= 5:
            reasons.append("frequent_poster")
    elif hire_rate is None:
        b2 = 6.5 if (total_spent and total_spent >= 1000) else 5.0
    else:
        b2 = 3.0
        reasons.append("hire_rate_low")
    breakdown["B2_hire_rate"] = round(b2, 2)

    # B3: Stars (rating) & review/like volume (8 pts)
    rating_val = client.get("rating") if client.get("rating") is not None else client.get("feedback_score")
    rating = parse_number(rating_val)
    if rating is None or rating == 0:
        b3 = 6.5 if (total_spent and total_spent >= 2500) else 5.0
    else:
        if rating >= 4.8 and (reviews_count >= 5 or jobs_with_hires >= 5 or (total_spent and total_spent >= 5000)):
            b3 = 8.0
            reasons.append("high_stars_high_reviews")
        elif rating >= 4.8:
            b3 = 7.5
            reasons.append("high_stars")
        elif rating >= 4.5:
            b3 = 6.0
        else:
            b3 = 1.5
            reasons.append("rating_low")
    breakdown["B3_rating"] = round(b3, 2)

    # B4: Willingness to pay higher rates (5 pts)
    job_type = str(job.get("type") or job.get("job_type") or "fixed").lower()
    raw_b = job.get("budget_fixed") or job.get("budget")
    bf = parse_number(raw_b.get("amount") if isinstance(raw_b, dict) else raw_b)
    raw_h = job.get("hourly_max") or job.get("hourly_budget")
    hm = parse_number(raw_h.get("max") if isinstance(raw_h, dict) else raw_h)

    avg_hourly = client.get("avg_hourly_paid") or client.get("avg_hourly_rate_paid")
    avg_h = parse_number(avg_hourly)
    spend_per_hire = (total_spent / float(jobs_with_hires)) if (total_spent and jobs_with_hires > 0) else None

    if avg_h is not None:
        if avg_h >= 50:
            b4 = 5.0
            reasons.append("high_payer")
        elif avg_h >= 30:
            b4 = 4.0
        elif avg_h >= 15:
            b4 = 2.5
        else:
            b4 = 0.0
            reasons.append("avg_paid_low")
    elif (hm is not None and hm >= 50) or (bf is not None and bf >= 1000) or (spend_per_hire is not None and spend_per_hire >= 800):
        b4 = 4.5
        reasons.append("high_payer")
    else:
        b4 = 3.2
    breakdown["B4_avg_hourly_paid"] = round(b4, 2)

    # B5: Payment verified (3 pts)
    if client.get("payment_verified", False):
        b5 = 3.0
    else:
        b5 = 0.5
        reasons.append("unverified")
    breakdown["B5_payment_verified"] = round(b5, 2)

    # =========================================================================
    # Category C: Job Economics & Pay Signal (15 pts)
    # =========================================================================
    if job_type == "fixed" and bf is not None:
        if bf >= 2500:
            c1 = 11.0
            reasons.append("budget_strong")
        elif bf >= 1000:
            c1 = 10.0
            reasons.append("budget_strong")
        elif bf >= 500:
            c1 = 8.5
        elif bf >= 250:
            c1 = 6.5
        else:
            c1 = 2.5
            reasons.append("budget_low")
    elif hm is not None:
        if hm >= 75:
            c1 = 11.0
            reasons.append("budget_strong")
        elif hm >= 50:
            c1 = 10.0
            reasons.append("budget_strong")
        elif hm >= 40:
            c1 = 8.5
        elif hm >= 30:
            c1 = 6.0
        else:
            c1 = 1.5
            reasons.append("ceiling_low")
    else:
        # Unspecified/open rate: reward if client has proven high spend
        c1 = 9.0 if (total_spent and total_spent >= 5000) else 6.5
    breakdown["C1_budget_signal"] = round(c1, 2)

    # C2: Duration (4 pts)
    duration_str = str(job.get("duration", "")).lower()
    if "> 3 months" in duration_str or "ongoing" in duration_str or "long-term" in desc:
        c2 = 4.0
    elif "1 to 3 months" in duration_str or "1-3 months" in duration_str:
        c2 = 3.5
    elif "< 1 month" in duration_str or "short" in duration_str:
        c2 = 2.8
    else:
        c2 = 2.8
    breakdown["C2_duration"] = round(c2, 2)

    # =========================================================================
    # Category D: First-Mover Speed & Low Competition (22 pts)
    # =========================================================================
    # D1: Proposals so far (10 pts — strict <20 window)
    prop_count = int(job.get("proposals_count") or 0)
    prop_tier = str(job.get("proposals_tier", "")).lower()
    if prop_count > 0:
        if prop_count < 5:
            d1 = 10.0
            reasons.append("first_mover_under_5_proposals")
        elif prop_count <= 10:
            d1 = 9.0
        elif prop_count <= 15:
            d1 = 7.5
        elif prop_count < 20:
            d1 = 6.0
        else:
            d1 = 0.0
            reasons.append("pile_on")
    elif "less than 5" in prop_tier:
        d1 = 10.0
        reasons.append("first_mover_under_5_proposals")
    elif "5 to 10" in prop_tier:
        d1 = 9.0
    elif "10 to 15" in prop_tier:
        d1 = 7.5
    elif "15 to 20" in prop_tier:
        d1 = 6.0
    elif "20 to 50" in prop_tier or "50+" in prop_tier or "more than 50" in prop_tier:
        d1 = 0.0
        reasons.append("pile_on")
    else:
        d1 = 8.5
    breakdown["D1_competition"] = round(d1, 2)

    # D2: Freshness within 1-Hour First-Mover Window (8 pts)
    posted_age = job.get("posted_age_hours")
    if posted_age is not None:
        age_f = float(posted_age)
        if age_f <= 0.25:
            d2 = 8.0
            reasons.append("fresh")
            reasons.append("first_mover_15m")
        elif age_f <= 0.50:
            d2 = 7.5
            reasons.append("fresh")
            reasons.append("first_mover_30m")
        elif age_f <= 1.0:
            d2 = 7.0
            reasons.append("fresh")
        else:
            d2 = 0.0
            reasons.append("stale")
    else:
        d2 = 6.5
    breakdown["D2_freshness"] = round(d2, 2)

    # D3: Zero-Interview Open Field (4 pts — penalize if client already interviewing/inviting)
    interviewing = int(activity.get("totalInvitedToInterview", 0) or activity.get("interviewing", 0) or 0)
    hired = int(activity.get("totalHired", 0) or activity.get("hired", 0) or 0)
    invites_sent = int(activity.get("invitesSent", 0) or job.get("invites_sent", 0) or 0)
    if interviewing > 0 or invites_sent > 0:
        d3 = 0.0
        reasons.append("client_interviewing")
    elif hired > 0:
        d3 = 0.0
        reasons.append("client_hired_already")
    else:
        d3 = 4.0
        reasons.append("zero_interviews_open_field")
    breakdown["D3_engagement"] = round(d3, 2)

    # =========================================================================
    # Category E: Low Friction (8 pts)
    # =========================================================================
    # E1: Screening questions (2 pts)
    questions = job.get("screening_questions") or []
    q_len = len(questions)
    if q_len <= 2:
        e1 = 2.0
    elif q_len <= 4:
        e1 = 1.5
    else:
        e1 = 0.8
        reasons.append("many_questions")
    breakdown["E1_questions"] = round(e1, 2)

    # E2: Red-flag language (3 pts)
    red_flag_hits = sum(1 for pat in RED_FLAG_PATTERNS if re.search(pat, desc))
    if red_flag_hits == 0:
        e2 = 3.0
    elif red_flag_hits == 1:
        e2 = 1.5
    else:
        e2 = 0.0
        reasons.append("red_flag_language")
    breakdown["E2_red_flags"] = round(e2, 2)

    # E3: Scope clarity (1.5 pts — do not heavily penalize concise posts from top clients)
    if len(desc) >= 150:
        e3 = 1.5
    elif len(desc) >= 60:
        e3 = 1.2
    else:
        e3 = 0.8
        reasons.append("scope_vague")
    breakdown["E3_scope_clarity"] = round(e3, 2)

    # E4: Connects cost (1.5 pts)
    connects_cost = int(job.get("connects_cost", 16) or 16)
    if connects_cost <= 16:
        e4 = 1.5
    elif connects_cost <= 20:
        e4 = 1.2
    else:
        e4 = 0.8
        reasons.append("connects_expensive")
    breakdown["E4_connects_cost"] = round(e4, 2)

    base_score = sum(breakdown.values())

    # Modifiers
    modifier_score = 0.0
    # +5 Elite Client Bonus (high stars + frequent poster/reviews + high spend)
    if (
        rating is not None
        and rating >= 4.75
        and ((total_spent is not None and total_spent >= 3000) or jobs_with_hires >= 5 or reviews_count >= 5 or jobs_posted >= 8)
    ):
        modifier_score += 5.0
        reasons.append("elite_client_bonus")

    # +3 First-Mover Prime Bonus (posted <= 30m ago and < 10 proposals)
    if posted_age is not None and float(posted_age) <= 0.5 and prop_count <= 10 and interviewing == 0 and invites_sent == 0:
        modifier_score += 3.0
        reasons.append("first_mover_prime")

    # +4 open related jobs/contracts
    if (client.get("open_jobs", 0) or 0) > 0 or (client.get("active_contracts", 0) or client.get("contracts_active", 0) or 0) > 0:
        modifier_score += 4.0
        reasons.append("open_related_jobs")

    # +4 Claude / Anthropic / MCP named
    if "claude" in title or "anthropic" in title or "claude" in desc or "anthropic" in desc or "mcp" in title:
        modifier_score += 4.0
        reasons.append("claude_named")

    # +2 IST-friendly timezone
    client_country = str(client.get("country", "")).lower()
    if any(c in client_country for c in ["united kingdom", "germany", "france", "netherlands", "uae", "switzerland", "ireland", "spain", "italy", "australia", "singapore"]):
        modifier_score += 2.0

    # -5 preferred location soft mismatch
    pref_locs = job.get("preferred_locations", {})
    if pref_locs and not pref_locs.get("location_required", False) and pref_locs.get("locations"):
        locs_str = " ".join(pref_locs.get("locations", [])).lower()
        if "united states" in locs_str and "india" not in locs_str:
            modifier_score -= 5.0
            reasons.append("location_soft_mismatch")

    breakdown["modifiers"] = round(modifier_score, 2)

    final_score = max(0.0, min(100.0, round(base_score + modifier_score, 1)))

    # Decision
    if final_score >= campaign_threshold:
        decision = "APPLY"
    elif final_score >= 55.0:
        decision = "REVIEW"
    else:
        decision = "SKIP"

    # Pricing hint
    pricing_hint = ""
    if job_type == "hourly":
        if avg_h is not None and avg_h < 15.0:
            pricing_hint = "Client pays avg <$15/hr; propose fixed Sprint ($599) instead of hourly"
        elif hm is not None and hm >= 45.0 and final_score >= 80.0:
            pricing_hint = f"Bid ceiling ${hm:.0f}/hr (score >=80) with fixed Sprint alternative"
        else:
            pricing_hint = "Bid sticker $65/hr with fixed Sprint alternative for <=10 hrs/week"
    else:
        if bf is not None and bf >= 1200:
            pricing_hint = f"Propose 3-milestone Implementation (Phase 1 ${min(bf, 3500.0):.0f})"
        else:
            pricing_hint = "Propose fixed Setup Sprint ($299/$599/$1,200) or Audit ($750)"

    return {
        "score": final_score,
        "score_breakdown": breakdown,
        "decision": decision,
        "reasons": reasons,
        "disqualifiers": [],
        "rung_suggested": rung_suggested,
        "pricing_hint": pricing_hint,
        "scoring_version": scoring_version,
    }
