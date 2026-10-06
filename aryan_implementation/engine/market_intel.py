"""
Market Intelligence and Content Knowledge Base Engine for Aryan Upwork Acquisition Pipeline.
Captures market demand signals, emerging tech stacks, client friction points, and content angles
from high-signal jobs (both open and rapidly-filled jobs).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .config import STATE_DIR, PROJECT_ROOT


TECH_KEYWORDS = {
    # AI & Agent Frameworks
    "Claude": r"\bclaude\b|\banthropic\b",
    "OpenAI": r"\bopenai\b|\bgpt[- ]?4\b|\bchatgpt\b",
    "Cursor": r"\bcursor\b|\bcursor\.sh\b",
    "Lovable": r"\blovable\b|\blovable\.dev\b",
    "v0": r"\bv0\b|\bv0\.dev\b",
    "Bolt.new": r"\bbolt\.new\b|\bbolt\b",
    "MCP": r"\bmcp\b|\bmodel context protocol\b",
    "LangChain": r"\blangchain\b",
    "LlamaIndex": r"\bllamaindex\b",
    "CrewAI": r"\bcrewai\b",
    "AutoGen": r"\bautogen\b",
    # RAG & Databases
    "RAG": r"\brag\b|\bretrieval[- ]augmented\b",
    "Evals": r"\bevals?\b|\bevaluation pipeline\b|\bragas\b",
    "Supabase": r"\bsupabase\b",
    "pgvector": r"\bpgvector\b",
    "Pinecone": r"\bpinecone\b",
    "Qdrant": r"\bqdrant\b",
    "Weaviate": r"\bweaviate\b",
    "PostgreSQL": r"\bpostgres(ql)?\b",
    # Automation & Workflows
    "n8n": r"\bn8n\b",
    "Make.com": r"\bmake(\.com)?\b|\bintegromat\b",
    "Zapier": r"\bzapier\b",
    "HubSpot": r"\bhubspot\b",
    "Slack": r"\bslack\b",
    "Notion": r"\bnotion\b",
    "Airtable": r"\bairtable\b",
    # Core Languages & Frameworks
    "Python": r"\bpython\b|\bfastapi\b|\bflask\b|\bdjango\b",
    "React": r"\breact\b|\bnext\.?js\b",
    "TypeScript": r"\btypescript\b|\bts\b",
}


def extract_tech_stack(text: str) -> List[str]:
    """Identify mentioned tools and frameworks."""
    found: List[str] = []
    text_lower = text.lower()
    for name, pattern in TECH_KEYWORDS.items():
        if re.search(pattern, text_lower):
            found.append(name)
    return found


def categorize_archetype(title: str, desc: str) -> str:
    """Classify the job into Aryan's core market categories."""
    full = f"{title} {desc}".lower()
    if any(k in full for k in ["eval", "rag", "retrieval", "vector", "hallucinat"]):
        return "RAG & Evaluation Pipeline (Prototype -> Production)"
    elif any(k in full for k in ["mcp", "model context protocol", "claude code", "agentic"]):
        return "Agent Architecture & MCP Tooling"
    elif any(k in full for k in ["n8n", "make.com", "zapier", "automation", "sync", "pipeline"]):
        return "Workflow & Business Automation"
    elif any(k in full for k in ["lovable", "cursor", "prototype", "v0", "mvp"]):
        return "AI Prototype Hardening & Production Delivery"
    return "Custom AI Engineering & Integration"


def extract_client_pain_point(desc: str) -> str:
    """Isolate key sentences describing client friction or failure modes."""
    sentences = re.split(r"[.!?\n]+", desc)
    pain_sentences = []
    pain_indicators = [
        "hallucinat", "wrong answer", "doesn't work", "don't have", "need an engineer",
        "issue", "fail", "broken", "unreliable", "slow", "struggling", "problem",
        "take to production", "measure", "clean up", "refactor"
    ]
    for s in sentences:
        s_clean = s.strip()
        if any(ind in s_clean.lower() for ind in pain_indicators) and len(s_clean) > 20:
            pain_sentences.append(s_clean)
            if len(pain_sentences) >= 2:
                break
    if pain_sentences:
        return " — ".join(pain_sentences)
    return desc[:180].strip() + ("..." if len(desc) > 180 else "")


