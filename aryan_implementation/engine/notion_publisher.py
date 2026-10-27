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
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .config import PROJECT_ROOT

logger = logging.getLogger("notion_publisher")

# Notion Page IDs created for Aryan's workspace
NOTION_MASTER_PAGE_ID = "3f197b4f-8610-816e-8ab0-cf54ac7b3a3e"
NOTION_DAILY_REPORTS_PAGE_ID = "3f197b4f-8610-81a1-ac3e-d59e9c8bf7d7"
NOTION_MARKET_INTEL_PAGE_ID = "3f197b4f-8610-81a7-b919-f430b7816837"

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
