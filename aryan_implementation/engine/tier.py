"""
Tier Identity, Priorities, Capabilities, and Metadata for Upwork Engine.
Identifies whether the process is executing on Railway, Vercel, or Local PC.
"""
from __future__ import annotations

import os
import subprocess
from typing import Dict, Set

# Tier priorities (1 is highest priority)
PRIORITY: Dict[str, int] = {
    "railway": 1,
    "vercel": 2,
    "local": 3,
}

# Declared capabilities per tier
CAPABILITIES: Dict[str, Set[str]] = {
    "railway": {
        "hunt",
        "watchdog",
        "telegram_polling",
        "alerts",
        "daily_report",
        "notion_sync",
        "monthly_strategy",
        "dashboard",
    },
    "vercel": {
        "hunt",
        "watchdog",
        "telegram_webhook",
        "alerts",
        "daily_report",
        "dashboard",
    },
    "local": {
        "hunt",
        "watchdog",
        "telegram_polling",
        "alerts",
        "windows_toast",
        "daily_report",
        "notion_sync",
        "monthly_strategy",
        "cloud_backup",
        "ide_sync",
    },
}


def current_tier() -> str:
    """
    Determine the current execution tier.
    Precedence:
    1. Explicit ENGINE_TIER env var
    2. Railway environment indicators
    3. Vercel environment indicators
    4. Default: local
    """
    explicit = os.environ.get("ENGINE_TIER")
    if explicit:
        return explicit.lower()

    if os.environ.get("RAILWAY_SERVICE_ID") or os.environ.get("RAILWAY_PROJECT_ID"):
        return "railway"

    if os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"):
        return "vercel"

    return "local"


def can(tier: str, capability: str) -> bool:
    """Check if a specific tier possesses a declared capability."""
    tier_name = tier.lower()
    return capability in CAPABILITIES.get(tier_name, set())


def get_commit_sha() -> str:
    """Resolve the current git commit SHA across environments."""
    for env_var in ["RAILWAY_GIT_COMMIT_SHA", "VERCEL_GIT_COMMIT_SHA", "GIT_COMMIT_SHA"]:
        val = os.environ.get(env_var)
        if val:
            return val[:8]

    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass

    return "unknown"
