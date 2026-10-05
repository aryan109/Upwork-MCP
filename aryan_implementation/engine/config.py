"""
Configuration and paths for Aryan Upwork MCP Acquisition Engine.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Any

# Root directory of this package
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = PACKAGE_ROOT.parent
PROJECT_ROOT = WORKSPACE_ROOT

# User state directory outside the repo
DEFAULT_ENGINE_DIR = Path(os.environ.get("USERPROFILE", os.path.expanduser("~"))) / "upwork_engine"
ENGINE_DIR = Path(os.environ.get("UPWORK_ENGINE_DIR", str(DEFAULT_ENGINE_DIR)))
STATE_DIR = ENGINE_DIR / "state"
PAYLOADS_DIR = ENGINE_DIR / "payloads"
BACKUP_DIR = ENGINE_DIR / "backup"
RUNS_LOG_PATH = STATE_DIR / "runs.jsonl"

# Templates directory in repository
TEMPLATES_DIR = PACKAGE_ROOT / "templates"
JOBS_SCHEMA_PATH = TEMPLATES_DIR / "jobs.schema.json"
STATE_SCHEMA_PATH = TEMPLATES_DIR / "state.schema.json"
CAMPAIGNS_SCHEMA_PATH = TEMPLATES_DIR / "campaigns.schema.json"
CAMPAIGNS_EXAMPLE_PATH = TEMPLATES_DIR / "campaigns.example.json"
SCORING_EXAMPLE_PATH = TEMPLATES_DIR / "scoring.example.json"
FACTS_PATH = PACKAGE_ROOT / "skills" / "aryan-profile-facts" / "SKILL.md"

# Operational Constants
DEFAULT_MAX_SUBMITS_PER_DAY = 5
DEFAULT_TARGET_SUBMITS_PER_DAY = 3
DEFAULT_MONTHLY_CONNECTS_BUDGET = 250
MAX_BOOST_CONNECTS = 10
MIN_SCORE_FOR_BOOST = 80
DEFAULT_STICKER_RATE = 65.0
MAX_DETAIL_FETCHES_PER_PASS = 25
MAX_SEARCHES_PER_PASS = 20

# Error Classes
ERROR_CLASSES = [
    "auth",
    "rate_limit",
    "validation",
    "business",
    "transient",
    "data",
    "tool_mismatch",
]

# Disqualifiers
DISQUALIFIERS = {
    "D1": "Already applied, invitation exists, or cannot apply",
    "D2": "Location required and India not eligible",
    "D3": "Capability gate (native mobile, Unity, Solidity, video, etc.)",
    "D4": "Off-platform or Terms of Service policy violation",
    "D5": "Staffing/agency pool or commission/equity-only",
    "D6": "Payment unverified AND $0 spend AND 0 hires",
    "D7": "Fixed under $100 or hourly ceiling under $25",
    "D8": "Older than 72h AND 50+ proposals AND 0 interviewing",
    "D9": "Free test task over 1 hour",
    "D10": "Conflict: open proposal or contract with same client",
    "D11": "Job already filled (hires reached limit)",
}
