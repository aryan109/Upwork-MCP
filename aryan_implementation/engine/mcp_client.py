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

        # Real MCP invocation over JSON-RPC HTTP transport
        return self._call_remote_mcp(tool, params)

    def _call_remote_mcp(self, tool: str, params: Dict[str, Any]) -> Any:
        import os
        import urllib.request
        from pathlib import Path

        # Resolve access token
        access_token = self.auth_token
        if not access_token:
            for potential_path in [
                Path(os.environ.get("USERPROFILE", "")) / ".gemini" / "antigravity" / "mcp_oauth_tokens.json",
                Path(os.environ.get("USERPROFILE", "")) / ".gemini" / "antigravity-ide" / "mcp_oauth_tokens.json",
            ]:
                if potential_path.exists():
                    try:
                        with open(potential_path, "r", encoding="utf-8") as tf:
                            td = json.load(tf)
                            upwork_tok = td.get("https://mcp.upwork.com/mcp", {}).get("token", {})
                            access_token = upwork_tok.get("access_token")
                            if access_token:
                                break
                    except Exception:
                        pass

        if not access_token:
            raise RuntimeError("Live Upwork MCP requires valid OAuth token in mcp_oauth_tokens.json")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "Antigravity/1.0 (Windows)",
        }

        # Initialize session if not cached
        if not getattr(self, "_mcp_session_id", None):
            init_body = json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "aryan-upwork-engine", "version": "1.0"},
                },
            }).encode("utf-8")
            init_req = urllib.request.Request(self.endpoint_url, data=init_body, headers=headers, method="POST")
            with urllib.request.urlopen(init_req, timeout=15) as r:
                self._mcp_session_id = r.headers.get("mcp-session-id")
                self._mcp_cookie = r.headers.get("set-cookie")

        headers["mcp-session-id"] = self._mcp_session_id
        if getattr(self, "_mcp_cookie", None):
            headers["Cookie"] = self._mcp_cookie

        # Prepare tool call
        full_tool_name = f"upwork__{tool}" if not tool.startswith("upwork__") else tool
        action = params.get("action", "")
        # Remove action from inner params copy to avoid duplicate
        inner_params = {k: v for k, v in params.items() if k != "action"}

        arguments: Dict[str, Any] = {
            "org_uid": "1243443370794516481",
        }
        if action:
            arguments["action"] = action
        if inner_params:
            arguments["params"] = inner_params

        call_body = json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": full_tool_name,
                "arguments": arguments,
            },
        }).encode("utf-8")

        call_req = urllib.request.Request(self.endpoint_url, data=call_body, headers=headers, method="POST")
        with urllib.request.urlopen(call_req, timeout=20) as r:
            res_json = json.loads(r.read().decode("utf-8"))
            content = res_json.get("result", {}).get("content", [])
            if content and "text" in content[0]:
                text = content[0]["text"]
                try:
                    return json.loads(text)
                except Exception:
                    return text
            return res_json.get("result", {})

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
