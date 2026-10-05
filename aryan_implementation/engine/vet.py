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
    r"\bunity\b",
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

POLICY_DISQUALIFIERS = [
    r"pay outside upwork",
    r"communicate outside upwork",
    r"telegram",
    r"whatsapp",
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


def check_disqualifiers(
    job: Dict[str, Any],
    open_clients: Optional[Set[str]] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Check hard disqualifiers D1–D11.
    Returns (is_disqualified, disqualifier_id, reason_str).
    """
    title = str(job.get("title", "")).lower()
    desc = str(job.get("description", "")).lower()
    full_text = f"{title} {desc}"

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
    for pattern in CAPABILITY_DISQUALIFIERS:
        if re.search(pattern, title) or re.search(pattern, desc[:500]):
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
    client = job.get("client_record") or job.get("client")
    activity = job.get("activityStat", {}).get("jobActivity", {}) or job.get("activity", {})
    if client is not None:
        verified = client.get("payment_verified", False)
        total_spent = float(client.get("total_spent", 0.0) or 0.0)
        total_hired = int(activity.get("totalHired", 0) or 0)
        if not verified and total_spent == 0.0 and total_hired == 0:
            return True, "D6", "Payment unverified AND $0 spend AND 0 hires"

    # D7: Fixed budget < $100 or hourly max < $25
    job_type = str(job.get("type", "")).lower()
    budget_fixed = job.get("budget_fixed") or job.get("budget", {}).get("amount")
    hourly_max = job.get("hourly_max") or job.get("hourly_budget", {}).get("max")
    if job_type == "fixed" and budget_fixed is not None:
        try:
            if float(budget_fixed) < 100.0:
                return True, "D7", f"Fixed budget ${budget_fixed} is under $100 floor"
        except (ValueError, TypeError):
            pass
    elif job_type == "hourly" and hourly_max is not None:
        try:
            if float(hourly_max) < 25.0:
                return True, "D7", f"Hourly ceiling ${hourly_max}/hr is under $25 floor"
        except (ValueError, TypeError):
            pass

    # D8: Posted > 72h AND proposals >= 50 AND interviewing == 0
    posted_age_hours = job.get("posted_age_hours")
    proposals_count = job.get("proposals_count") or 0
    interviewing = int(activity.get("totalInvitedToInterview", 0) or activity.get("interviewing", 0) or 0)
    if posted_age_hours is not None and posted_age_hours > 72 and proposals_count >= 50 and interviewing == 0:
        return True, "D8", "Job posted > 72h ago with 50+ proposals and 0 interviewing"

    # D9: Free sample / unpaid test task > 1h
    if "free trial" in desc or "unpaid test" in desc or "sample task for free" in desc:
        return True, "D9", "Asks for free test task or trial before hire"

    # D10: Conflict with same client
    if client and open_clients:
        client_hash = client.get("hash") or client.get("id") or client.get("client_id")
        if client_hash and str(client_hash) in open_clients:
            return True, "D10", f"Conflict: open proposal or contract exists with client {client_hash}"

    # D11: Job already filled (totalHired >= personsToHire)
    contract_terms = job.get("contractTerms") or {}
    raw_pth = (
        job.get("persons_to_hire")
        or contract_terms.get("personsToHire")
        or job.get("personsToHire")
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

    return False, None, None


def score_job(
    job: Dict[str, Any],
    campaign_threshold: int = 70,
    scoring_version: str = "1.0",
) -> Dict[str, Any]:
    """
    Computes weighted score (0–100) across categories A–E and modifiers.
    Returns dictionary with score, breakdown, decision, reasons, rung, and pricing hint.
    """
    title = str(job.get("title", "")).lower()
    desc = str(job.get("description", "")).lower()
    client = job.get("client_record") or job.get("client", {})
    activity = job.get("activityStat", {}).get("jobActivity", {}) or job.get("activity", {})

    reasons: List[str] = []
    breakdown: Dict[str, float] = {}

    # Category A: Fit to Aryan's positioning (35 pts)
    # A1: Title match (15 pts)
    strong_terms = ["claude", "claude code", "anthropic", "ai agent", "n8n", "mcp", "rag"]
    adjacent_terms = ["automation", "integration", "llm", "chatbot", "make.com", "make", "zapier", "workflow", "api", "gpt"]
    if any(term in title for term in strong_terms):
        a1 = 15.0
        reasons.append("title_strong_match")
    elif any(term in title for term in adjacent_terms):
        a1 = 15.0 * 0.6  # 9.0
        reasons.append("title_adjacent")
    else:
        a1 = 0.0
        reasons.append("title_no_match")
    breakdown["A1_title_match"] = round(a1, 2)

    # A2: Business workflow clarity (8 pts)
    workflow_indicators = ["workflow", "automate", "sync", "pipeline", "connect", "hubspot", "slack", "notion", "crm", "lead"]
    model_research = ["train a model", "fine-tuning llama", "research paper", "reproduce paper"]
    if any(term in desc for term in model_research):
        a2 = 8.0 * 0.2
    elif any(term in desc for term in workflow_indicators):
        a2 = 8.0 * 1.0
        reasons.append("workflow_clear")
    else:
        a2 = 8.0 * 0.5
    breakdown["A2_workflow_clarity"] = round(a2, 2)

    # A3: Offer ladder match (7 pts)
    if "audit" in title or "review" in title:
        a3 = 7.0
        reasons.append("rung_audit")
        rung_suggested = "audit"
    elif "sprint" in title or "quick" in title or "setup" in title:
        a3 = 7.0
        reasons.append("rung_sprint")
        rung_suggested = "sprint"
    elif "build" in title or "develop" in title or "system" in title:
        a3 = 7.0
        reasons.append("rung_impl")
        rung_suggested = "implementation"
    else:
        a3 = 7.0 * 0.5
        rung_suggested = "sprint"
    breakdown["A3_rung_match"] = round(a3, 2)

    # A4: Proof match (5 pts)
    if any(k in title or k in desc for k in ["chatbot", "scraping", "warehouse", "mcp", "n8n"]):
        a4 = 5.0
        reasons.append("proof_direct")
    elif any(k in title or k in desc for k in ["rag", "agent", "integration"]):
        a4 = 2.5
        reasons.append("proof_adjacent")
    else:
        a4 = 0.0
        reasons.append("proof_none")
    breakdown["A4_proof_match"] = round(a4, 2)

    # Category B: Client Quality (25 pts)
    # B1: Total spent (8 pts)
    total_spent_val = client.get("total_spent")
    if total_spent_val is None:
        b1 = 8.0 * 0.4  # unknown = 0.4
        reasons.append("spend_unknown")
    else:
        total_spent = float(total_spent_val)
        if total_spent >= 10000:
            b1 = 8.0 * 1.0
            reasons.append("spend_high")
        elif total_spent >= 1000:
            b1 = 8.0 * 0.8
        elif total_spent >= 100:
            b1 = 8.0 * 0.5
        elif client.get("payment_verified", False):
            b1 = 8.0 * 0.3
            reasons.append("spend_zero_verified")
        else:
            b1 = 8.0 * 0.2
    breakdown["B1_total_spent"] = round(b1, 2)

    # B2: Hire rate (5 pts)
    hire_rate_val = client.get("hire_rate_percent") or client.get("hire_rate")
    if hire_rate_val is None:
        b2 = 5.0 * 0.5
    else:
        hire_rate = float(hire_rate_val)
        if hire_rate >= 70:
            b2 = 5.0 * 1.0
        elif hire_rate >= 40:
            b2 = 5.0 * 0.7
        else:
            b2 = 5.0 * 0.3
            reasons.append("hire_rate_low")
    breakdown["B2_hire_rate"] = round(b2, 2)

    # B3: Rating (4 pts)
    rating_val = client.get("rating")
    if rating_val is None or float(rating_val) == 0:
        b3 = 4.0 * 0.6
    else:
        rating = float(rating_val)
        if rating >= 4.8:
            b3 = 4.0 * 1.0
        elif rating >= 4.5:
            b3 = 4.0 * 0.7
        else:
            b3 = 4.0 * 0.2
            reasons.append("rating_low")
    breakdown["B3_rating"] = round(b3, 2)

    # B4: Avg hourly paid (5 pts)
    avg_hourly = client.get("avg_hourly_paid") or client.get("avg_hourly_rate_paid")
    if avg_hourly is None:
        b4 = 5.0 * 0.5
    else:
        avg_h = float(avg_hourly)
        if avg_h >= 50:
            b4 = 5.0 * 1.0
        elif avg_h >= 30:
            b4 = 5.0 * 0.7
        elif avg_h >= 15:
            b4 = 5.0 * 0.3
        else:
            b4 = 0.0
            reasons.append("avg_paid_low")
    breakdown["B4_avg_hourly_paid"] = round(b4, 2)

    # B5: Payment verified (3 pts)
    if client.get("payment_verified", False):
        b5 = 3.0 * 1.0
    else:
        b5 = 3.0 * 0.3
        reasons.append("unverified")
    breakdown["B5_payment_verified"] = round(b5, 2)

    # Category C: Money (15 pts)
    job_type = str(job.get("type", "fixed")).lower()
    budget_fixed = job.get("budget_fixed") or job.get("budget", {}).get("amount")
    hourly_max = job.get("hourly_max") or job.get("hourly_budget", {}).get("max")

    if job_type == "fixed" and budget_fixed is not None:
        bf = float(budget_fixed)
        if bf >= 3000:
            c1 = 10.0 * 1.0
            reasons.append("budget_strong")
        elif bf >= 1000:
            c1 = 10.0 * 0.9
        elif bf >= 500:
            c1 = 10.0 * 0.7
        elif bf >= 250:
            c1 = 10.0 * 0.5
        else:
            c1 = 10.0 * 0.2
            reasons.append("budget_low")
    elif hourly_max is not None:
        hm = float(hourly_max)
        if hm >= 80:
            c1 = 10.0 * 1.0
            reasons.append("budget_strong")
        elif hm >= 60:
            c1 = 10.0 * 0.9
        elif hm >= 45:
            c1 = 10.0 * 0.7
        elif hm >= 30:
            c1 = 10.0 * 0.4
        else:
            c1 = 10.0 * 0.1
            reasons.append("ceiling_low")
    else:
        c1 = 10.0 * 0.5
    breakdown["C1_budget_signal"] = round(c1, 2)

    # C2: Duration (5 pts)
    duration_str = str(job.get("duration", "")).lower()
    if "> 3 months" in duration_str or "ongoing" in duration_str or "long-term" in desc:
        c2 = 5.0 * 1.0
    elif "1 to 3 months" in duration_str or "1-3 months" in duration_str:
        c2 = 5.0 * 0.8
    elif "< 1 month" in duration_str or "short" in duration_str:
        c2 = 5.0 * 0.5
    else:
        c2 = 5.0 * 0.3
    breakdown["C2_duration"] = round(c2, 2)

    # Category D: Competition & Timing (15 pts)
    # D1: Proposals so far (7 pts)
    prop_count = job.get("proposals_count") or 0
    prop_tier = str(job.get("proposals_tier", "")).lower()
    if prop_count > 0:
        if prop_count < 5:
            d1 = 7.0 * 1.0
        elif prop_count <= 10:
            d1 = 7.0 * 0.9
        elif prop_count <= 15:
            d1 = 7.0 * 0.7
        elif prop_count <= 20:
            d1 = 7.0 * 0.5
        elif prop_count < 50:
            d1 = 7.0 * 0.25
        else:
            d1 = 7.0 * 0.05
            reasons.append("pile_on")
    elif "less than 5" in prop_tier:
        d1 = 7.0 * 1.0
    elif "5 to 10" in prop_tier:
        d1 = 7.0 * 0.9
    elif "10 to 15" in prop_tier:
        d1 = 7.0 * 0.7
    elif "15 to 20" in prop_tier:
        d1 = 7.0 * 0.5
    elif "20 to 50" in prop_tier:
        d1 = 7.0 * 0.25
    else:
        d1 = 7.0 * 0.05
        reasons.append("pile_on")
    breakdown["D1_competition"] = round(d1, 2)

    # D2: Freshness (4 pts)
    posted_age = job.get("posted_age_hours")
    if posted_age is not None:
        if posted_age < 6:
            d2 = 4.0 * 1.0
            reasons.append("fresh")
        elif posted_age <= 24:
            d2 = 4.0 * 0.8
        elif posted_age <= 72:
            d2 = 4.0 * 0.5
        else:
            d2 = 4.0 * 0.2
            reasons.append("stale")
    else:
        d2 = 4.0 * 0.8
    breakdown["D2_freshness"] = round(d2, 2)

    # D3: Client engagement (4 pts)
    interviewing = int(activity.get("totalInvitedToInterview", 0) or activity.get("interviewing", 0) or 0)
    hired = int(activity.get("totalHired", 0) or activity.get("hired", 0) or 0)
    invites_sent = int(activity.get("invitesSent", 0) or 0)
    if interviewing > 0 or invites_sent > 0:
        d3 = 4.0 * 1.0
        reasons.append("client_interviewing")
    elif hired > 0:
        d3 = 0.0
        reasons.append("client_hired_already")
    else:
        d3 = 4.0 * 0.5
    breakdown["D3_engagement"] = round(d3, 2)

    # Category E: Risk & Friction (10 pts)
    # E1: Screening questions (3 pts)
    questions = job.get("screening_questions") or []
    q_len = len(questions)
    if q_len <= 2:
        e1 = 3.0 * 1.0
    elif q_len <= 4:
        e1 = 3.0 * 0.6
    else:
        e1 = 3.0 * 0.3
        reasons.append("many_questions")
    breakdown["E1_questions"] = round(e1, 2)

    # E2: Red-flag language (3 pts)
    red_flag_hits = sum(1 for pat in RED_FLAG_PATTERNS if re.search(pat, desc))
    if red_flag_hits == 0:
        e2 = 3.0 * 1.0
    elif red_flag_hits == 1:
        e2 = 3.0 * 0.5
    else:
        e2 = 0.0
        reasons.append("red_flag_language")
    breakdown["E2_red_flags"] = round(e2, 2)

    # E3: Scope clarity (2 pts)
    if len(desc) > 300 and any(w in desc for w in ["deliverable", "requirement", "goal", "scope", "phase"]):
        e3 = 2.0 * 1.0
    elif len(desc) < 150:
        e3 = 2.0 * 0.2
        reasons.append("scope_vague")
    else:
        e3 = 2.0 * 0.6
    breakdown["E3_scope_clarity"] = round(e3, 2)

    # E4: Connects cost (2 pts)
    connects_cost = int(job.get("connects_cost", 16) or 16)
    if connects_cost <= 12:
        e4 = 2.0 * 1.0
    elif connects_cost <= 18:
        e4 = 2.0 * 0.7
    else:
        e4 = 2.0 * 0.4
        reasons.append("connects_expensive")
    breakdown["E4_connects_cost"] = round(e4, 2)

    base_score = sum(breakdown.values())

    # Modifiers
    modifier_score = 0.0
    # +5 open related jobs/contracts
    if client.get("open_jobs", 0) > 0 or client.get("active_contracts", 0) > 0:
        modifier_score += 5.0
        reasons.append("open_related_jobs")

    # +5 Claude / Anthropic named
    if "claude" in title or "anthropic" in title or "claude" in desc or "anthropic" in desc:
        modifier_score += 5.0
        reasons.append("claude_named")

    # +3 IST-friendly timezone
    client_country = str(client.get("country", "")).lower()
    if any(c in client_country for c in ["united kingdom", "germany", "france", "netherlands", "uae", "switzerland", "ireland", "spain", "italy"]):
        modifier_score += 3.0

    # -10 pile-on and bidding above avg paid
    if prop_count >= 50 and avg_hourly is not None and float(avg_hourly) < 25.0:
        modifier_score -= 10.0

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
        if avg_hourly is not None and float(avg_hourly) < 15.0:
            pricing_hint = "Client pays avg <$15/hr; propose fixed Sprint ($599) instead of hourly"
        elif hourly_max is not None and float(hourly_max) >= 45.0 and final_score >= 80.0:
            pricing_hint = f"Bid ceiling ${hourly_max}/hr (score >=80) with fixed Sprint alternative"
        else:
            pricing_hint = "Bid sticker $65/hr with fixed Sprint alternative for <=10 hrs/week"
    else:
        if budget_fixed is not None and float(budget_fixed) >= 1200:
            pricing_hint = f"Propose 3-milestone Implementation (Phase 1 ${min(float(budget_fixed), 3500):.0f})"
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
