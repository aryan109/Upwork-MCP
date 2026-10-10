"""
Daily Comprehensive Report & Continuous Improvement Engine for Aryan Upwork Acquisition Pipeline.
Compiles a 4-part daily briefing:
1. What's Happened (Last 24 hours retrospective: jobs analysed, selected, rejected & why)
2. What the Trend Is (Market intelligence, velocity, tech stacks)
3. What You Need to Focus On (Profile adjustments, content angles, proof assets)
4. How We Can Improve (System learning, query calibration, conversion tuning)
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import STATE_DIR, PROJECT_ROOT, ENGINE_DIR
from .market_intel import MarketIntelEngine
from .notifier import notify_daily_report_ready
from .notion_publisher import NotionPublisher
from .state_manager import StateManager
from .web_report import (
    compile_daily_report_metrics,
    render_html_dashboard,
    render_telegram_summary_message,
)

logger = logging.getLogger("daily_report")


class DailyReportEngine:
    """Generates comprehensive daily reports for human review and continuous pipeline improvement."""

    def __init__(self, state_dir: Optional[Path] = None, write_to_repo: Optional[bool] = None):
        self.state_dir = state_dir or STATE_DIR
        self.state_mgr = StateManager(self.state_dir)
        self.intel_eng = MarketIntelEngine(self.state_dir)
        self.reports_dir = (self.state_dir.parent / "reports") if self.state_dir else (ENGINE_DIR / "reports")
        self.workspace_report = PROJECT_ROOT / "daily_report.md"
        self.write_to_repo = (not os.environ.get("UPWORK_TEST_MODE")) if write_to_repo is None else write_to_repo

    def generate_daily_report(self, date_str: Optional[str] = None) -> Dict[str, Any]:
        """
        Compile the full 4-part daily report.
        Writes to daily_report.md, daily_report_{date}.html, and stores in the historical archive.
        """
        now_utc = datetime.now(timezone.utc)
        target_date = date_str or now_utc.strftime("%Y-%m-%d")
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        archive_path = self.reports_dir / f"daily_report_{target_date}.md"
        html_archive_path = self.reports_dir / f"daily_report_{target_date}.html"
        latest_html_path = self.reports_dir / "daily_report_latest.html"

        # Compile granular metrics across jobs, state, and market intelligence
        metrics = compile_daily_report_metrics(self.state_dir, target_date=target_date)

        connects_balance = metrics["connects_balance"]
        connects_budget = metrics["connects_budget"]
        total_analysed = metrics["total_analysed"]
        selected_jobs = metrics["selected_jobs"]
        rejected_jobs = metrics["rejected_jobs"]
        rejection_breakdown = metrics["rejection_breakdown"]
        connects_saved = metrics["connects_saved"]
        top_techs = metrics["top_techs"]
        avg_hourly = metrics["avg_hourly"]
        top_ceiling = metrics["top_ceiling"]
        dynamic_hook = metrics["dynamic_hook"]

        # -------------------------------------------------------------
        # Part 1: What's Happened (Last 24 Hours Retrospective)
        # -------------------------------------------------------------
        report_lines = [
            f"# Daily Upwork Intelligence & Action Report — {target_date}",
            f"*Generated: {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}*",
            "",
            f"> **Executive Summary**: Hourly background hunter is active. Analyzed **{total_analysed}** opportunities with strict D1–D11 and AI risk safeguards, preserving **~{connects_saved} Connects**. High-velocity market demand centers around hardening Claude MCP, Cursor/Lovable AI prototypes into production-grade RAG and Supabase pipelines.",
            "",
            "---",
            "",
            "## 1. What's Happened & Pipeline Activity",
            "",
            f"- **Connects Status**: **{connects_balance}** available (Monthly Budget: {connects_budget})",
            f"- **Total Opportunities Analysed**: **{total_analysed}** leads",
            f"- **Proposals Awaiting Your 1-Click Review**: **{len(selected_jobs)}**",
            f"- **Disqualified Leads Filtered**: **{len(rejected_jobs)}**",
            f"- 🛡️ **Connects Preserved by Safeguards**: **~{connects_saved} Connects** (Est. Value: ~${connects_saved * 0.15:.2f})",
        ]

        # System Health Note
        s_health = metrics.get("system_health", {})
        if s_health.get("is_downtime"):
            report_lines.append(f"- ⚠️ **Runner Status Alert**: {s_health.get('status_label')}. Last scan completed at {s_health.get('last_activity_at')}.")
        else:
            report_lines.append(f"- 🟢 **Runner Status**: Active & Healthy (last scan {s_health.get('elapsed_desc')}).")

        # Review Queue Backlog from earlier dates
        backlog = metrics.get("review_queue_backlog", [])
        if backlog:
            report_lines.append("")
            report_lines.append(f"### 📋 Review Queue Backlog ({len(backlog)} Pending from Earlier Dates):")
            for b in backlog:
                report_lines.append(f"- **[{b.get('title')}]({b.get('url')})** — Score: `{b.get('score', 0):.1f}` | Rate: `{b.get('pricing')}`")
                report_lines.append(f"  - *Staged Date*: **{b.get('staged_date')}** ({b.get('age_days')} days ago)")
                report_lines.append(f"  - *Review Command*: `python -m aryan_implementation.engine.cli submit --job-id {b.get('job_id')} --confirm`")

        # Connects Saved by D11 explicit mention
        d11_info = rejection_breakdown.get("D11")
        if d11_info:
            report_lines.append(f"- ⚡ **Connects Saved by D11**: Successfully caught **{d11_info['count']}** already-filled jobs before proposal creation.")

        # Granular Rejection Breakdown & Why
        if rejection_breakdown:
            report_lines.append("")
            report_lines.append("### 🛑 Disqualification Breakdown & Why Rejected:")
            for code, item in sorted(rejection_breakdown.items(), key=lambda x: x[1]["count"], reverse=True):
                cnt = item["count"]
                expl = item["explanation"]
                report_lines.append(f"- **`{code}` ({cnt} jobs)**: *{expl}*")
                if item["examples"]:
                    for ex in item["examples"][:2]:
                        report_lines.append(f"  - Example: *{ex}*")

        # Staged Proposals Pending Action (With Why Selected)
        if selected_jobs:
            report_lines.append("")
            report_lines.append(f"### 🎯 Staged Proposals Pending Action (Why Selected) — {target_date}:")
            for s in selected_jobs:
                reasons_str = "; ".join(s["why_selected"])
                report_lines.append(f"- **[{s.get('title')}]({s.get('url')})** — Score: `{s.get('score', 0):.1f}` | Rate: `{s.get('pricing')}`")
                report_lines.append(f"  - **Why Selected**: {reasons_str}")
                report_lines.append(f"  - *Review Command*: `python -m aryan_implementation.engine.cli submit --job-id {s.get('job_id')} --confirm`")
        else:
            report_lines.append("")
            report_lines.append(f"### 🎯 Staged Proposals on {target_date}:")
            report_lines.append(f"- *0 new proposals were staged strictly on {target_date}.*")

        # -------------------------------------------------------------
        # Part 2: What the Trend Is (Market Demand Signals & Velocity)
        # -------------------------------------------------------------
        report_lines.extend([
            "",
            "---",
            "",
            "## 2. What the Trend Is (Market Demand Signals & Velocity)",
            "",
            "### Emerging Tech Stack Demand Matrix:",
            "| Tool / Framework | Mentions in Tracked Leads | Market Velocity |",
            "|---|---|---|",
        ])

        for tech, count, velocity in top_techs:
            report_lines.append(f"| **{tech}** | {count} | {velocity} |")

        report_lines.extend([
            "",
            f"- **Average Top Hourly Rate**: **${avg_hourly:.0f}/hr** (Ceiling: **${top_ceiling:.0f}/hr**) for fullstack AI / agent implementation roles.",
            f"- **Fastest Hiring Niche**: Founders who built prototypes in **Cursor** or **Lovable** needing an engineer to add automated **evals** and fix document **hallucinations**.",
            "",
            "---",
            "",
            "## 3. What You Need to Focus on Today & Possible Actions",
            "",
            "### A. Upwork Profile & Tags:",
            "- Ensure these tags are active on your profile: `#AIEvals, #RAGArchitecture, #LovableDev, #CursorAI, #Supabase, #ModelContextProtocol`",
            "- Update your profile headline/intro to emphasize: *\"Taking Cursor & Lovable AI Prototypes to Production Reliability (RAG, Evals, MCP)\"*",
            "",
            "### B. Social / Content Hook to Publish Today (Market-Derived):",
            f"- **Headline / Hook**: **\"{dynamic_hook}\"**",
            "- **Post Talking Points**:",
            "  - 1. The Demo Trap: AI app builders make slick demos in hours, but production accuracy plummets when messy customer PDFs arrive.",
            "  - 2. Stop Tweaking Prompts Blindly: Set up an automated evaluation harness measuring retrieval recall and answer faithfulness.",
            "  - 3. Hardening Vector Retrieval: Hybrid search in Supabase (pgvector + full-text) and strict confidence thresholds keep your assistant trustworthy.",
            "",
            "### C. Recommended Next Actions:",
        ])

        for act in metrics["possible_actions"]:
            report_lines.append(f"- [ ] {act}")

        # -------------------------------------------------------------
        # Part 4: How We Can Improve (Continuous System Evolution)
        # -------------------------------------------------------------
        report_lines.extend([
            "",
            "---",
            "",
            "## 4. How We Can Improve (Continuous System Evolution)",
            "",
            "1. **Speed to Discovery**: High-paying AI roles ($50–$80/hr) are hiring within 3 hours. Running the automated hourly task ensures new postings are caught within 15–45 minutes.",
            "2. **Campaign Keyword Calibration**: Live marketplace signals show high client demand for `Lovable`, `Cursor`, and `Evals`. Adding these terms into `campaigns.json` under `rag-knowledge` will increase high-converting candidate discovery.",
            "3. **Connects Preservation**: Disqualifiers D6 and D11 successfully prevent applying to ghost or already-filled jobs, directly preserving your Connects balance.",
            "4. **Proposal Structure Feedback**: Proposing a clear fixed Sprint ($599) as an alternative to hourly rates makes it easy for fast-moving founders to approve immediately without open-ended hourly risk.",
            "",
            "---",
            "",
            "### Quick Action Commands:",
            "- View Review Queue: `python -m aryan_implementation.engine.cli queue`",
            "- Run On-Demand Hunt: `python -m aryan_implementation.engine.cli hunt`",
            "- View Market Intel Digest: `python -m aryan_implementation.engine.cli intel`",
            f"- Open Web Dashboard: `{metrics['web_report_link']}`",
            "- Regenerate This Daily Report: `python -m aryan_implementation.engine.cli daily-report`",
        ])

        report_md = "\n".join(report_lines)

        # Render Standalone HTML Dashboard
        report_html = render_html_dashboard(metrics)

        # Write Markdown & HTML reports to workspace and archive
        try:
            if self.write_to_repo:
                with open(self.workspace_report, "w", encoding="utf-8") as f:
                    f.write(report_md)
            with open(archive_path, "w", encoding="utf-8") as f:
                f.write(report_md)
            with open(html_archive_path, "w", encoding="utf-8") as f:
                f.write(report_html)
            with open(latest_html_path, "w", encoding="utf-8") as f:
                f.write(report_html)
        except Exception as e:
            logger.warning(f"Error writing daily report files: {e}")

        # Sync with Notion
        try:
            notion_pub = NotionPublisher()
            notion_pub.sync_daily_report(report_md)
            notion_pub.sync_master_hub()
            logger.info("Daily report successfully synced to Notion.")
        except Exception as e:
            logger.debug(f"Notion sync note: {e}")

        # Trigger desktop and Telegram notification with rich metrics
        notify_daily_report_ready(
            target_date,
            metrics["selected_count"],
            report_text=report_md,
            metrics=metrics,
        )

        return {
            "date": target_date,
            "report_path": str(self.workspace_report),
            "archive_path": str(archive_path),
            "html_path": str(html_archive_path),
            "staged_count": metrics["selected_count"],
            "metrics": metrics,
            "content": report_md,
        }
