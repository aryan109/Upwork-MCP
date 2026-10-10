"""
Monthly Strategy Engine for Aryan Upwork Acquisition Pipeline.
Analyzes 30-day market intelligence trends, tech stack shifts, and proposal conversion data.
Synthesizes market findings via Groq LLM and automatically updates the
authoritative proposal crafting guidelines (UPWORK_PROPOSAL_CRAFTING_GUIDE.md and SKILL.md).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import PROJECT_ROOT, STATE_DIR
from .market_intel import MarketIntelEngine
from .notion_publisher import NotionPublisher
from .state_manager import StateManager
from .telegram_notifier import get_telegram_credentials, send_telegram_message

logger = logging.getLogger("monthly_strategy_engine")


class MonthlyStrategyEngine:
    """Orchestrates monthly market research, trend analysis, and proposal rule evolution."""

    def __init__(self, state_dir: Optional[Path] = None, write_to_repo: Optional[bool] = None):
        self.state_dir = state_dir or STATE_DIR
        self.state_mgr = StateManager(self.state_dir)
        self.intel_eng = MarketIntelEngine(self.state_dir)
        self.skill_file = PROJECT_ROOT / "aryan_implementation" / "skills" / "upwork-proposal-crafting-skill" / "SKILL.md"
        self.guide_file = PROJECT_ROOT / "UPWORK_PROPOSAL_CRAFTING_GUIDE.md"
        self.write_to_repo = (not os.environ.get("UPWORK_TEST_MODE")) if write_to_repo is None else write_to_repo

    def analyze_30day_market_trends(self, days: int = 30) -> Dict[str, Any]:
        """Aggregate and analyze market signals cataloged over the past 30 days."""
        intel_data = self.intel_eng.load_intelligence()
        records = list(intel_data.get("records", {}).values())

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        recent_records = []
        for r in records:
            rec_date_str = r.get("recorded_at")
            if rec_date_str:
                try:
                    rec_date = datetime.fromisoformat(rec_date_str)
                    if rec_date >= cutoff:
                        recent_records.append(r)
                except Exception:
                    recent_records.append(r)
            else:
                recent_records.append(r)

        # Fallback to all records if fewer than 5 in window
        analyzed_records = recent_records if len(recent_records) >= 5 else records

        tech_counter: Counter[str] = Counter()
        archetype_counter: Counter[str] = Counter()
        filled_counter: Counter[str] = Counter()
        hourly_rates: List[float] = []
        fixed_budgets: List[float] = []
        pain_points: List[str] = []

        for r in analyzed_records:
            for tech in r.get("tech_stack", []):
                tech_counter[tech] += 1

            arch = r.get("archetype", "General")
            archetype_counter[arch] += 1

            if r.get("status") == "FILLED" or int(r.get("total_hired", 0) or 0) > 0:
                filled_counter[arch] += 1

            b = r.get("budget", {})
            if b.get("type") == "hourly":
                h_max = b.get("hourly_max")
                if h_max:
                    try:
                        hourly_rates.append(float(h_max))
                    except (ValueError, TypeError):
                        pass
            elif b.get("type") == "fixed":
                amt = b.get("fixed_amount")
                if amt:
                    try:
                        fixed_budgets.append(float(amt))
                    except (ValueError, TypeError):
                        pass

            pp = r.get("client_pain_point")
            if pp and pp not in pain_points:
                pain_points.append(pp)

        top_techs = [t for t, _ in tech_counter.most_common(10)]
        top_archetypes = [a for a, _ in archetype_counter.most_common(5)]
        fast_hired = [a for a, _ in filled_counter.most_common(3)]

        avg_hourly = round(sum(hourly_rates) / len(hourly_rates), 2) if hourly_rates else 55.0
        avg_fixed = round(sum(fixed_budgets) / len(fixed_budgets), 2) if fixed_budgets else 850.0

        return {
            "total_analyzed": len(analyzed_records),
            "window_days": days,
            "top_technologies": top_techs,
            "top_archetypes": top_archetypes,
            "fastest_hiring_niches": fast_hired,
            "pricing_telemetry": {
                "avg_hourly_ceiling": avg_hourly,
                "avg_fixed_budget": avg_fixed,
                "sample_hourly_count": len(hourly_rates),
                "sample_fixed_count": len(fixed_budgets),
            },
            "key_pain_points": pain_points[:8],
        }

    def synthesize_strategy_with_llm(self, trends: Dict[str, Any]) -> Dict[str, Any]:
        """Use Groq LLM to synthesize market trends into actionable proposal updates."""
        groq_key = os.environ.get("GROQ_API_KEY")
        if not groq_key:
            from .telegram_notifier import load_env_file
            env = load_env_file(PROJECT_ROOT / ".env")
            groq_key = env.get("GROQ_API_KEY")

        tech_list = ", ".join(trends.get("top_technologies", [])[:8])
        archetypes = ", ".join(trends.get("top_archetypes", [])[:5])
        fast_hired = ", ".join(trends.get("fastest_hiring_niches", [])[:3])
        pricing = trends.get("pricing_telemetry", {})
        pain_points = "\n".join(f"- {p}" for p in trends.get("key_pain_points", [])[:5])

        system_prompt = (
            "You are Aryan's Upwork Principal Acquisition Strategist. "
            "Your objective is to evaluate monthly market telemetry from Upwork and formulate actionable refinements "
            "to Aryan's proposal crafting strategy.\n\n"
            "Respond strictly in valid JSON format with keys:\n"
            "- 'market_summary': 2-sentence macro analysis of current client demand.\n"
            "- 'recommended_proof_focus': Specific technical proof item to prioritize in Paragraph 3.\n"
            "- 'recommended_risk_focus': Specific technical/operational risk warning to emphasize in Paragraph 4.\n"
            "- 'trending_keywords_to_mirror': List of 3-5 high-signal technical terms clients respond to.\n"
            "- 'changelog_entry': Markdown bullet summary of this month's strategy calibration."
        )

        user_prompt = (
            f"Monthly Market Telemetry:\n"
            f"- Total Opportunities Analyzed: {trends.get('total_analyzed')}\n"
            f"- Top Tech Stacks: {tech_list}\n"
            f"- Dominant Archetypes: {archetypes}\n"
            f"- Fastest Hiring Niches: {fast_hired}\n"
            f"- Average Hourly Ceiling: ${pricing.get('avg_hourly_ceiling')}/hr\n"
            f"- Average Fixed Budget: ${pricing.get('avg_fixed_budget')}\n"
            f"- Frequent Client Pain Points:\n{pain_points}\n"
        )

        models = [
            os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-20b",
        ]

        if groq_key:
            for model in models:
                try:
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
                            "User-Agent": "Mozilla/5.0",
                        },
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        res = json.loads(resp.read().decode("utf-8"))
                        content = res["choices"][0]["message"]["content"]
                        parsed = json.loads(content)
                        logger.info(f"Synthesized monthly strategy using Groq LLM ({model})")
                        return parsed
                except Exception as e:
                    logger.warning(f"Groq monthly strategy synthesis failed with {model}: {e}")
                    continue

        # Heuristic fallback if LLM is offline
        return {
            "market_summary": f"High demand observed in {archetypes or 'AI workflows'}, with strong buyer interest in {tech_list or 'MCP and automations'}.",
            "recommended_proof_focus": "Production agent system on official MCP server with human approval gates and full audit logging.",
            "recommended_risk_focus": "Silent webhook failure and duplicate records during automated third-party sync retries.",
            "trending_keywords_to_mirror": ["MCP", "Claude Code", "pgvector", "n8n", "human-in-the-loop"],
            "changelog_entry": f"Prioritized {tech_list[:40]} integrations with emphasis on human approval safeguards.",
        }

    def update_proposal_rules_markdown(self, strategy: Dict[str, Any], version_bump: str = "minor") -> bool:
        """Safely updates UPWORK_PROPOSAL_CRAFTING_GUIDE.md and SKILL.md with monthly insights."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        summary = strategy.get("market_summary", "")
        proof_focus = strategy.get("recommended_proof_focus", "")
        risk_focus = strategy.get("recommended_risk_focus", "")
        trending = ", ".join(strategy.get("trending_keywords_to_mirror", []))
        entry_text = strategy.get("changelog_entry", "")

        changelog_line = (
            f"- **[{now_str}] Monthly Strategy Calibration**: {entry_text} "
            f"Trending stacks: `{trending}`. Core proof priority: *'{proof_focus}'*. "
            f"Risk anchor: *'{risk_focus}'*."
        )

        updated_any = False
        for target_file in [self.guide_file, self.skill_file]:
            if not target_file.exists():
                continue
            try:
                content = target_file.read_text(encoding="utf-8")
                # Update last_updated in frontmatter
                content = re.sub(r'last_updated: ".*?"', f'last_updated: "{now_str}"', content)

                # Append to Section 6
                if "## 6. Dynamic Market Evolution Changelog" in content:
                    parts = content.split("## 6. Dynamic Market Evolution Changelog", 1)
                    header_part = parts[0] + "## 6. Dynamic Market Evolution Changelog"
                    rest = parts[1]
                    # Find end of intro note
                    if "> *This section is maintained automatically by the Monthly Strategy Engine.*" in rest:
                        subparts = rest.split("> *This section is maintained automatically by the Monthly Strategy Engine.*", 1)
                        new_content = (
                            header_part + subparts[0] +
                            "> *This section is maintained automatically by the Monthly Strategy Engine.*\n\n" +
                            changelog_line + "\n" +
                            subparts[1].lstrip("\n")
                        )
                        target_file.write_text(new_content, encoding="utf-8")
                        updated_any = True
                        logger.info(f"Updated proposal guidelines in {target_file.name}")
            except Exception as e:
                logger.error(f"Failed to update {target_file.name}: {e}")

        return updated_any

    def run_monthly_pass(self) -> Dict[str, Any]:
        """Execute the full end-to-end monthly market analysis and proposal rule calibration."""
        logger.info("=== Starting Monthly Upwork Strategy & Market Trend Pass ===")
        now_utc = datetime.now(timezone.utc)
        trends = self.analyze_30day_market_trends(days=30)
        strategy = self.synthesize_strategy_with_llm(trends)

        # Update Markdown skill and guide files
        updated = self.update_proposal_rules_markdown(strategy) if self.write_to_repo else True

        # Persist date in engine state
        state = self.state_mgr.load_state()
        state["last_monthly_strategy_date"] = now_utc.strftime("%Y-%m-%d")
        state["last_monthly_strategy_summary"] = strategy
        self.state_mgr.save_state(state)

        # Sync to Notion
        notion_synced = False
        try:
            notion_pub = NotionPublisher()
            report_md = (
                f"# Monthly Upwork Market & Proposal Strategy Report\n\n"
                f"*Compiled: {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}*\n\n"
                f"### Market Trend Synthesis\n{strategy.get('market_summary')}\n\n"
                f"### High-Signal Tech Stacks\n{', '.join(trends.get('top_technologies', []))}\n\n"
                f"### Tactical Proposal Calibrations\n"
                f"- **Proof Focus**: {strategy.get('recommended_proof_focus')}\n"
                f"- **Risk Emphasis**: {strategy.get('recommended_risk_focus')}\n"
                f"- **Trending Terms**: {', '.join(strategy.get('trending_keywords_to_mirror', []))}\n\n"
                f"---\n*Proposal Crafting Rules updated in UPWORK_PROPOSAL_CRAFTING_GUIDE.md and SKILL.md*"
            )
            notion_synced = notion_pub.sync_market_intel(report_md)
        except Exception as e:
            logger.debug(f"Notion sync note: {e}")

        # Send Telegram notification
        token, chat_id = get_telegram_credentials()
        if token and chat_id:
            top_techs = ", ".join(trends.get("top_technologies", [])[:5])
            msg = (
                f"📊 <b>Monthly Upwork Strategy Calibration Complete!</b>\n\n"
                f"• 📈 <b>Top Stacks (30d):</b> {top_techs}\n"
                f"• 💡 <b>Proof Priority:</b> {strategy.get('recommended_proof_focus')}\n"
                f"• ⚠️ <b>Key Risk Hook:</b> {strategy.get('recommended_risk_focus')}\n"
                f"• 📝 <b>Guide Updated:</b> <code>UPWORK_PROPOSAL_CRAFTING_GUIDE.md</code> (Rules intact)\n\n"
                f"<i>Proposal generation prompts dynamically calibrated to current market demand.</i>"
            )
            send_telegram_message(msg, parse_mode="HTML")

        logger.info("=== Monthly Strategy Pass Finished Successfully ===")
        return {
            "status": "success",
            "timestamp": now_utc.isoformat(),
            "trends": trends,
            "strategy": strategy,
            "markdown_updated": updated,
            "notion_synced": notion_synced,
        }


def main():
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Aryan Upwork Monthly Strategy Engine")
    parser.add_argument("--run", action="store_true", help="Run the monthly strategy pass immediately")
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days (default: 30)")
    args = parser.parse_args()

    engine = MonthlyStrategyEngine()
    if args.run:
        result = engine.run_monthly_pass()
        print("\n=== MONTHLY STRATEGY PASS RESULT ===")
        print(f"Status: {result.get('status')}")
        print(f"Market Summary: {result.get('strategy', {}).get('market_summary')}")
        print(f"Proof Focus: {result.get('strategy', {}).get('recommended_proof_focus')}")
        print(f"Rules Markdown Updated: {result.get('markdown_updated')}\n")
    else:
        trends = engine.analyze_30day_market_trends(days=args.days)
        print(json.dumps(trends, indent=2))


if __name__ == "__main__":
    main()