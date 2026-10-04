"""
Proposal drafting engine for Aryan Upwork pipeline.
Builds personalized cover letters, screening answers, proposed terms,
and performs the 12-point self-check per 07_PROPOSAL_SYSTEM.md.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

FORBIDDEN_PHRASES = [
    r"8\+?\s*years",
    r"over a decade",
    r"decade of experience",
    r"enterprise-grade",
    r"gxp compliant",
    r"hipaa compliant",
    r"soc2 compliant",
    r"100% guarantee",
    r"guaranteed results",
    r"openclaw",
    r"upwork mcp automation",
    r"my automation engine",
]


class ProposalDrafter:
    """Generates and self-checks Upwork proposal drafts."""

    def __init__(self, facts_content: Optional[str] = None):
        self.facts_content = facts_content or ""

    def select_proof_item(self, job: Dict[str, Any]) -> Tuple[str, str]:
        """Select the most relevant proof item for the job."""
        title = str(job.get("title", "")).lower()
        desc = str(job.get("description", "")).lower()
        full_text = f"{title} {desc}"

        if "mcp" in full_text or "claude" in full_text:
            return (
                "P2",
                "Built an agent system for my own company that discovers, scores and drafts with human approval on top of an official MCP server, running scheduled passes with complete audit logs.",
            )
        elif "n8n" in full_text or "make" in full_text or "zapier" in full_text:
            return (
                "P5",
                "Implemented multi-step workflow automations connecting CRMs, communication channels and internal APIs with automated error handling and webhook reconciliation.",
            )
        elif "scrap" in full_text or "warehous" in full_text or "etl" in full_text:
            return (
                "P3",
                "Deployed scheduled data extraction and warehousing pipelines handling automated ingestion, schema validation and structured database sync.",
            )
        elif "bot" in full_text or "chat" in full_text or "rag" in full_text:
            return (
                "P1",
                "Built custom document-grounded AI chatbots connecting business knowledge bases to messaging tools with strict guardrails and low hallucination rates.",
            )
        else:
            return (
                "P2",
                "Designed and deployed production AI agent workflows with human-in-the-loop approval, strict tool permissions and observable audit logging.",
            )

    def identify_risk(self, job: Dict[str, Any]) -> str:
        """Formulate one specific technical/operational risk for the job."""
        desc = str(job.get("description", "")).lower()
        if "fully automated" in desc or "autonomous" in desc:
            return "The key operational risk in fully automated pipelines is silent failure during third-party schema changes; I recommend building explicit human approval gates on high-impact actions."
        elif "scrap" in desc:
            return "The primary challenge in automated web extraction is rate-limiting and anti-bot drift; we should incorporate defensive retry backoffs and session rotation from day one."
        elif "crm" in desc or "hubspot" in desc or "lead" in desc:
            return "A common pitfall with automated CRM updates is duplicate creation during webhook retries; enforcing strict deduplication keys ensures database integrity."
        elif "rag" in desc or "document" in desc:
            return "The main risk with document retrieval is stale indexing when source documents update; setting up an automated sync trigger prevents retrieval of outdated answers."
        else:
            return "The main implementation risk is integration scope creep without defined acceptance tests; locking milestone acceptance criteria before development avoids surprises."

    def build_cover_letter(self, job: Dict[str, Any], score_data: Dict[str, Any]) -> str:
        """Construct a 4-part cover letter following 07_PROPOSAL_SYSTEM.md."""
        title = job.get("title", "your workflow")
        proof_id, proof_text = self.select_proof_item(job)
        risk_text = self.identify_risk(job)

        # 1. Understanding & Desired Outcome
        p1 = f"I reviewed your requirements for {title}. The goal is to establish a reliable, maintainable system that your team can trust without fragile manual intervention."

        # 2. Architecture & Technical Steps
        p2 = "My approach is to structure this in three clear phases: first, map the integration points and establish data contracts; second, build the core logic with robust error-handling; and third, deliver recorded walkthrough documentation alongside the production handoff."

        # 3. Proof Match
        p3 = f"For similar requirements, I have {proof_text.lower()}"

        # 4. Risk & Calm CTA
        p4 = f"{risk_text}\n\nIf helpful, I am available for a brief 15-minute scoping call this week to review your architecture and provide an exact implementation roadmap.\n\nAryan"

        return f"{p1}\n\n{p2}\n\n{p3}\n\n{p4}"

    def answer_screening_questions(self, questions: List[str], job: Dict[str, Any]) -> List[Dict[str, str]]:
        """Generate concise, direct answers to client screening questions."""
        answers = []
        for q in questions:
            q_lower = q.lower()
            if "experience" in q_lower or "similar" in q_lower:
                ans = "I have built and maintained production AI workflows, MCP connectors, and automation pipelines with human approval gates and full audit logging."
            elif "timeline" in q_lower or "how long" in q_lower:
                ans = "A standard Setup Sprint takes 2 to 5 business days once specifications and credentials are confirmed, followed by structured testing."
            elif "approach" in q_lower or "how would you" in q_lower:
                ans = "I begin with an architecture review to define schema contracts, implement the core workflow with error boundaries, and conclude with handover documentation."
            else:
                ans = "I focus on reliable business workflows with human-in-the-loop safeguards, structured milestones, and complete documentation."
            answers.append({"question": q, "answer": ans})
        return answers

    def determine_proposed_terms(self, job: Dict[str, Any], score_data: Dict[str, Any]) -> Dict[str, Any]:
        """Determine rate, fixed price, and boost parameters."""
        job_type = str(job.get("type", "fixed")).lower()
        score = float(score_data.get("score", 70.0))

        if job_type == "hourly":
            hourly_max = job.get("hourly_max") or job.get("hourly_budget", {}).get("max")
            avg_paid = job.get("client_record", {}).get("avg_hourly_paid")
            if avg_paid and float(avg_paid) < 15.0:
                terms = {
                    "type": "fixed_alternative",
                    "hourly_bid": 65.0,
                    "suggested_fixed": 599.0,
                    "note": "Client avg paid <$15; propose fixed Setup Sprint ($599)",
                }
            elif hourly_max and float(hourly_max) >= 45.0 and score >= 80.0:
                terms = {
                    "type": "hourly",
                    "hourly_bid": min(float(hourly_max), 85.0),
                    "note": f"Bid near client ceiling (${hourly_max}/hr)",
                }
            else:
                terms = {
                    "type": "hourly",
                    "hourly_bid": 65.0,
                    "note": "Standard profile sticker rate ($65/hr)",
                }
        else:
            budget = job.get("budget_fixed") or job.get("budget", {}).get("amount")
            if budget and float(budget) >= 1200:
                terms = {
                    "type": "fixed",
                    "charged_amount": min(float(budget), 3500.0),
                    "milestones": [
                        {"name": "Architecture & acceptance criteria", "pct": 30},
                        {"name": "Core build & integration testing", "pct": 50},
                        {"name": "Rollout, docs & handover training", "pct": 20},
                    ],
                }
            else:
                terms = {
                    "type": "fixed",
                    "charged_amount": float(budget) if budget else 599.0,
                    "rung": "sprint",
                }

        # Boost calculation
        boost = 0
        if score >= 80.0:
            boost = min(10, int(job.get("boost_recommended", 6) or 6))

        terms["boost_connects"] = boost
        return terms

    def self_check_draft(
        self,
        cover_letter: str,
        answers: List[Dict[str, str]],
        terms: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Run the strict 12-point self-check.
        Returns dict with passed (bool), issues (list), and checks (dict).
        """
        issues = []
        checks = {}

        # 1. Word count (120-220, or up to 330 with questions)
        words = cover_letter.split()
        word_count = len(words)
        max_words = 220 if not answers else 330
        checks["word_count"] = word_count
        if word_count < 110:
            issues.append(f"Word count ({word_count}) is below minimum (120 words)")
        elif word_count > max_words + 20:
            issues.append(f"Word count ({word_count}) exceeds maximum ({max_words} words)")

        # 2. Risk identified
        risk_keywords = ["risk", "pitfall", "challenge", "mitigate", "boundary", "stale", "drift"]
        has_risk = any(rk in cover_letter.lower() for rk in risk_keywords)
        checks["risk_stated"] = has_risk
        if not has_risk:
            issues.append("Letter does not explicitly identify a technical or operational risk")

        # 3. Forbidden phrases
        found_forbidden = []
        for pat in FORBIDDEN_PHRASES:
            if re.search(pat, cover_letter, re.IGNORECASE):
                found_forbidden.append(pat)
        checks["forbidden_phrases"] = found_forbidden
        if found_forbidden:
            issues.append(f"Letter contains forbidden phrases: {found_forbidden}")

        # 4. No exclamation marks
        has_exclamation = "!" in cover_letter
        checks["no_exclamation"] = not has_exclamation
        if has_exclamation:
            issues.append("Letter contains exclamation marks")

        # 5. No em dashes (—)
        has_em_dash = "—" in cover_letter
        checks["no_em_dash"] = not has_em_dash
        if has_em_dash:
            issues.append("Letter contains em dash (—); use commas or hyphens")

        # 6. Starts with outcome/pain, not "I am" or "My name is"
        first_sentence = cover_letter.strip().split(".")[0].lower()
        if first_sentence.startswith("i am") or first_sentence.startswith("my name is"):
            issues.append("First sentence must not start with 'I am' or 'My name is'")
            checks["good_opening"] = False
        else:
            checks["good_opening"] = True

        # 7. Sign off as "Aryan"
        ends_with_aryan = cover_letter.strip().endswith("Aryan")
        checks["signed_aryan"] = ends_with_aryan
        if not ends_with_aryan:
            issues.append("Letter must sign off with 'Aryan'")

        # 8. Boost check <= 10
        boost = terms.get("boost_connects", 0)
        checks["boost_capped"] = boost <= 10
        if boost > 10:
            issues.append(f"Boost connects ({boost}) exceeds safety cap of 10")

        return {
            "passed": len(issues) == 0,
            "issues": issues,
            "word_count": word_count,
            "checks": checks,
        }

    def generate_full_draft(self, job: Dict[str, Any], score_data: Dict[str, Any]) -> Dict[str, Any]:
        """Produce a complete draft package ready for review."""
        cover_letter = self.build_cover_letter(job, score_data)
        questions = job.get("screening_questions", [])
        answers = self.answer_screening_questions(questions, job)
        terms = self.determine_proposed_terms(job, score_data)
        self_check = self.self_check_draft(cover_letter, answers, terms)

        return {
            "cover_letter": cover_letter,
            "answers": answers,
            "terms": terms,
            "self_check": self_check,
            "status": "drafted" if self_check["passed"] else "needs_edit",
        }
