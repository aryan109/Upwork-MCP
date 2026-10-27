"""
Notion Integration & Publishing Engine for Aryan Upwork Acquisition Pipeline.
Automatically syncs:
1. Daily 4-part intelligence & improvement reports to Notion
2. Market Intelligence & Demand signals to Notion
3. Master Command Center hub page on Notion
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import PROJECT_ROOT
from .draft import sanitize_no_em_dash

logger = logging.getLogger("notion_publisher")

# Notion Page IDs created for Aryan's workspace
NOTION_MASTER_PAGE_ID = "3f197b4f-8610-816e-8ab0-cf54ac7b3a3e"
NOTION_DAILY_REPORTS_PAGE_ID = "3f197b4f-8610-81a1-ac3e-d59e9c8bf7d7"
NOTION_MARKET_INTEL_PAGE_ID = "3f197b4f-8610-81a7-b919-f430b7816837"
NOTION_STAGING_DESK_PAGE_ID = "40697b4f-8610-81d2-a7d6-d2b5ee0851b8"

NOTION_API_VERSION = "2022-06-28"


def get_notion_token() -> Optional[str]:
    """
    Resolve Notion integration token from:
    1. NOTION_API_KEY / NOTION_TOKEN environment variable
    2. PROJECT_ROOT/.env
    3. C:\\Users\\Aryan\\.gemini\\config\\mcp_config.json
    """
    token = os.environ.get("NOTION_API_KEY") or os.environ.get("NOTION_TOKEN")
    if token:
        return token.strip()

    # Check .env
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("NOTION_API_KEY=") or line.startswith("NOTION_TOKEN="):
                        val = line.split("=", 1)[1].strip().strip("'\"")
                        if val:
                            return val
        except Exception:
            pass

    # Check gemini mcp_config.json
    gemini_cfg = Path(os.environ.get("USERPROFILE", os.path.expanduser("~"))) / ".gemini" / "config" / "mcp_config.json"
    if gemini_cfg.exists():
        try:
            with open(gemini_cfg, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                notion_srv = cfg.get("mcpServers", {}).get("notion-mcp-server", {})
                openapi_headers = notion_srv.get("env", {}).get("OPENAPI_MCP_HEADERS", "")
                if openapi_headers:
                    h_json = json.loads(openapi_headers)
                    auth = h_json.get("Authorization", "")
                    if auth.startswith("Bearer "):
                        return auth[7:].strip()
        except Exception:
            pass

    return None


class NotionPublisher:
    """Manages document publishing and updates in Notion via Notion REST API."""

    def __init__(self, token: Optional[str] = None):
        self.token = token or get_notion_token()

    def update_page_markdown(self, page_id: str, markdown: str) -> bool:
        """
        Replace page content with enhanced Markdown via Notion REST API.
        Endpoint: PATCH /v1/pages/{page_id}/markdown
        """
        if not self.token:
            logger.warning("Notion sync skipped: Notion token could not be resolved.")
            return False

        clean_page_id = page_id.replace("-", "")
        url = f"https://api.notion.com/v1/pages/{clean_page_id}/markdown"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": NOTION_API_VERSION,
            "Content-Type": "application/json",
        }
        body = {
            "type": "replace_content",
            "replace_content": {
                "new_str": markdown,
                "allow_deleting_content": False,
            },
        }

        try:
            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method="PATCH")
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 200:
                    logger.info(f"Notion page {page_id} successfully updated with markdown.")
                    return True
                else:
                    logger.warning(f"Notion API returned HTTP {resp.status} for page {page_id}")
                    return False
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")
            logger.error(f"Notion API HTTP error {e.code} updating page {page_id}: {err}")
            return False
        except Exception as e:
            logger.error(f"Failed to update Notion page {page_id}: {e}")
            return False

    def sync_daily_report(self, report_md: str) -> bool:
        """Syncs the daily report markdown to Notion."""
        return self.update_page_markdown(NOTION_DAILY_REPORTS_PAGE_ID, report_md)

    def sync_market_intel(self, intel_md: str) -> bool:
        """Syncs the market intelligence knowledge base markdown to Notion."""
        return self.update_page_markdown(NOTION_MARKET_INTEL_PAGE_ID, intel_md)

    def sync_daily_market_demand_report(self, date_str: str, report_md: str) -> Dict[str, Any]:
        """
        Syncs the Daily Market Demand & Trends Report to Notion:
        1. Updates the live 'Market Intelligence & Demand Knowledge Base' page.
        2. Creates or updates a dated child page: '📊 Market Demand & Trends — {date_str}'
           under NOTION_DAILY_REPORTS_PAGE_ID so daily history is preserved in Notion.
        3. Updates the Master Command Center hub page.
        """
        res = {"main_intel": False, "daily_page": False, "daily_page_id": None, "master_hub": False}
        if not self.token:
            logger.warning("Notion sync skipped: Notion token could not be resolved.")
            return res

        # 1. Update live Market Intelligence page
        res["main_intel"] = self.sync_market_intel(report_md)

        # 2. Add or update daily dated subpage in Notion
        try:
            state_file = PROJECT_ROOT / "aryan_implementation" / "engine" / "notion_daily_pages.json"
            daily_pages = {}
            if state_file.exists():
                try:
                    with open(state_file, "r", encoding="utf-8") as sf:
                        daily_pages = json.load(sf)
                except Exception:
                    daily_pages = {}

            target_pid = daily_pages.get(date_str)
            page_title = f"📊 Market Demand & Trends — {date_str}"

            if target_pid:
                ok = self.update_page_markdown(target_pid, report_md)
                if ok:
                    res["daily_page"] = True
                    res["daily_page_id"] = target_pid
                    logger.info(f"Updated existing Notion daily demand page {target_pid} for {date_str}")
                else:
                    target_pid = None

            if not target_pid:
                clean_parent = NOTION_DAILY_REPORTS_PAGE_ID.replace("-", "")
                url = "https://api.notion.com/v1/pages"
                headers = {
                    "Authorization": f"Bearer {self.token}",
                    "Notion-Version": NOTION_API_VERSION,
                    "Content-Type": "application/json",
                }
                body = {
                    "parent": {"page_id": clean_parent},
                    "properties": {
                        "title": [{"text": {"content": page_title}}]
                    }
                }
                data = json.dumps(body).encode("utf-8")
                req = urllib.request.Request(url, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status in (200, 201):
                        created = json.loads(resp.read().decode("utf-8"))
                        new_pid = created.get("id")
                        if new_pid:
                            self.update_page_markdown(new_pid, report_md)
                            daily_pages[date_str] = new_pid
                            try:
                                with open(state_file, "w", encoding="utf-8") as sf:
                                    json.dump(daily_pages, sf, indent=2)
                            except Exception:
                                pass
                            res["daily_page"] = True
                            res["daily_page_id"] = new_pid
                            logger.info(f"Created new Notion daily demand page {new_pid} for {date_str}")
        except Exception as e:
            logger.error(f"Error creating/updating Notion daily demand page: {e}")

        # 3. Update master hub
        res["master_hub"] = self.sync_master_hub()
        return res

    def sync_master_hub(self) -> bool:
        """Syncs the top-level command center hub on Notion."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M IST")
        hub_md = (
            "# Upwork Autonomous Acquisition & Market Intelligence OS\n\n"
            "Welcome to the live Notion command center for Aryan's Upwork acquisition and positioning engine.\n\n"
            "### Hub Sections\n"
            "<page url=\"https://app.notion.com/p/Proposal-Staging-Review-Desk-40697b4f861081d2a7d6d2b5ee0851b8\"/>\n\n"
            "<page url=\"https://app.notion.com/p/Daily-Intelligence-Action-Reports-3f197b4f861081a1ac3ed59e9c8bf7d7\"/>\n\n"
            "<page url=\"https://app.notion.com/p/Market-Intelligence-Demand-Knowledge-Base-3f197b4f861081a7b919f430b7816837\"/>\n\n"
            "---\n"
            f"*Last Synced: {now_str} via Autonomous Acquisition Runner*\n"
        )
        return self.update_page_markdown(NOTION_MASTER_PAGE_ID, hub_md)

    def sync_all(self, workspace_root: Optional[Path] = None) -> Dict[str, bool]:
        """Reads local daily report and market intel files and pushes all to Notion."""
        root = workspace_root or PROJECT_ROOT
        res = {"daily_report": False, "market_intel": False, "master_hub": False}

        daily_path = root / "daily_report.md"
        if daily_path.exists():
            try:
                report_md = daily_path.read_text(encoding="utf-8")
                res["daily_report"] = self.sync_daily_report(report_md)
            except Exception as e:
                logger.error(f"Error reading {daily_path}: {e}")

        intel_path = root / "market_intelligence_digest.md"
        if intel_path.exists():
            try:
                intel_md = intel_path.read_text(encoding="utf-8")
                res["market_intel"] = self.sync_market_intel(intel_md)
            except Exception as e:
                logger.error(f"Error reading {intel_path}: {e}")

        res["master_hub"] = self.sync_master_hub()
        return res

    def get_page_markdown(self, page_id: str) -> Optional[str]:
        """
        Fetch markdown content of a Notion page.
        Endpoint: GET /v1/pages/{page_id}/markdown
        """
        if not self.token:
            logger.warning("Notion get_page_markdown skipped: Notion token could not be resolved.")
            return None

        clean_page_id = page_id.replace("-", "")
        url = f"https://api.notion.com/v1/pages/{clean_page_id}/markdown"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": NOTION_API_VERSION,
        }
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    return data.get("markdown", "")
                else:
                    logger.warning(f"Notion API GET returned HTTP {resp.status} for page {page_id}")
                    return None
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")
            logger.error(f"Notion API HTTP error {e.code} fetching markdown for page {page_id}: {err}")
            return None
        except Exception as e:
            logger.error(f"Failed to fetch markdown for Notion page {page_id}: {e}")
            return None

    def get_or_create_staging_desk_page(self) -> Tuple[bool, Optional[str]]:
        """
        Returns the parent staging desk page ID, creating it under the master page if necessary.
        """
        return True, NOTION_STAGING_DESK_PAGE_ID

    def publish_staged_proposal(
        self,
        job: Dict[str, Any],
        score_res: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Publishes a proposal draft to a dedicated Notion review page under the Staging Desk.
        Returns: (success, page_id, page_url)
        """
        if not self.token:
            logger.warning("publish_staged_proposal skipped: missing Notion token.")
            return False, None, None

        draft = job.get("draft") or {}
        cover_letter = sanitize_no_em_dash(draft.get("cover_letter") or "")
        answers = draft.get("answers") or []
        terms = draft.get("terms") or draft.get("proposed_terms") or {}
        jid = str(job.get("job_id") or "").lstrip("~")
        title = sanitize_no_em_dash(job.get("title") or "Untitled Job")
        job_url = job.get("url") or job.get("job_url") or f"https://www.upwork.com/jobs/~{jid}"

        score = float((score_res.get("score") if score_res else job.get("score")) or 0.0)
        reasons_list = (score_res.get("reasons") if score_res else job.get("reasons")) or []
        reasons = ", ".join(reasons_list[:4]) if reasons_list else "Strong semantic match"

        b_type = str(terms.get("type", job.get("type", "hourly"))).capitalize()
        b_rate = terms.get("charged_amount") or terms.get("charge_rate") or terms.get("hourly_bid") or 65.0
        boost = int(terms.get("boost_connects", 0) or 0)

        # Build Markdown content
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M IST")

        # Format answers
        if answers:
            ans_blocks = []
            for a in answers:
                q_text = sanitize_no_em_dash(a.get("question", "")).strip()
                a_text = sanitize_no_em_dash(a.get("answer", "")).strip()
                ans_blocks.append(f"### Q: {q_text}\n\n**Answer:**\n{a_text}")
            formatted_answers = "\n\n".join(ans_blocks)
        else:
            formatted_answers = "*No screening questions required for this job.*"

        page_md = (
            f"# 📝 Proposal Review: {title}\n\n"
            f"> 💡 **Proposal Staging Desk**:\n"
            f"> Edit the **Cover Letter** and **Screening Answers** below directly in Notion.\n"
            f"> When you are ready, tap **✅ Approve & Submit** on Telegram to submit this exact version to Upwork!\n\n"
            f"---\n\n"
            f"### Job Overview\n"
            f"- **Upwork Link**: [{job_url}]({job_url})\n"
            f"- **Job ID**: `~{jid}`\n"
            f"- **Fit Score**: `{score:.1f} / 100` (APPLY)\n"
            f"- **Matched Signals**: {reasons}\n"
            f"- **Proposed Terms**: {b_type} **${b_rate}** | **Boost Connects**: {boost}\n"
            f"- **Staged At**: {now_str}\n\n"
            f"---\n\n"
            f"## Cover Letter\n\n"
            f"{cover_letter}\n\n"
            f"---\n\n"
            f"## Screening Answers\n\n"
            f"{formatted_answers}\n"
        )

        target_pid = draft.get("notion_page_id")

        if not target_pid:
            # Create a new child page under NOTION_STAGING_DESK_PAGE_ID
            clean_parent = NOTION_STAGING_DESK_PAGE_ID.replace("-", "")
            page_title = f"📝 [Review] {title[:80]} (~{jid})"
            url = "https://api.notion.com/v1/pages"
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": NOTION_API_VERSION,
                "Content-Type": "application/json",
            }
            body = {
                "parent": {"page_id": clean_parent},
                "properties": {
                    "title": [{"text": {"content": page_title}}]
                }
            }
            try:
                data = json.dumps(body).encode("utf-8")
                req = urllib.request.Request(url, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status in (200, 201):
                        created = json.loads(resp.read().decode("utf-8"))
                        target_pid = created.get("id")
                    else:
                        logger.warning(f"Failed to create Notion proposal page: HTTP {resp.status}")
                        return False, None, None
            except Exception as e:
                logger.error(f"Exception creating Notion proposal page: {e}")
                return False, None, None

        if target_pid:
            ok = self.update_page_markdown(target_pid, page_md)
            if ok:
                clean_pid = target_pid.replace("-", "")
                page_url = f"https://app.notion.com/p/{clean_pid}"
                # Cache in draft
                draft["notion_page_id"] = target_pid
                draft["notion_url"] = page_url
                return True, target_pid, page_url

        return False, None, None

    def fetch_staged_proposal(self, page_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetches the latest edited markdown from Notion and extracts
        the updated cover letter and screening answers.
        """
        md = self.get_page_markdown(page_id)
        if not md:
            return None
        parsed = parse_staged_markdown(md)
        parsed["raw_markdown"] = md
        return parsed

    def update_proposal_status(self, page_id: str, new_status: str, title: str) -> bool:
        """
        Updates the Notion page title to reflect the new status:
        - 'submitted': '✅ [Submitted] {title}'
        - 'rejected' / 'skipped': '❌ [Skipped] {title}'
        """
        if not self.token or not page_id:
            return False

        clean_pid = page_id.replace("-", "")
        clean_title = sanitize_no_em_dash(title or "Job")
        if new_status == "submitted":
            new_title = f"✅ [Submitted] {clean_title[:80]}"
        elif new_status in ("rejected", "skipped"):
            new_title = f"❌ [Skipped] {clean_title[:80]}"
        else:
            new_title = f"📝 [{new_status.capitalize()}] {clean_title[:80]}"

        url = f"https://api.notion.com/v1/pages/{clean_pid}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": NOTION_API_VERSION,
            "Content-Type": "application/json",
        }
        body = {
            "properties": {
                "title": [{"text": {"content": new_title}}]
            }
        }
        try:
            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method="PATCH")
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Failed to update Notion proposal status for {page_id}: {e}")
            return False


