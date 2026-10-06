"""
Continuous Client Learning & Feedback Engine for Aryan Upwork Acquisition Pipeline.
Learns from Aryan's approval/rejection decisions, automated disqualifications,
and market telemetry to continuously adapt criteria for avoiding bad clients.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import STATE_DIR

logger = logging.getLogger("client_learner")


class ClientLearningEngine:
    """Manages dynamic positive/negative client learnings to protect Aryan from bad clients."""

    def __init__(self, state_dir: Optional[Path] = None):
        self.state_dir = state_dir or STATE_DIR
        self.learnings_file = self.state_dir / "client_learnings.json"

    def load_learnings(self) -> Dict[str, Any]:
        """Load stored learning records."""
        if not self.learnings_file.exists():
            return {
                "version": "1.0.0",
                "last_updated": None,
                "negative_patterns": {
                    "toxic_keywords": [
                        "unpaid test", "free sample", "cheap", "rock bottom",
                        "equity only", "commission only", "full-time employee disguised",
                        "must be on screen 8 hours", "immediate deadline today"
                    ],
                    "rejected_client_hashes": [],
                    "bad_client_reasons": Counter(),
                    "total_rejected": 0,
                },
                "positive_patterns": {
                    "preferred_tech": [
                        "claude", "mcp", "n8n", "rag", "fastapi", "django",
                        "evals", "pgvector", "anthropic", "langgraph"
                    ],
                    "approved_client_hashes": [],
                    "total_approved": 0,
                },
                "history": [],
            }
        try:
            with open(self.learnings_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Ensure structure
                if "bad_client_reasons" in data.get("negative_patterns", {}):
                    if isinstance(data["negative_patterns"]["bad_client_reasons"], dict):
                        data["negative_patterns"]["bad_client_reasons"] = Counter(
                            data["negative_patterns"]["bad_client_reasons"]
                        )
                return data
        except Exception as e:
            logger.warning(f"Error loading client learnings, creating fresh state: {e}")
            return {
                "version": "1.0.0",
                "last_updated": None,
                "negative_patterns": {
                    "toxic_keywords": [],
                    "rejected_client_hashes": [],
                    "bad_client_reasons": Counter(),
                    "total_rejected": 0,
                },
                "positive_patterns": {
                    "preferred_tech": [],
                    "approved_client_hashes": [],
                    "total_approved": 0,
                },
                "history": [],
            }

    def save_learnings(self, data: Dict[str, Any]) -> None:
        """Persist learning records."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        to_save = json.loads(json.dumps(data, default=lambda o: dict(o) if isinstance(o, Counter) else str(o)))
        with open(self.learnings_file, "w", encoding="utf-8") as f:
            json.dump(to_save, f, indent=2, ensure_ascii=False)

    def record_rejection(self, job: Dict[str, Any], reason: str = "Human rejected") -> None:
        """Record a human rejection event to penalize similar client profiles."""
        data = self.load_learnings()
        neg = data.setdefault("negative_patterns", {})
        client = job.get("client_record") if isinstance(job.get("client_record"), dict) else (job.get("client") if isinstance(job.get("client"), dict) else {})
        client_hash = client.get("hash") or client.get("id") or client.get("client_id")

        if client_hash and str(client_hash) not in neg.get("rejected_client_hashes", []):
            neg.setdefault("rejected_client_hashes", []).append(str(client_hash))

        reasons = neg.setdefault("bad_client_reasons", Counter())
        if isinstance(reasons, dict) and not isinstance(reasons, Counter):
            reasons = Counter(reasons)
            neg["bad_client_reasons"] = reasons
        reasons[reason] += 1
        neg["total_rejected"] = neg.get("total_rejected", 0) + 1

        # Extract title keywords to avoid
        title = str(job.get("title", "")).lower()
        if "data entry" in title or "cold call" in title or "wordpress plugin" in title:
            if title not in neg.get("toxic_keywords", []):
                neg.setdefault("toxic_keywords", []).append(title[:40])

        data["history"].append({
            "type": "rejection",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "job_id": job.get("job_id") or job.get("id"),
            "title": job.get("title"),
            "reason": reason,
        })
        self.save_learnings(data)
        logger.info(f"Learned rejection pattern for '{job.get('title')}': {reason}")

    def record_approval(self, job: Dict[str, Any]) -> None:
        """Record a human approval event to reinforce high-value client archetypes."""
        data = self.load_learnings()
        pos = data.setdefault("positive_patterns", {})
        client = job.get("client_record") if isinstance(job.get("client_record"), dict) else (job.get("client") if isinstance(job.get("client"), dict) else {})
        client_hash = client.get("hash") or client.get("id") or client.get("client_id")

        if client_hash and str(client_hash) not in pos.get("approved_client_hashes", []):
            pos.setdefault("approved_client_hashes", []).append(str(client_hash))

        pos["total_approved"] = pos.get("total_approved", 0) + 1
        data["history"].append({
            "type": "approval",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "job_id": job.get("job_id") or job.get("id"),
            "title": job.get("title"),
        })
        self.save_learnings(data)
        logger.info(f"Learned positive client pattern for '{job.get('title')}'")

    def get_learning_context(self) -> str:
        """Compile a concise, high-signal instruction block for AI job vetting."""
        data = self.load_learnings()
        neg = data.get("negative_patterns", {})
        pos = data.get("positive_patterns", {})

        toxic_words = ", ".join(neg.get("toxic_keywords", [])[:8])
        top_reasons = ""
        reasons = neg.get("bad_client_reasons", {})
        if reasons:
            top_reasons = ", ".join(f"{k} ({v}x)" for k, v in Counter(reasons).most_common(3))

        lines = [
            "CONTINUOUS CLIENT LEARNING KNOWLEDGE BASE:",
            f"- Bad Client Warning Signals: {toxic_words or 'Unrealistic fixed budgets, unpaid test asks, scope creep'}.",
        ]
        if top_reasons:
            lines.append(f"- Aryan's Common Rejection Reasons: {top_reasons}.")
        lines.append(
            "- Preferred High-Converting Clients: High-spending tech founders/leads with clear API/tool architectures, reasonable budgets (>= $60/hr or >= $500 fixed), and verified payments."
        )
        return "\n".join(lines)