def generate_engagement_tags(tech_stack: List[str], archetype: str) -> List[str]:
    """Generate social/Upwork tags to engage in."""
    tags = set()
    for tech in tech_stack:
        tags.add(f"#{tech.replace('.', '').replace(' ', '')}")
    if "RAG" in archetype or "Evaluation" in archetype:
        tags.update(["#AIEvals", "#RAGArchitecture", "#LLMOps"])
    if "Agent" in archetype or "MCP" in archetype:
        tags.update(["#AIAgents", "#ModelContextProtocol", "#ClaudeAI"])
    if "Prototype" in archetype:
        tags.update(["#AIPrototypes", "#CursorAI", "#LovableDev"])
    return sorted(list(tags))


def generate_content_angles(
    title: str,
    pain_point: str,
    tech_stack: List[str],
    archetype: str,
    hired_fast: bool = False,
) -> Dict[str, Any]:
    """
    Generate actionable LinkedIn/Upwork content hook, post outline,
    and portfolio proof item for Aryan.
    """
    stack_str = ", ".join(tech_stack[:3]) if tech_stack else "AI & LLM"

    if "RAG" in archetype or "Evaluation" in archetype or "Lovable" in tech_stack or "Cursor" in tech_stack:
        hook = f"Why {stack_str} prototypes hallucinate in production (and how to fix them with automated evals)"
        outline = [
            "1. The Prototype Illusion: AI builders (Lovable, Cursor, v0) create stunning demos in hours, but crumble when real customer documents hit edge cases.",
            "2. The #1 Mistake: Trying to fix hallucinations by prompt tweaking before setting up an automated evaluation pipeline measuring answer faithfulness and retrieval recall.",
            "3. Production Grounding: How chunking strategy, hybrid pgvector search, and confidence thresholds transform 'unreliable' bots into enterprise-ready assistants.",
        ]
        proof_item = "Build a 5-min Loom + GitHub demo showcasing a lightweight eval runner benchmarking retrieval precision on messy sample PDFs."
    elif "MCP" in archetype or "Agent" in archetype:
        hook = "Connecting Claude Code to live systems: Why MCP (Model Context Protocol) is replacing custom API wrappers"
        outline = [
            "1. Moving past stateless prompts: Why modern engineering teams need tools that directly inspect databases and workflows.",
            "2. Safe Tool Execution: How to structure approval gates and rate limits inside custom MCP servers.",
            "3. Practical Architecture: An end-to-end walkthrough connecting local workflows to remote services cleanly.",
        ]
        proof_item = "Publish an open-source MCP starter connector with human-in-the-loop confirmation."
    else:
        hook = f"The difference between fragile workflows and resilient automation with {stack_str}"
        outline = [
            "1. Silent webhook failures: What happens when edge cases hit third-party integrations.",
            "2. State & Idempotency: Designing pipelines that recover automatically without duplicating tasks.",
            "3. Client ROI: Why clients are paying premium rates for reliable architecture rather than quick hacks.",
        ]
        proof_item = "Share an architectural diagram showing retry queues, error notifications, and audit logging."

    velocity_note = "High Urgency Signal: Client hired within hours. Market is desperate for engineers with verified proof in this exact topic." if hired_fast else "Standard Demand Signal."

    return {
        "headline_hook": hook,
        "outline": outline,
        "proof_asset_to_build": proof_item,
        "velocity_note": velocity_note,
    }