def parse_staged_markdown(markdown: str) -> Dict[str, Any]:
    """
    Parses staged proposal markdown exported from Notion.
    Extracts:
    - 'cover_letter': Text under '## Cover Letter' up to next section or end of text.
    - 'answers': List of {'question': q, 'answer': a} from '## Screening Answers'.
    Enforces zero em-dashes across all extracted text.
    """
    res: Dict[str, Any] = {
        "cover_letter": "",
        "answers": [],
    }
    if not markdown:
        return res

    text = markdown.replace("\r\n", "\n")

    # 1. Extract Cover Letter
    cl_match = re.search(r"##\s*Cover Letter\s*\n", text, re.IGNORECASE)
    if cl_match:
        start_idx = cl_match.end()
        next_section = re.search(r"\n(?=##\s+|---\s*\n)", text[start_idx:])
        if next_section:
            cl_raw = text[start_idx : start_idx + next_section.start()]
        else:
            cl_raw = text[start_idx:]
        res["cover_letter"] = sanitize_no_em_dash(cl_raw.strip())

    # 2. Extract Screening Answers
    sa_match = re.search(r"##\s*Screening Answers\s*\n", text, re.IGNORECASE)
    if sa_match:
        sa_start = sa_match.end()
        next_sec = re.search(r"\n(?=##\s+|---\s*\n)", text[sa_start:])
        sa_raw = text[sa_start : sa_start + next_sec.start()] if next_sec else text[sa_start:]

        q_blocks = re.split(r"\n(?=###\s*(?:Q:)?\s*)", sa_raw.strip())
        answers: List[Dict[str, str]] = []
        for blk in q_blocks:
            blk = blk.strip()
            if not blk or blk.startswith("*No screening questions"):
                continue
            hdr_match = re.match(r"^###\s*(?:Q:)?\s*(.+?)(?:\n|$)", blk)
            if hdr_match:
                q_text = sanitize_no_em_dash(hdr_match.group(1).strip())
                ans_body = blk[hdr_match.end():].strip()
                ans_body = re.sub(r"^\*{0,2}Answer:\*{0,2}\s*", "", ans_body, flags=re.IGNORECASE).strip()
                if q_text:
                    answers.append({
                        "question": q_text,
                        "answer": sanitize_no_em_dash(ans_body)
                    })
            else:
                bullet_match = re.search(r"[•\-\*]\s*(?:Q:)?\s*(.+?)(?:\n\s*(?:👉|A:|\*\*Answer:\*\*)\s*(.+)|$)", blk, re.DOTALL)
                if bullet_match:
                    q_text = sanitize_no_em_dash(bullet_match.group(1).strip())
                    ans_text = sanitize_no_em_dash((bullet_match.group(2) or "").strip())
                    if q_text:
                        answers.append({
                            "question": q_text,
                            "answer": ans_text
                        })

        res["answers"] = answers

    return res


_default_publisher: Optional[NotionPublisher] = None


def get_publisher() -> NotionPublisher:
    global _default_publisher
    if _default_publisher is None:
        _default_publisher = NotionPublisher()
    return _default_publisher


def publish_staged_proposal(job: Dict[str, Any], score_res: Optional[Dict[str, Any]] = None) -> Tuple[bool, Optional[str], Optional[str]]:
    return get_publisher().publish_staged_proposal(job, score_res)


def fetch_staged_proposal(page_id: str) -> Optional[Dict[str, Any]]:
    return get_publisher().fetch_staged_proposal(page_id)


def update_proposal_status(page_id: str, new_status: str, title: str) -> bool:
    return get_publisher().update_proposal_status(page_id, new_status, title)

