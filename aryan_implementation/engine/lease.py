"""
Distributed Lease Manager for Upwork Engine.
Ensures exactly one active hunter across Railway, Vercel, and Local PC tiers.
Enforces 20-minute lease expiry, CAS writes, priority-based yields, and no mid-pass preemption.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Tuple

from .state_backend import StateBackend, get_default_backend
from .tier import PRIORITY

logger = logging.getLogger("upwork_engine")

LEASE_FILE = "lease.json"
LEASE_DURATION_SECONDS = 1200  # 20 minutes


class LeaseManager:
    """Manages distributed leases using the shared state backend."""

    def __init__(self, backend: Optional[StateBackend] = None):
        self.backend = backend or get_default_backend()

    def try_acquire(
        self,
        resource: str,
        tier: str,
        run_id: str = "",
        force: bool = False,
    ) -> bool:
        """
        Attempt to acquire or extend the lease for a given resource.
        Returns True if lease acquired.
        """
        now_utc = datetime.now(timezone.utc)
        now_iso = now_utc.isoformat()
        expires_dt = now_utc + timedelta(seconds=LEASE_DURATION_SECONDS)
        expires_iso = expires_dt.isoformat()

        # Read current lease
        lease_data, sha = self.backend.read_json(LEASE_FILE)
        tier_prio = PRIORITY.get(tier.lower(), 99)

        if lease_data:
            current_holder = lease_data.get("holder", "")
            exp_str = lease_data.get("expires_at", "")
            is_expired = True

            if exp_str:
                try:
                    exp_dt = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
                    if now_utc < exp_dt:
                        is_expired = False
                except Exception:
                    is_expired = True

            # If held by self, extend
            if current_holder.lower() == tier.lower():
                lease_data["expires_at"] = expires_iso
                lease_data["updated_at"] = now_iso
                ok, _ = self.backend.write_json(LEASE_FILE, lease_data, message=f"extend lease {tier}", sha=sha)
                return ok

            # If not expired and not held by self, check if can acquire
            if not is_expired and not force:
                logger.info(
                    f"Lease for '{resource}' currently held by '{current_holder}' "
                    f"until {exp_str} (tier priority: {PRIORITY.get(current_holder, 99)} vs {tier_prio})."
                )
                return False

        # Attempt to acquire lease via CAS write
        new_lease = {
            "resource": resource,
            "holder": tier.lower(),
            "acquired_at": now_iso,
            "expires_at": expires_iso,
            "run_id": run_id,
            "updated_at": now_iso,
        }

        ok, _ = self.backend.write_json(
            LEASE_FILE,
            new_lease,
            message=f"acquire lease for {tier}",
            sha=sha,
        )
        if ok:
            logger.info(f"Successfully acquired lease for '{resource}' as tier '{tier}'. Expires at {expires_iso}.")
        else:
            logger.warning(f"Failed to acquire lease for '{resource}' as tier '{tier}' due to CAS conflict.")

        return ok

    def should_yield(self, tier: str) -> bool:
        """
        Determine if current tier should yield the lease to a higher-priority tier.
        Checks if any higher-priority tier has a fresh heartbeat (< 20 mins old).
        """
        tier_prio = PRIORITY.get(tier.lower(), 99)
        now_utc = datetime.now(timezone.utc)

        for higher_tier, prio in PRIORITY.items():
            if prio < tier_prio:
                hb_file = f"heartbeats/{higher_tier}.json"
                hb_data, _ = self.backend.read_json(hb_file)
                if hb_data and hb_data.get("ok"):
                    seen_str = hb_data.get("seen_at")
                    if seen_str:
                        try:
                            seen_dt = datetime.fromisoformat(seen_str.replace("Z", "+00:00"))
                            if (now_utc - seen_dt).total_seconds() < 1200:
                                logger.info(
                                    f"Yielding lease: Higher-priority tier '{higher_tier}' (priority {prio}) "
                                    f"is active (heartbeat: {seen_str})."
                                )
                                return True
                        except Exception:
                            pass
        return False

    def renew_or_yield(self, resource: str, tier: str) -> bool:
        """
        Renew lease if healthy, or yield (release) if higher-priority tier is active.
        """
        if self.should_yield(tier):
            logger.info(f"Tier '{tier}' yielding lease for '{resource}'.")
            self.force_release(resource)
            return False

        return self.try_acquire(resource, tier)

    def force_release(self, resource: str) -> bool:
        """Release the lease immediately."""
        lease_data, sha = self.backend.read_json(LEASE_FILE)
        if lease_data:
            empty_lease = {
                "resource": resource,
                "holder": None,
                "acquired_at": None,
                "expires_at": None,
                "released_at": datetime.now(timezone.utc).isoformat(),
            }
            ok, _ = self.backend.write_json(LEASE_FILE, empty_lease, message=f"release lease {resource}", sha=sha)
            return ok
        return True

    def get_lease(self, resource: str = "hunter") -> Tuple[Dict[str, Any], Optional[str]]:
        """Retrieve current lease status."""
        data, sha = self.backend.read_json(LEASE_FILE)
        if data and data.get("holder"):
            active = True
            exp = data.get("expires_at")
            if exp:
                try:
                    exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                    if datetime.now(timezone.utc) >= exp_dt:
                        active = False
                except Exception:
                    active = False
            data["active"] = active
            return data, sha
        return {"holder": None, "active": False, "resource": resource}, sha


def try_acquire_lease(resource: str = "hunter", tier: str = "local") -> bool:
    """Convenience helper to attempt lease acquisition."""
    return LeaseManager().try_acquire(resource, tier)
