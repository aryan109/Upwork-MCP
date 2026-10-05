"""
Unit tests for the standalone serverless visualizer.html
"""
from pathlib import Path
import json
import re


def test_visualizer_html_exists():
    workspace = Path(__file__).resolve().parent.parent.parent
    html_path = workspace / "visualizer.html"
    assert html_path.exists(), "visualizer.html should exist at workspace root"
    assert html_path.stat().st_size > 100_000, "visualizer.html should contain embedded content"


def test_visualizer_html_embedded_payload():
    workspace = Path(__file__).resolve().parent.parent.parent
    html_path = workspace / "visualizer.html"
    content = html_path.read_text(encoding="utf-8")

    # Extract JSON embedded inside script tag
    match = re.search(r'<script id="embedded-xml-data" type="application/json">\s*(\[.*?\])\s*</script>', content, re.DOTALL)
    assert match is not None, "embedded-xml-data JSON payload should be present"

    raw_json = match.group(1)
    files = json.loads(raw_json)
    assert len(files) >= 11, f"Expected at least 11 XML files embedded, got {len(files)}"

    filenames = [f["name"] for f in files]
    assert "ARYAN_IMPLEMENTATION_PLAN.xml" in filenames
    assert "UPWORK_MCP_DOCUMENTATION.xml" in filenames
    assert any("comparitive_analysis" in name or "comparative_analysis" in name for name in filenames)


def test_visualizer_html_features():
    workspace = Path(__file__).resolve().parent.parent.parent
    html_path = workspace / "visualizer.html"
    content = html_path.read_text(encoding="utf-8")

    # Verify key serverless capabilities
    assert "showDirectoryPicker" in content, "Should include File System Access API support"
    assert "DOMParser" in content, "Should use browser native DOMParser"
    assert "dropzone-overlay" in content, "Should support drag and drop"
    assert "renderPlanDashboard" in content, "Should include specialized Plan dashboard"
    assert "renderMcpDashboard" in content, "Should include specialized MCP dashboard"
    assert "renderTreeNode" in content, "Should include interactive XML tree"
