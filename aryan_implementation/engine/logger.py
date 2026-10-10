"""
Audit logging, error classification, and MCP execution wrapper for the Upwork engine.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple, Union

from .config import RUNS_LOG_PATH, ERROR_CLASSES

logger = logging.getLogger("upwork_engine")


def redact_data(data: Any) -> Any:
    """Remove sensitive tokens and credentials before writing to audit logs."""
    if data is None:
        return None
    try:
        raw_str = json.dumps(data, default=str)
        # Redact known credential keywords
        for key in ["access_token", "refresh_token", "authorization", "secret", "password", "token"]:
            if key in raw_str.lower():
                # If it's a dict, sanitize keys
                pass
        if len(raw_str) > 20000:
            return {
                "_truncated": True,
                "length": len(raw_str),
                "sha1": hashlib.sha1(raw_str.encode("utf-8")).hexdigest(),
            }
        parsed = json.loads(raw_str)
        return _deep_redact(parsed)
    except Exception:
        return {"_unserializable": str(type(data).__name__)}


def _deep_redact(obj: Any) -> Any:
    sensitive_keys = {
        "access_token",
        "refresh_token",
        "authorization",
        "auth_token",
        "password",
        "secret",
        "api_key",
    }
    if isinstance(obj, dict):
        cleaned = {}
        for k, v in obj.items():
            if str(k).lower() in sensitive_keys:
                cleaned[k] = "[REDACTED]"
            else:
                cleaned[k] = _deep_redact(v)
        return cleaned
    elif isinstance(obj, list):
        return [_deep_redact(x) for x in obj]
    return obj


def classify_error(err: Union[Exception, str]) -> str:
    """Classify an error message into one of the designated categories."""
    msg = str(err).lower()
    if any(x in msg for x in ["401", "unauthor", "unauthenticated", "invalid_token", "forbidden", "403"]):
        return "auth"
    if any(x in msg for x in ["429", "rate limit", "too many requests", "throttle"]):
        return "rate_limit"
    if any(x in msg for x in ["vj-ja-10", "already applied", "cannot apply", "can_apply=false", "closed"]):
        return "business"
    if any(x in msg for x in ["timeout", "timed out", "502", "503", "504", "connection reset", "econnreset"]):
        return "transient"
    if any(x in msg for x in ["filters_rejected", "validation error", "invalid param", "cover_letter too long"]):
        return "validation"
    if any(x in msg for x in ["tool not found", "unknown tool", "tool_mismatch", "schema mismatch"]):
        return "tool_mismatch"
    if any(x in msg for x in ["missing client_record", "unexpected format", "keyerror", "jsondecodeerror"]):
        return "data"
    return "validation"


def log_event(
    run_id: str,
    step: str,
    campaign: Optional[str] = None,
    inputs: Optional[Any] = None,
    state_before: Optional[Any] = None,
    result: Optional[Any] = None,
    error: Optional[Dict[str, Any]] = None,
    duration_ms: Optional[int] = None,
    log_path: Optional[Path] = None,
) -> None:
    """Append a structured JSON line to runs.jsonl audit log."""
    path = log_path or RUNS_LOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "step": step,
        "campaign": campaign or "none",
        "input": redact_data(inputs),
        "state_before": redact_data(state_before),
        "result": redact_data(result),
        "duration_ms": duration_ms,
        "error": error,
    }

    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Audit log writing failed: {e}")


def summarize_result(res: Any) -> Any:
    """Provide a compact representation of MCP call results."""
    if isinstance(res, dict):
        summary = {}
        for k in ("count", "jobs", "results", "preview_id", "proposal_id", "balance", "filters_ignored"):
            if k in res:
                v = res[k]
                summary[k] = len(v) if isinstance(v, list) else v
        if not summary:
            # Fallback to key preview
            summary = {"keys": list(res.keys())[:5], "total_keys": len(res)}
        return summary
    return {"type": type(res).__name__}


def execute_with_audit(
    func: Callable[..., Any],
    tool: str,
    action: str,
    params: Dict[str, Any],
    *,
    run_id: str,
    campaign: Optional[str] = None,
    state: Optional[Dict[str, Any]] = None,
    retries: int = 3,
    log_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Execute a function with full audit logging, retry handling and error classification."""
    step_name = f"{tool}.{action}" if action else tool
    inputs = {"tool": tool, "action": action, **params}
    t0 = time.time()

    for attempt in range(1, retries + 1):
        try:
            res = func(tool, {"action": action, **params} if action else params)
            duration_ms = int((time.time() - t0) * 1000)

            # Check for filter rejections reported in payload
            if isinstance(res, dict) and res.get("filters_rejected"):
                err_info = {
                    "class": "validation",
                    "msg": "filters_rejected",
                    "details": res.get("filters_rejected"),
                }
                log_event(
                    run_id=run_id,
                    step=step_name,
                    campaign=campaign,
                    inputs=inputs,
                    state_before=state,
                    result={"ok": False, "filters_rejected": res["filters_rejected"]},
                    error=err_info,
                    duration_ms=duration_ms,
                    log_path=log_path,
                )
                return {"ok": False, "error_class": "validation", "data": res}

            log_event(
                run_id=run_id,
                step=step_name,
                campaign=campaign,
                inputs=inputs,
                state_before=state,
                result={"ok": True, "summary": summarize_result(res)},
                duration_ms=duration_ms,
                log_path=log_path,
            )
            return {"ok": True, "data": res}

        except Exception as e:
            duration_ms = int((time.time() - t0) * 1000)
            err_class = classify_error(e)
            err_payload = {
                "class": err_class,
                "msg": str(e)[:500],
                "attempt": attempt,
                "trace": traceback.format_exc()[-1000:],
            }

            log_event(
                run_id=run_id,
                step=step_name,
                campaign=campaign,
                inputs=inputs,
                state_before=state,
                error=err_payload,
                duration_ms=duration_ms,
                log_path=log_path,
            )

            if state is not None:
                incidents = state.setdefault("incidents", [])
                incidents.append({
                    "at": datetime.now(timezone.utc).isoformat(),
                    "type": err_class,
                    "detail": str(e)[:200],
                    "resolved": False,
                })
                if len(incidents) > 50:
                    state["incidents"] = incidents[-50:]

            if err_class in ("auth", "rate_limit"):
                logger.warning(f"[{err_class.upper()}] MCP execution error in {step_name} (attempt {attempt}): {e}")

            if err_class == "auth":
                # Auth failures must immediately fail and halt the pipeline
                return {"ok": False, "error_class": "auth", "message": str(e)}

            if err_class in ("business", "validation", "tool_mismatch"):
                return {"ok": False, "error_class": err_class, "message": str(e)}

            # For transient or rate limit errors, apply backoff
            if attempt < retries:
                backoff = 2 ** attempt
                time.sleep(backoff)

    return {"ok": False, "error_class": "transient", "message": f"Retries exhausted ({retries} attempts)"}
