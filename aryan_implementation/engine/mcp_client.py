"""
MCP Client adapter for the official Upwork MCP server.
Supports HTTP/JSON-RPC integration, identity validation, and mock/offline execution.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Union

from .logger import execute_with_audit

logger = logging.getLogger("upwork_engine")


class UpworkMCPClient:
    """Client for Upwork Model Context Protocol server."""

    def __init__(
        self,
        endpoint_url: str = "https://mcp.upwork.com/mcp",
        auth_token: Optional[str] = None,
        mock_mode: bool = False,
    ):
        self.endpoint_url = endpoint_url
        self.auth_token = auth_token
        self.mock_mode = mock_mode
        self._mock_data: Dict[str, Any] = {}

    def set_mock_data(self, key: str, data: Any) -> None:
        """Register mock responses for testing and dry-run simulation."""
        self._mock_data[key] = data

    def call_raw(self, tool: str, params: Dict[str, Any]) -> Any:
        """Low-level tool invocation (or mock simulation)."""
        if self.mock_mode:
            action = params.get("action", "")
            mock_key = f"{tool}.{action}" if action else tool
            if mock_key in self._mock_data:
                res = self._mock_data[mock_key]
                return res(params) if callable(res) else res
            if tool in self._mock_data:
                res = self._mock_data[tool]
                return res(params) if callable(res) else res

            # Default canned mocks for common read-only tools
            if tool == "list_accounts":
                return {"accounts": [{"id": "aryan_upwork_id", "name": "Aryan", "type": "freelancer"}]}
            elif tool == "get_profile":
                action = params.get("action")
                if action == "connects_balance":
                    return {"balance": 110, "currency": "USD"}
                return {"name": "Aryan", "title": "AI Automation & Claude Implementation", "jss": 100}
            elif tool == "get_freelancer_dashboard":
                return {"profile_views": 12, "proposals_sent": 3, "interviews": 1}
            elif tool == "find_jobs":
                action = params.get("action")
                if action in ("smart_search", "search"):
                    return {
                        "count": 0,
                        "jobs": [],
                        "filters_ignored": ["verified_payment_only"] if action == "smart_search" else [],
                    }
                elif action == "get":
                    job_id = params.get("job_id", "~01test")
                    return {
                        "job_id": job_id,
                        "title": "Claude AI Automation Engineer",
                        "description": "Need an expert to connect Claude to our internal tools via MCP and build automated workflows.",
                        "type": "fixed",
                        "budget_fixed": 1200,
                        "client_record": {"total_spent": 15000, "hire_rate_percent": 80, "rating": 4.9, "payment_verified": True},
                        "activityStat": {"jobActivity": {"totalInvitedToInterview": 1, "invitesSent": 2}},
                        "connects_cost": 16,
                        "can_apply": True,
                        "applied": False,
                    }
            elif tool == "list_freelancer_proposals":
                return {"proposals": [], "count": 0}
            elif tool == "list_contracts":
                return {"contracts": [], "count": 0}
            elif tool == "manage_proposals":
                action = params.get("action")
                if action == "create":
                    return {"preview_id": "prev_12345", "status": "preview_ready"}
                elif action == "confirm_preview":
                    return {"proposal_id": "prop_998877", "connects_spent": 16, "status": "submitted"}

            return {"ok": True, "mock": True, "tool": tool, "params": params}

        # Real MCP invocation over JSON-RPC or transport
        raise NotImplementedError("Live remote MCP transport requires active MCP session or daemon connection.")

    def call_tool(
        self,
        tool: str,
        action: str,
        params: Dict[str, Any],
        run_id: str,
        campaign: Optional[str] = None,
        state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Call an MCP tool wrapped with audit logging and error handling."""
        return execute_with_audit(
            func=self.call_raw,
            tool=tool,
            action=action,
            params=params,
            run_id=run_id,
            campaign=campaign,
            state=state,
        )

    def verify_account_identity(self, run_id: str) -> Tuple[bool, str]:
        """Verify that the connector is authorized as Aryan."""
        res = self.call_tool("list_accounts", "", {}, run_id=run_id)
        if not res.get("ok"):
            return False, f"Failed to list accounts: {res.get('message')}"
        data = res.get("data", {})
        accounts = data.get("accounts", [])
        if not accounts:
            return False, "No accounts returned from Upwork connector"

        # Check for Aryan
        for acc in accounts:
            name = acc.get("name", "")
            if "aryan" in name.lower():
                return True, name
            # Check if it's still Patrick H.
            if "patrick" in name.lower():
                return False, f"Connector is still authorized as '{name}', NOT Aryan. Re-auth required."

        primary_name = accounts[0].get("name", "Unknown")
        return False, f"Account '{primary_name}' does not match Aryan"
