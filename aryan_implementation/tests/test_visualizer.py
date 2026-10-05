"""
Unit tests for XML Visualizer parser, APIs, and file watching.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from aryan_implementation.visualizer.parser import parse_xml_file, detect_file_type
from aryan_implementation.visualizer.server import FileWatcher, EventBroadcaster

WORKSPACE_DIR = Path(__file__).resolve().parent.parent.parent


def test_parse_implementation_plan() -> None:
    plan_file = WORKSPACE_DIR / "aryan_implementation" / "ARYAN_IMPLEMENTATION_PLAN.xml"
    res = parse_xml_file(plan_file)

    assert res["ok"] is True
    assert res["file_type"] == "implementation_plan"
    spec = res["specialized"]
    assert "progress" in spec
    assert spec["progress"]["total_tasks"] == 73
    assert len(spec["phases"]) == 6
    assert len(spec["gates"]) == 8
    assert len(spec["campaigns"]) == 7


def test_parse_mcp_documentation() -> None:
    mcp_file = WORKSPACE_DIR / "UPWORK_MCP_DOCUMENTATION.xml"
    res = parse_xml_file(mcp_file)

    assert res["ok"] is True
    assert res["file_type"] == "mcp_documentation"
    spec = res["specialized"]
    assert spec["tool_count"] > 40
    assert len(spec["domains"]) > 0


def test_parse_comparative_analysis() -> None:
    comp_file = WORKSPACE_DIR / "Upwork_plan_comparitive_analysis_gemini_flash.xml"
    res = parse_xml_file(comp_file)

    assert res["ok"] is True
    assert res["file_type"] == "comparative_analysis"
    spec = res["specialized"]
    assert "agreements" in spec
    assert "verdict" in spec


def test_file_watcher_scan(tmp_path: Path) -> None:
    # Create test XML file
    test_xml = tmp_path / "test.xml"
    test_xml.write_text("<root><item>Hello</item></root>", encoding="utf-8")

    watcher = FileWatcher(tmp_path)
    mtimes = watcher.scan_files()

    assert "test.xml" in mtimes
    assert mtimes["test.xml"] > 0
