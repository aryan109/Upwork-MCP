# Resilience Testing & Chaos Drills (Part F)

This document specifies the step-by-step procedures to simulate failures, verify automated fail-overs, and validate self-healing across the Aryan Upwork Pipeline.

---

## Drill 1: Corrupted / Junk Upwork OAuth Token

**Objective:** Validate that token invalidation triggers an immediate `W2 auth_failed` alert with remediation instructions, and local tier re-seeds from IDE tokens.

1. **Simulation:**
   Write an invalid token to the state store:
   ```python
   from aryan_implementation.engine.state_backend import get_default_backend
   b = get_default_backend()
   data, sha = b.read_json("secrets/upwork_oauth.json")
   data["access_token"] = "junk_invalid_token"
   b.write_json("secrets/upwork_oauth.json", data, sha=sha, message="drill: corrupt token")
   ```
2. **Execute Tick:**
   Run a tick on any tier:
   ```bash
   python -m aryan_implementation.engine.tick --tier local
   ```
3. **Expected Behavior:**
   - Watchdog detects auth failure.
   - Alert `W2 auth_failed` is dispatched to Telegram (and local toast) naming remediation: `python -m aryan_implementation.engine.cli upwork-login`.
   - On the next local tick, `reseed_from_ide_file()` detects the discrepancy and restores a working token.

---

## Drill 2: Railway Outage & Automated Fail-Over

**Objective:** Verify that when Priority 1 (Railway) goes silent, Priority 2 (Vercel) or Priority 3 (Local) acquires the lease without race conditions.

1. **Simulation:**
   Down the Railway service or simulate stale heartbeat (> 35 min).
2. **Execute Tick on Vercel or Local:**
   Trigger `/api/tick` on Vercel or run `python -m aryan_implementation.engine.tick --tier local`.
3. **Expected Behavior:**
   - Watchdog detects `W1 hunter_silent` and `W3 tier_missing (railway)`.
   - Secondary tier acquires `hunter` lease upon expiration of Railway's 20-minute lease.
   - Discovery runs normally; proof-of-work recorded in `passes/<tier>/<date>.jsonl`.
   - When Railway returns, secondary tier yields the lease at pass end.

---

## Drill 3: Rapid Deployments & Concurrency Protection

**Objective:** Verify that restarting or deploying a tier multiple times within an hour generates zero duplicate cards and zero duplicate daily reports.

1. **Simulation:**
   Trigger 3 consecutive runs within 10 seconds:
   ```bash
   python -m aryan_implementation.engine.tick --tier local
   python -m aryan_implementation.engine.tick --tier local
   python -m aryan_implementation.engine.tick --tier local
   ```
2. **Expected Behavior:**
   - `lease.try_acquire` succeeds for the first call and returns `False` for concurrent ticks.
   - Staged proposal cards check `alerted_at`; existing cards are never re-sent.
   - Only 1 daily report is dispatched per calendar day.

---

## Drill 4: Simultaneous / Concurrent `/api/tick` Invocations

**Objective:** Verify distributed compare-and-swap (CAS) lock on `lease.json`.

1. **Simulation:**
   Send two simultaneous POST requests to `/api/tick`:
   ```bash
   curl -X POST https://<app>.vercel.app/api/tick -H "X-Tick-Secret: <secret>" &
   curl -X POST https://<app>.vercel.app/api/tick -H "X-Tick-Secret: <secret>"
   ```
2. **Expected Behavior:**
   - One request acquires the lease and executes the hunt pass.
   - The second request receives `status: standby, role: watchdog`.
   - Exactly one pass record written to `passes/vercel/<date>.jsonl`.

---

## Drill 5: Store Unreachable / GitHub API Downtime

**Objective:** Verify graceful degradation when the remote state store is unreachable.

1. **Simulation:**
   Temporarily execute local tick with a bad token or invalid repo:
   ```bash
   STATE_REPO_TOKEN=invalid_token python -m aryan_implementation.engine.tick --tier local
   ```
2. **Expected Behavior:**
   - Cloud tiers abort safely with `store_unreachable_aborted` to prevent split-brain writes.
   - Local PC logs alert `W6 store_unreachable` and continues safely from local disk cache (`%USERPROFILE%\upwork_engine\state`).

---

## Drill 6: Emergency Kill Switch

**Objective:** Verify immediate halting of all discovery and bidding.

1. **Simulation:**
   Set kill switch:
   ```bash
   python -m aryan_implementation.engine.cli kill-switch on --reason "Chaos drill test"
   ```
2. **Execute Tick:**
   Run `python -m aryan_implementation.engine.tick --tier local`.
3. **Expected Behavior:**
   - Watchdog detects `W4 kill_switch_active`.
   - Pass aborts before issuing any Upwork API calls.
   - Telegram receives critical alert.
4. **Recovery:**
   ```bash
   python -m aryan_implementation.engine.cli kill-switch off
   ```

---

## Drill 7: Telegram API Network Block

**Objective:** Verify that even if Telegram is completely blocked or unreachable, external monitoring still functions.

1. **Simulation:**
   Set an invalid `TELEGRAM_BOT_TOKEN`.
2. **Execute Tick:**
   Run `python -m aryan_implementation.engine.tick --tier local`.
3. **Expected Behavior:**
   - Telegram notifier logs warning and never raises unhandled exceptions.
   - On Windows local tier, system tray toast notification still fires.
   - On healthy passes, external `dead_man_ping()` still reaches healthchecks.io.

---

## Drill 8: Offline PC Resumption (3-Day Simulation)

**Objective:** Verify that when the local PC turns on after being powered off for days, state seamlessly synchronizes and cloud backups resume.

1. **Simulation:**
   Set `last_run_at` in `manifest.json` to 3 days ago.
2. **Execute Tick:**
   Run `python -m aryan_implementation.engine.tick --tier local`.
3. **Expected Behavior:**
   - `backup_due()` returns `True`.
   - Cloud backup executes immediately: git clone pulls state store, Railway and Vercel logs/configs are backed up to local disk.
   - All passes run in the cloud during the downtime are visible locally in `%USERPROFILE%\upwork_engine\cloud_backup\store\passes\`.
