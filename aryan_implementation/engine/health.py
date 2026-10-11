"""Health reason collector shared by Railway HTTP endpoints and tests."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def collect_health_reasons(
    state: Optional[Dict[str, Any]],
    now_utc: Optional[datetime] = None,
) -> List[str]:
    """Return operational reasons. Empty list means the hunter looks healthy."""
    reasons: List[str] = []
    now = now_utc or datetime.now(timezone.utc)
    st = state or {}

    if st.get("kill_switch"):
        reasons.append("kill_switch_active")

    last_success = st.get("last_success_at")
    if last_success:
        try:
            succ_dt = datetime.fromisoformat(str(last_success).replace("Z", "+00:00"))
            if (now - succ_dt).total_seconds() > 2 * 3600:
                reasons.append("hunter_silent: last successful pass > 2h old")
        except Exception:
            reasons.append("hunter_silent: last_success_at unparseable")
    else:
        reasons.append("hunter_silent: no successful pass recorded")

    last_pass = st.get("last_pass_record") or {}
    if last_pass and not last_pass.get("auth_ok", True):
        reasons.append("auth_failed: OAuth rejected")

    searches_ok = int(last_pass.get("searches_ok") or 0)
    searches_failed = int(last_pass.get("searches_failed") or 0)
    if searches_failed > 0 and searches_ok == 0:
        reasons.append("search_failed: last pass had 0 successful searches")

    return reasons
