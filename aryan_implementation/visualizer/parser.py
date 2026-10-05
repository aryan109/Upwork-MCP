"""
XML Parser and specialized data extractor for human-readable visualisations.
Converts arbitrary XML and domain-specific schemas into structured JSON.
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


def xml_node_to_dict(node: ET.Element) -> Dict[str, Any]:
    """Recursively convert an XML element tree to a nested dictionary."""
    text = (node.text or "").strip()
    children = [xml_node_to_dict(child) for child in node]
    return {
        "tag": node.tag,
        "attrib": dict(node.attrib),
        "text": text if text else None,
        "children": children,
    }


def parse_xml_file(filepath: Union[str, Path]) -> Dict[str, Any]:
    """Parse an XML file into raw text, generic tree, and specialized view models."""
    path = Path(filepath)
    with open(path, "r", encoding="utf-8") as f:
        raw_content = f.read()

    try:
        root = ET.fromstring(raw_content)
    except ET.ParseError as e:
        return {
            "ok": False,
            "error": f"XML parse error: {e}",
            "raw": raw_content,
            "filename": path.name,
            "path": str(path),
            "file_type": "error",
            "root_tag": "error",
            "attributes": {},
            "specialized": {},
            "tree": None,
            "size_bytes": len(raw_content.encode("utf-8")),
        }

    generic_tree = xml_node_to_dict(root)
    file_type = detect_file_type(root, path)

    specialized_data = {}
    if file_type == "implementation_plan":
        specialized_data = extract_implementation_plan(root)
    elif file_type == "mcp_documentation":
        specialized_data = extract_mcp_documentation(root)
    elif file_type == "comparative_analysis":
        specialized_data = extract_comparative_analysis(root)
    elif file_type == "strategy_overhaul":
        specialized_data = extract_strategy_overhaul(root)

    return {
        "ok": True,
        "filename": path.name,
        "path": str(path),
        "file_type": file_type,
        "root_tag": root.tag,
        "attributes": dict(root.attrib),
        "specialized": specialized_data,
        "tree": generic_tree,
        "raw": raw_content,
        "size_bytes": len(raw_content.encode("utf-8")),
    }


def detect_file_type(root: ET.Element, path: Path) -> str:
    """Identify the specialized category of an XML document."""
    tag = root.tag.lower()
    name = path.name.lower()

    if tag == "implementation_plan" or "aryan_implementation_plan" in name:
        return "implementation_plan"
    if "mcp_documentation" in tag or "mcp" in name:
        return "mcp_documentation"
    if "comparative_analysis" in tag or "comparative_analysis" in name or "consensus" in name:
        return "comparative_analysis"
    if "overhaul_plan" in tag or "strategy" in name or "overhaul" in name:
        return "strategy_overhaul"

    return "generic_xml"


def extract_implementation_plan(root: ET.Element) -> Dict[str, Any]:
    """Extract full dashboard view model for ARYAN_IMPLEMENTATION_PLAN.xml."""
    summary_el = root.find("summary")
    summary = {}
    if summary_el is not None:
        pos = summary_el.find("positioning")
        title_el = summary_el.find("title")
        summary["positioning"] = pos.text.strip() if pos is not None and pos.text else ""
        summary["title"] = dict(title_el.attrib) if title_el is not None else {}
        summary["baseline"] = summary_el.findtext("baseline", "").strip()
        summary["offer_ladder_summary"] = summary_el.findtext("offer_ladder_summary", "").strip()

        # Rate ladder
        rate_steps = []
        for step in summary_el.findall(".//rate_ladder/step"):
            rate_steps.append({**dict(step.attrib), "note": step.attrib.get("note", "")})
        summary["rate_ladder"] = rate_steps

        # Non-negotiables
        rules = []
        for r in summary_el.findall(".//non_negotiables/rule"):
            rules.append({"id": r.attrib.get("id"), "text": (r.text or "").strip()})
        summary["non_negotiables"] = rules

    # Phases & Tasks
    phases = []
    total_tasks = 0
    completed_tasks = 0

    for p in root.findall(".//phases/phase"):
        phase_info = dict(p.attrib)
        tasks = []
        for t in p.findall("tasks/task"):
            total_tasks += 1
            status = t.attrib.get("status", "todo")
            if status == "done":
                completed_tasks += 1

            tasks.append({
                "id": t.attrib.get("id"),
                "status": status,
                "day": t.attrib.get("day"),
                "owner": t.attrib.get("owner"),
                "priority": t.attrib.get("priority"),
                "title": t.findtext("title", "").strip(),
                "description": t.findtext("description", "").strip(),
                "tool": t.findtext("tool", "").strip(),
                "acceptance": t.findtext("acceptance_criteria", "").strip(),
                "rollback": t.findtext("rollback", "").strip(),
                "verify_live": t.find("verify_live").attrib if t.find("verify_live") is not None else {},
            })
        phase_info["tasks"] = tasks
        phases.append(phase_info)

    # Decision Gates
    gates = []
    for g in root.findall(".//decision_gates/gate"):
        gates.append({
            "id": g.attrib.get("id"),
            "when": g.attrib.get("when"),
            "status": g.attrib.get("status", "todo"),
            "related_tasks": g.attrib.get("related_tasks", ""),
            "question": g.findtext("question", "").strip(),
            "metrics": g.findtext("metrics", "").strip(),
            "if_passed": g.findtext("if_passed", "").strip(),
            "if_failed": g.findtext("if_failed", "").strip(),
        })

    # Campaigns
    campaigns = []
    for c in root.findall(".//campaigns/campaign"):
        campaigns.append({
            "id": c.attrib.get("id"),
            "active": c.attrib.get("active", "true"),
            "priority": c.attrib.get("priority"),
            "fixed_floor": c.attrib.get("fixed_floor"),
            "hourly_floor": c.attrib.get("hourly_floor"),
            "max_drafts_per_day": c.attrib.get("max_drafts_per_day"),
            "connects_cap_per_day": c.attrib.get("connects_cap_per_day"),
            "score_threshold": c.attrib.get("score_threshold"),
            "rung_default": c.attrib.get("rung_default"),
            "queries": c.findtext("queries", "").strip(),
            "title_filters": c.findtext("title_filters", "").strip(),
            "subcategories": c.findtext("subcategories", "").strip(),
        })

    # Registries
    verify_live = []
    for vl in root.findall(".//verify_live_registry/item"):
        verify_live.append({
            "id": vl.attrib.get("id"),
            "status": vl.attrib.get("status", "unverified"),
            "verified": vl.attrib.get("verified", "false") == "true",
            "used_in": vl.attrib.get("used_in", ""),
            "text": (vl.text or "").strip(),
        })

    placeholders = []
    for ph in root.findall(".//placeholders_registry/placeholder"):
        placeholders.append({
            "id": ph.attrib.get("id"),
            "file": ph.attrib.get("file"),
            "name": ph.attrib.get("name"),
            "status": ph.attrib.get("status", "todo"),
            "text": (ph.text or "").strip(),
        })

    return {
        "summary": summary,
        "progress": {
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "percent": round((completed_tasks / max(1, total_tasks)) * 100, 1),
        },
        "phases": phases,
        "gates": gates,
        "campaigns": campaigns,
        "verify_live": verify_live,
        "placeholders": placeholders,
    }


def extract_mcp_documentation(root: ET.Element) -> Dict[str, Any]:
    """Extract tool schemas and API catalog from UPWORK_MCP_DOCUMENTATION.xml."""
    tools = []
    domains = {}

    for tool in root.findall(".//tool") or root.findall(".//tool_definition"):
        t_id = tool.attrib.get("id") or tool.attrib.get("name") or tool.findtext("name", "")
        domain = tool.attrib.get("domain") or tool.findtext("domain", "General")
        desc = tool.findtext("description", "").strip() or tool.attrib.get("description", "")

        params = []
        for param in tool.findall(".//param") or tool.findall(".//parameter"):
            params.append({
                "name": param.attrib.get("name") or param.findtext("name", ""),
                "type": param.attrib.get("type") or param.findtext("type", "string"),
                "required": param.attrib.get("required", "false") in ("true", "1"),
                "description": (param.text or param.findtext("description", "")).strip(),
            })

        tool_obj = {
            "id": t_id,
            "domain": domain,
            "description": desc,
            "parameters": params,
        }
        tools.append(tool_obj)
        domains.setdefault(domain, []).append(tool_obj)

    # Errors
    errors = []
    for err in root.findall(".//error") or root.findall(".//error_code"):
        errors.append({
            "code": err.attrib.get("code") or err.findtext("code", ""),
            "meaning": err.findtext("meaning", "") or (err.text or "").strip(),
            "action": err.findtext("action", "").strip(),
        })

    return {
        "tool_count": len(tools),
        "domain_count": len(domains),
        "domains": [{"name": k, "tools": v} for k, v in domains.items()],
        "errors": errors,
    }


def extract_comparative_analysis(root: ET.Element) -> Dict[str, Any]:
    """Extract verdict and consensus tables from comparative analysis XML."""
    title = root.findtext("title", "") or root.attrib.get("title", "Comparative Analysis")
    verdict = root.findtext(".//verdict", "").strip() or root.findtext(".//recommendation", "").strip()

    agreements = []
    for item in root.findall(".//agreements/item") or root.findall(".//point[@type='agreement']"):
        agreements.append((item.text or item.findtext("summary", "")).strip())

    disagreements = []
    for item in root.findall(".//disagreements/item") or root.findall(".//point[@type='disagreement']"):
        disagreements.append((item.text or item.findtext("summary", "")).strip())

    scores = []
    for doc in root.findall(".//document_evaluation/document") or root.findall(".//document"):
        scores.append({
            "name": doc.attrib.get("name") or doc.findtext("name", ""),
            "verdict": doc.findtext("verdict", "").strip(),
            "score": doc.attrib.get("score") or doc.findtext("score", ""),
            "notes": doc.findtext("notes", "").strip(),
        })

    return {
        "title": title,
        "verdict": verdict,
        "agreements": agreements,
        "disagreements": disagreements,
        "document_scores": scores,
    }


def extract_strategy_overhaul(root: ET.Element) -> Dict[str, Any]:
    """Extract strategy, rates, and audit elements from overhaul plan XML."""
    positioning = root.findtext(".//positioning", "").strip()
    rate = root.findtext(".//hourly_rate", "") or root.findtext(".//rate", "")
    summary = root.findtext(".//summary", "").strip() or root.findtext(".//overview", "").strip()

    tiers = []
    for tier in root.findall(".//offer_ladder/tier") or root.findall(".//tier"):
        tiers.append({
            "name": tier.attrib.get("name") or tier.findtext("name", ""),
            "price": tier.attrib.get("price") or tier.findtext("price", ""),
            "duration": tier.attrib.get("duration") or tier.findtext("duration", ""),
            "description": (tier.text or tier.findtext("description", "")).strip(),
        })

    return {
        "positioning": positioning,
        "suggested_rate": rate,
        "summary": summary,
        "tiers": tiers,
    }
