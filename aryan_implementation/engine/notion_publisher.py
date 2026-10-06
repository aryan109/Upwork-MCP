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