class MarketIntelEngine:
    """Manages the Upwork Market Intelligence & Content Knowledge Base."""

    def __init__(self, state_dir: Optional[Path] = None):
        self.state_dir = state_dir or STATE_DIR
        self.intel_file = self.state_dir / "market_intelligence.json"
        self.digest_file = self.state_dir / "market_intelligence_digest.md"
        self.workspace_digest = PROJECT_ROOT / "market_intelligence_digest.md"

    def load_intelligence(self) -> Dict[str, Any]:
        """Load stored market intelligence records."""
        if not self.intel_file.exists():
            return {"meta": {"last_updated": None, "total_records": 0}, "records": {}}
        try:
            with open(self.intel_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"meta": {"last_updated": None, "total_records": 0}, "records": {}}

    def save_intelligence(self, data: Dict[str, Any]) -> None:
        """Persist intelligence records."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        data["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        data["meta"]["total_records"] = len(data.get("records", {}))
        with open(self.intel_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def record_job(
        self,
        job: Dict[str, Any],
        status_override: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Extract market signals and catalog the job into the knowledge base.
        Works for both open and filled/closed jobs.
        """
        jid = str(job.get("job_id") or job.get("id", ""))
        if not jid:
            return {}

        title = str(job.get("title", ""))
        desc = str(job.get("description", ""))
        full_text = f"{title}\n{desc}"

        tech_stack = extract_tech_stack(full_text)
        archetype = categorize_archetype(title, desc)
        pain_point = extract_client_pain_point(desc)
        tags = generate_engagement_tags(tech_stack, archetype)

        # Check hiring activity
        activity = job.get("activityStat", {}).get("jobActivity", {}) or job.get("activity", {})
        contract_terms = job.get("contractTerms") or {}
        persons_to_hire = int(job.get("persons_to_hire") or contract_terms.get("personsToHire") or 1)
        total_hired = int(activity.get("totalHired") or job.get("total_hired") or 0)

        is_filled = persons_to_hire > 0 and total_hired >= persons_to_hire
        job_status = status_override or ("FILLED" if is_filled else "OPEN")

        content_angles = generate_content_angles(
            title=title,
            pain_point=pain_point,
            tech_stack=tech_stack,
            archetype=archetype,
            hired_fast=is_filled,
        )

        client = job.get("client_record") or job.get("client", {})

        record = {
            "job_id": jid,
            "url": f"https://www.upwork.com/jobs/~{jid.lstrip('~')}",
            "title": title,
            "archetype": archetype,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "status": job_status,
            "total_hired": total_hired,
            "persons_to_hire": persons_to_hire,
            "budget": {
                "type": job.get("type", "hourly"),
                "hourly_min": job.get("budget_hourly_min") or job.get("hourly_min"),
                "hourly_max": job.get("budget_hourly_max") or job.get("hourly_max"),
                "fixed_amount": job.get("budget_fixed") or job.get("budget", {}).get("amount"),
            },
            "client": {
                "country": client.get("country", "Unknown"),
                "total_spent": client.get("total_spent", 0.0),
                "hire_rate": client.get("hire_rate_percent", client.get("hire_rate", 0)),
                "rating": client.get("rating", 5.0),
            },
            "tech_stack": tech_stack,
            "client_pain_point": pain_point,
            "engagement_tags": tags,
            "content_angles": content_angles,
            "user_notes": notes or "",
        }

        intel = self.load_intelligence()
        intel["records"][jid] = record
        self.save_intelligence(intel)
        self.generate_digest(intel)

        return record

    def generate_digest(self, intel_data: Optional[Dict[str, Any]] = None) -> str:
        """
        Compile all cataloged jobs into a clean, human-readable Markdown intelligence digest.
        """
        if intel_data is None:
            intel_data = self.load_intelligence()

        records = list(intel_data.get("records", {}).values())
        records.sort(key=lambda r: r.get("recorded_at", ""), reverse=True)

        lines: List[str] = [
            "# Upwork Market Intelligence & Demand Knowledge Base",
            f"*Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}*",
            f"*Total Cataloged Opportunities: {len(records)}*",
            "",
            "> **Purpose**: Tracks high-value client pain points, emerging tech stacks, and rapid-hire niches across Upwork. Even when a job is hired before we submit, the demand signal reveals exactly what topics, proof assets, and engagement tags Aryan should leverage.",
            "",
            "---",
            "",
            "## 1. High-Velocity / Rapid-Hire Niches (Hired Fast)",
            "",
        ]

        filled_jobs = [r for r in records if r.get("status") == "FILLED" or r.get("total_hired", 0) > 0]
        if filled_jobs:
            for r in filled_jobs:
                budget_info = ""
                b = r.get("budget", {})
                if b.get("type") == "hourly":
                    budget_info = f"${b.get('hourly_min', 0)}–${b.get('hourly_max', 0)}/hr"
                else:
                    budget_info = f"${b.get('fixed_amount', 0)} fixed"

                c = r.get("client", {})
                lines.append(f"### ⚡ [{r.get('title')}]({r.get('url')})")
                lines.append(f"- **Status**: `FILLED` ({r.get('total_hired')}/{r.get('persons_to_hire')} hired)")
                lines.append(f"- **Client Profile**: {c.get('country')} | ${c.get('total_spent', 0):,.2f} spent | {c.get('hire_rate', 0)}% hire rate | Rate: {budget_info}")
                lines.append(f"- **Archetype**: {r.get('archetype')}")
                lines.append(f"- **Tech Stack**: `{', '.join(r.get('tech_stack', [])) or 'General AI'}`")
                lines.append(f"- **Core Friction / Pain Point**: *\"{r.get('client_pain_point')}\"*")
                lines.append(f"- **Recommended Engagement Tags**: {' '.join(r.get('engagement_tags', []))}")
                
                angles = r.get("content_angles", {})
                lines.append(f"- **Ready-to-Post Hook**: **\"{angles.get('headline_hook')}\"**")
                lines.append(f"- **Proof Demo to Build**: *{angles.get('proof_asset_to_build')}*")
                lines.append("")
        else:
            lines.append("_No rapid-hire records logged yet._\n")

        lines.extend([
            "---",
            "",
            "## 2. Active & Monitored Market Demand Signals",
            "",
        ])

        open_jobs = [r for r in records if r not in filled_jobs]
        if open_jobs:
            for r in open_jobs:
                b = r.get("budget", {})
                budget_info = f"${b.get('hourly_min', 0)}–${b.get('hourly_max', 0)}/hr" if b.get("type") == "hourly" else f"${b.get('fixed_amount', 0)} fixed"
                c = r.get("client", {})
                lines.append(f"### 🎯 [{r.get('title')}]({r.get('url')})")
                lines.append(f"- **Status**: `{r.get('status')}` | Rate: {budget_info} | Client: {c.get('country')}")
                lines.append(f"- **Tech Stack**: `{', '.join(r.get('tech_stack', []))}`")
                lines.append(f"- **Core Friction**: *\"{r.get('client_pain_point')}\"*")
                lines.append(f"- **Tags**: {' '.join(r.get('engagement_tags', []))}")
                angles = r.get("content_angles", {})
                lines.append(f"- **Content Hook**: **\"{angles.get('headline_hook')}\"**")
                lines.append("")
        else:
            lines.append("_All cataloged jobs currently in rapid-hire archive._\n")

        lines.extend([
            "---",
            "",
            "## 3. Tech Stacks & Tooling Frequency Matrix",
            "",
            "| Tool / Framework | Mentions in Captured Jobs | Demand Velocity |",
            "|---|---|---|",
        ])

        tech_counts: Dict[str, int] = {}
        for r in records:
            for t in r.get("tech_stack", []):
                tech_counts[t] = tech_counts.get(t, 0) + 1

        for tech, count in sorted(tech_counts.items(), key=lambda x: x[1], reverse=True):
            signal = "🔥 Critical (Clients hiring in <3h)" if tech in ["Cursor", "Lovable", "RAG", "Evals", "Supabase"] else "High"
            lines.append(f"| **{tech}** | {count} | {signal} |")

        lines.extend([
            "",
            "---",
            "",
            "## 4. Aryan's Content & Positioning Roadmap",
            "",
            "Based on live market queries, here are the exact posts, portfolio updates, and tags to focus on this week:",
            "",
            "1. **LinkedIn / Twitter / Substack Post Hook**:",
            "   > *\"Why your Lovable / Cursor prototype breaks on real customer data (and how to fix document grounding with automated evals).\"*",
            "   - Explain the difference between UI prototypes and production vector retrieval.",
            "   - Show how hybrid search in Supabase + pgvector prevents confident hallucination.",
            "",
            "2. **Upwork Profile Adjustments**:",
            "   - Add specific tags: `#AIEvals`, `#RAG`, `#Supabase`, `#ModelContextProtocol`, `#LovableDev`.",
            "   - Mention in profile overview: *\"I take AI prototypes built in Cursor / Lovable and harden them for production B2B reliability.\"*",
            "",
            "3. **Proof Asset / Portfolio Demo**:",
            "   - Record a 3-minute video: Taking a hallucinating RAG setup, adding an eval runner, and demonstrating 0% hallucination with rejection thresholds.",
            "",
        ])

        digest_content = "\n".join(lines)

        try:
            self.digest_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.digest_file, "w", encoding="utf-8") as f:
                f.write(digest_content)
            with open(self.workspace_digest, "w", encoding="utf-8") as f:
                f.write(digest_content)
        except Exception:
            pass

        # Sync with Notion
        try:
            from .notion_publisher import NotionPublisher
            NotionPublisher().sync_market_intel(digest_content)
        except Exception:
            pass

        return digest_content
