"""
AI Job Analysis & Bad Client Detection Engine for Aryan Upwork Acquisition Pipeline.
Deeply analyzes job descriptions, client history, scope feasibility, and red flags.
Powered primarily by Google Studio Gemini (gemini-3.8-flash / 3.5-flash) with Groq fallback.
Continuously learns from Aryan's feedback to eliminate effort wasted on bad clients.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from .ai_client_learner import ClientLearningEngine
from .config import PROJECT_ROOT, STATE_DIR

logger = logging.getLogger("ai_job_analyzer")


class AIJobAnalyzer:
    """Evaluates candidate Upwork jobs using Google Gemini or Groq LLM with adaptive learning."""

    def __init__(self, state_dir: Optional[Path] = None):
        self.state_dir = state_dir or STATE_DIR
        self.learner = ClientLearningEngine(self.state_dir)

    def _get_api_keys(self) -> Tuple[Optional[str], Optional[str]]:
        """Retrieve Google Studio and Groq API keys."""
        google_key = os.environ.get("GOOGLE_STUDIO_API_KEY")
        groq_key = os.environ.get("GROQ_API_KEY")

        if not google_key or not groq_key:
            from .telegram_notifier import load_env_file
            env = load_env_file(PROJECT_ROOT / ".env")
            google_key = google_key or env.get("GOOGLE_STUDIO_API_KEY")
            groq_key = groq_key or env.get("GROQ_API_KEY")

        return google_key, groq_key

    def analyze_job_fit(
        self,
        job: Dict[str, Any],
        heuristic_score_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Deeply vet a job's true fit, client trustworthiness, and win probability.
        Returns structured analysis with fit_score, decision, client_risk_level, and winning hook.
        """
        google_key, groq_key = self._get_api_keys()
        h_score = (heuristic_score_data or {}).get("score", 70.0)
        h_decision = (heuristic_score_data or {}).get("decision", "REVIEW")

        title = str(job.get("title", ""))
        desc = str(job.get("description") or job.get("description_snippet", ""))
        client = job.get("client_record") if isinstance(job.get("client_record"), dict) else (job.get("client") if isinstance(job.get("client"), dict) else {})
        activity = job.get("activityStat", {}).get("jobActivity", {}) if isinstance(job.get("activityStat"), dict) else {}
        budget_str = f"Budget: {job.get('budget')} | Hourly: {job.get('hourly_budget') or job.get('hourly_max')}"
        learning_context = self.learner.get_learning_context()

        system_prompt = (
            "You are Aryan's Senior AI Lead Vetting Specialist on Upwork. "
            "Aryan is a Top Rated developer with a 100% Job Success Score specializing in: "
            "Claude Code, Model Context Protocol (MCP), production AI agent architectures, FastAPI/Django backends, "
            "eval-driven document RAG, and resilient n8n/Make automation pipelines.\n\n"
            "YOUR MISSION: Deeply audit this job opportunity to determine if it is a TRUE high-fit win, "
            "or a BAD CLIENT / LOW-MARGIN TRAP to immediately skip.\n\n"
            f"{learning_context}\n\n"
            "AUDIT CRITERIA:\n"
            "1. Client Risk & Toxicity Check: Look for red flags (unrealistic deadlines like 'must finish today', "
            "demands for free work/unpaid tests, micromanagement, zero spend unverified ghost clients, abusive tone).\n"
            "2. Scope Feasibility: Can this realistically be packaged into an entry offer (Setup Sprint $299/$599/$1200 or Audit $750)? "
            "Or is it a 6-month enterprise build disguised as a $200 task?\n"
            "3. Positioning Match: Is it in Aryan's wheelhouse (AI agents, LLM integrations, Python/workflow backends)? "
            "Skip if out of scope (mobile Swift/Kotlin, low-level C++, hardware, cold calling, generic SEO).\n\n"
            "Return JSON ONLY with exact keys:\n"
            "- 'fit_score': number (0 to 100)\n"
            "- 'decision': string ('APPLY', 'REVIEW', or 'SKIP')\n"
            "- 'client_risk_level': string ('LOW', 'MEDIUM', 'HIGH', or 'CRITICAL')\n"
            "- 'toxic_client_flags': array of string warnings (empty if clean)\n"
            "- 'scope_archetype': string (e.g. 'MCP Agent Workflow', 'Document RAG Pipeline', 'Webhook Automation', 'Out-of-Scope')\n"
            "- 'fit_reasoning': string (2-sentence executive summary of why Aryan should or shouldn't bid)\n"
            "- 'key_winning_hook': string (the unique technical insight that will make Aryan's proposal stand out)"
        )

        user_prompt = (
            f"Job Title: {title}\n"
            f"Client Telemetry: Country: {client.get('country', 'Unknown')}, Spent: ${client.get('total_spent', 0)}, "
            f"Hire Rate: {client.get('hire_rate_percent', client.get('hire_rate', 'Unknown'))}%, "
            f"Verified Payment: {client.get('payment_verified', False)}, "
            f"Total Hired: {activity.get('totalHired', 0)}\n"
            f"{budget_str}\n\n"
            f"Full Job Description:\n{desc[:3000]}"
        )

        # 1. Primary Engine: Google Studio Gemini (3.5 Flash Lite / 3.5 Flash / 3.8 Flash)
        if google_key:
            gemini_models = ["models/gemini-3.5-flash-lite", "models/gemini-3.5-flash", "models/gemini-3.8-flash"]
            for g_model in gemini_models:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/{g_model}:generateContent?key={google_key}"
                    payload = {
                        "systemInstruction": {"parts": [{"text": system_prompt}]},
                        "contents": [
                            {"role": "user", "parts": [{"text": user_prompt}]}
                        ],
                        "generationConfig": {
                            "responseMimeType": "application/json",
                            "temperature": 0.1,
                        },
                    }
                    req = urllib.request.Request(
                        url,
                        data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        res_json = json.loads(resp.read().decode("utf-8"))
                        text_out = res_json["candidates"][0]["content"]["parts"][0]["text"]
                        parsed = json.loads(text_out)
                        parsed["evaluator"] = f"gemini ({g_model.split('/')[-1]})"
                        logger.info(
                            f"AI Job Vetting completed via Gemini ({g_model}): "
                            f"{parsed.get('decision')} (Score: {parsed.get('fit_score')}, Risk: {parsed.get('client_risk_level')})"
                        )
                        return parsed
                except Exception as e:
                    logger.warning(f"Gemini job vetting attempt with {g_model} failed: {e}")
                    continue

        # 2. Secondary Engine: Groq LLM (120B / 70B)
        if groq_key:
            groq_models = [
                os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
                "llama-3.3-70b-versatile",
                "openai/gpt-oss-20b",
            ]
            for q_model in groq_models:
                try:
                    url = "https://api.groq.com/openai/v1/chat/completions"
                    payload = {
                        "model": q_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0.1,
                        "response_format": {"type": "json_object"},
                    }
                    req = urllib.request.Request(
                        url,
                        data=json.dumps(payload).encode("utf-8"),
                        headers={
                            "Authorization": f"Bearer {groq_key}",
                            "Content-Type": "application/json",
                            "User-Agent": "Mozilla/5.0",
                        },
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=12) as resp:
                        res_json = json.loads(resp.read().decode("utf-8"))
                        text_out = res_json["choices"][0]["message"]["content"]
                        parsed = json.loads(text_out)
                        parsed["evaluator"] = f"groq ({q_model})"
                        logger.info(
                            f"AI Job Vetting completed via Groq ({q_model}): "
                            f"{parsed.get('decision')} (Score: {parsed.get('fit_score')})"
                        )
                        return parsed
                except Exception as e:
                    logger.warning(f"Groq job vetting attempt with {q_model} failed: {e}")
                    continue

        # 3. Tertiary Heuristic Fallback
        return {
            "fit_score": h_score,
            "decision": h_decision,
            "client_risk_level": "LOW" if h_score >= 70 else "MEDIUM",
            "toxic_client_flags": [],
            "scope_archetype": "Heuristic Assessment",
            "fit_reasoning": "Heuristic rubric evaluation (LLM offline).",
            "key_winning_hook": "Focus on reliable production execution with human approval safeguards.",
            "evaluator": "heuristic_fallback",
        }