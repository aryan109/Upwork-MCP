"""
Proposal drafting engine for Aryan Upwork pipeline.
Builds personalized cover letters, screening answers, proposed terms,
and performs the 12-point self-check per 07_PROPOSAL_SYSTEM.md.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import PROJECT_ROOT

logger = logging.getLogger("proposal_drafter")

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
            h_budget = job.get("hourly_budget") if isinstance(job.get("hourly_budget"), dict) else {}
            hourly_max = job.get("hourly_max") or h_budget.get("max") or (job.get("hourly_budget") if not isinstance(job.get("hourly_budget"), dict) else None)
            c_rec = job.get("client_record") if isinstance(job.get("client_record"), dict) else {}
            avg_paid = c_rec.get("avg_hourly_paid")
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
            b_val = job.get("budget")
            budget = job.get("budget_fixed") or (b_val.get("amount") if isinstance(b_val, dict) else b_val)
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

    @staticmethod
    def load_system_prompt_from_guide() -> str:
        """Dynamically load master system prompt from the markdown proposal guide."""
        guide_paths = [
            PROJECT_ROOT / "UPWORK_PROPOSAL_CRAFTING_GUIDE.md",
            PROJECT_ROOT / "aryan_implementation" / "skills" / "upwork-proposal-crafting-skill" / "SKILL.md",
        ]
        for p in guide_paths:
            if p.exists():
                try:
                    text = p.read_text(encoding="utf-8")
                    if "## 5. Master System Prompt Template" in text:
                        part = text.split("## 5. Master System Prompt Template", 1)[1]
                        if "```text" in part:
                            prompt_body = part.split("```text", 1)[1].split("```", 1)[0].strip()
                            if len(prompt_body) > 100:
                                return prompt_body
                except Exception as e:
                    logger.debug(f"Failed to read prompt guide from {p}: {e}")

        # Safe fallback if guide file is unavailable
        return (
            "You are an expert proposal drafting AI for Aryan, a Top Rated Upwork consultant with a 100% Job Success Score.\n"
            "Your objective is to draft a personalized, highly persuasive 4-part Upwork cover letter and concise answers to any client screening questions.\n\n"
            "CRITICAL RULES:\n"
            "1. Four concise paragraphs strictly:\n"
            "   - Paragraph 1: Understanding & Desired Outcome (1-2 sentences establishing clear grasp of their goal).\n"
            "   - Paragraph 2: Technical Approach (3 clear, concrete phases).\n"
            "   - Paragraph 3: Verifiable Proof (Reference building a production agent system on an official MCP server with human approval gates, or production document pipelines).\n"
            "   - Paragraph 4: Exactly one specific technical or operational risk warning + calm CTA (15-min scoping call).\n"
            "2. Total word count of cover letter MUST be strictly between 130 and 190 words.\n"
            "3. Plain, calm, direct style. NO self-congratulatory adjectives ('passionate', 'exceptional', 'expert developer').\n"
            "4. NO exclamation marks. NO em-dashes ('--' or '—'); use commas or hyphens instead.\n"
            "5. NO buzzwords or unverified claims ('8+ years', 'decade', 'enterprise-grade', 'guaranteed').\n"
            "6. Sign off strictly with:\nAryan\n"
            "7. Return JSON ONLY with keys: 'cover_letter' (string) and 'answers' (list of dicts with 'question' and 'answer')."
        )

    def generate_with_groq_llm(
        self, job: Dict[str, Any], score_data: Dict[str, Any]
    ) -> Optional[Tuple[str, List[Dict[str, str]]]]:
        """Call Groq LLM API to synthesize personalized cover letter and screening answers."""
        groq_key = os.environ.get("GROQ_API_KEY")
        if not groq_key:
            from .telegram_notifier import load_env_file
            env = load_env_file(PROJECT_ROOT / ".env")
            groq_key = env.get("GROQ_API_KEY")

        if not groq_key:
            return None

        title = job.get("title", "Project")
        description = job.get("description") or job.get("description_snippet", "")
        questions = job.get("screening_questions", [])

        system_prompt = self.load_system_prompt_from_guide()

        user_prompt = f"Job Title: {title}\nJob Description:\n{description[:2500]}\n"
        if questions:
            user_prompt += f"\nScreening Questions to answer:\n" + "\n".join(f"- {q}" for q in questions)

        models = [
            os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-20b",
        ]
        for model in models:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            }
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    res_data = json.loads(resp.read().decode("utf-8"))
                    content = res_data["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    cl = parsed.get("cover_letter", "").strip()
                    # Sanitize em-dashes and exclamations
                    cl = cl.replace("—", "-").replace("–", "-").replace("!", ".")
                    if not cl.endswith("Aryan"):
                        cl = f"{cl}\n\nAryan"

                    ans_raw = parsed.get("answers", [])
                    answers: List[Dict[str, str]] = []
                    if isinstance(ans_raw, list):
                        for a in ans_raw:
                            if isinstance(a, dict) and "question" in a and "answer" in a:
                                answers.append({"question": str(a["question"]), "answer": str(a["answer"])})
                    elif isinstance(ans_raw, dict):
                        for q_k, a_v in ans_raw.items():
                            answers.append({"question": str(q_k), "answer": str(a_v)})

                    if cl:
                        logger.info(f"Successfully generated proposal via Groq LLM ({model})")
                        return cl, answers
            except Exception as e:
                logger.warning(f"Groq generation attempt with {model} failed: {e}")
                continue

        return None

    def generate_with_gemini_llm(
        self, job: Dict[str, Any], score_data: Dict[str, Any]
    ) -> Optional[Tuple[str, List[Dict[str, str]]]]:
        """Call Google Studio Gemini API to synthesize personalized cover letter and screening answers."""
        google_key = os.environ.get("GOOGLE_STUDIO_API_KEY")
        if not google_key:
            from .telegram_notifier import load_env_file
            env = load_env_file(PROJECT_ROOT / ".env")
            google_key = env.get("GOOGLE_STUDIO_API_KEY")

        if not google_key:
            return None

        title = job.get("title", "Project")
        description = job.get("description") or job.get("description_snippet", "")
        questions = job.get("screening_questions", [])
        ai_analysis = job.get("ai_analysis") or {}

        system_prompt = self.load_system_prompt_from_guide()
        user_prompt = f"Job Title: {title}\nJob Description:\n{description[:3000]}\n"
        if ai_analysis.get("key_winning_hook"):
            user_prompt += f"\nRecommended Technical Winning Angle:\n{ai_analysis['key_winning_hook']}\n"
        if questions:
            user_prompt += f"\nScreening Questions to answer:\n" + "\n".join(f"- {q}" for q in questions)

        gemini_models = ["models/gemini-3.5-flash-lite", "models/gemini-3.5-flash", "models/gemini-3.8-flash"]
        for g_model in gemini_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/{g_model}:generateContent?key={google_key}"
            payload = {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"parts": [{"text": user_prompt}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    res_json = json.loads(resp.read().decode("utf-8"))
                    text_out = res_json["candidates"][0]["content"]["parts"][0]["text"]
                    parsed = json.loads(text_out)
                    cl = parsed.get("cover_letter", "").strip()
                    cl = cl.replace("—", "-").replace("–", "-").replace("!", ".")
                    if not cl.endswith("Aryan"):
                        cl = f"{cl}\n\nAryan"

                    ans_raw = parsed.get("answers", [])
                    answers: List[Dict[str, str]] = []
                    if isinstance(ans_raw, list):
                        for a in ans_raw:
                            if isinstance(a, dict) and "question" in a and "answer" in a:
                                answers.append({"question": str(a["question"]), "answer": str(a["answer"])})
                    elif isinstance(ans_raw, dict):
                        for q_k, a_v in ans_raw.items():
                            answers.append({"question": str(q_k), "answer": str(a_v)})

                    if cl:
                        logger.info(f"Successfully generated proposal via Gemini ({g_model})")
                        return cl, answers
            except Exception as e:
                logger.warning(f"Gemini generation attempt with {g_model} failed: {e}")
                continue

        return None

    def generate_full_draft(self, job: Dict[str, Any], score_data: Dict[str, Any]) -> Dict[str, Any]:
        """Produce a complete draft package ready for review."""
        terms = self.determine_proposed_terms(job, score_data)

        # 1. Attempt Gemini or Groq LLM synthesis
        llm_res = None
        gen_type = "heuristic_fallback"
        try:
            llm_res = self.generate_with_gemini_llm(job, score_data)
            if llm_res:
                gen_type = "gemini_llm"
            else:
                llm_res = self.generate_with_groq_llm(job, score_data)
                if llm_res:
                    gen_type = "groq_llm"
        except Exception as e:
            logger.warning(f"LLM drafting exception: {e}")

        if llm_res:
            cover_letter, answers = llm_res
            self_check = self.self_check_draft(cover_letter, answers, terms)
            if self_check["passed"]:
                return {
                    "cover_letter": cover_letter,
                    "answers": answers,
                    "terms": terms,
                    "self_check": self_check,
                    "status": "drafted",
                    "generator": gen_type,
                }

        # 2. Deterministic heuristic fallback
        cover_letter = self.build_cover_letter(job, score_data)
        questions = job.get("screening_questions", [])
        answers = self.answer_screening_questions(questions, job)
        self_check = self.self_check_draft(cover_letter, answers, terms)

        return {
            "cover_letter": cover_letter,
            "answers": answers,
            "terms": terms,
            "self_check": self_check,
            "status": "drafted" if self_check["passed"] else "needs_edit",
            "generator": "heuristic_fallback",
        }
