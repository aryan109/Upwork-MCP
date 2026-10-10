# Upwork Engine: Operational Runbook & Incident Response Guide

This runbook covers day-to-day operations, failure recovery, fail-over verification, and disaster recovery across all three tiers (Railway, Vercel, and Local PC).

---

## 1. Quick Diagnostics & Health Checks

### Check System Status
From the local terminal:
```bash
python -m aryan_implementation.engine.cli status
```
Or check via Vercel / Railway endpoints:
- **Vercel Health:** `https://<your-vercel-app>.vercel.app/api/health`
- **Railway Health:** `https://upwork-engine-production-16dc.up.railway.app/health`
- **Live Web Dashboard:** `https://upwork-engine-production-16dc.up.railway.app/report` (or Vercel `/report`)

### Inspect Heartbeats & Passes
Heartbeats and pass records are stored continuously in the private GitHub store (`aryan109/upwork-engine-state`):
- `heartbeats/railway.json`: Railway container status, commit, and last seen timestamp.
- `heartbeats/vercel.json`: Vercel serverless execution status.
- `heartbeats/local.json`: Local PC background runner status.
- `passes/<tier>/<YYYY-MM-DD>.jsonl`: Detailed proof-of-work records (`auth_ok`, `searches_ok`, `candidates`, `duration`).

---

## 2. Managing Distributed Leases

The hunter loop is governed by distributed compare-and-swap (CAS) leases in `lease.json`.
Priority order:
1. **Railway (Priority 1)**
2. **Vercel (Priority 2)**
3. **Local PC (Priority 3)**

### Force Releasing a Stalled Lease
If a tier encounters an unhandled freeze or network partition holding the lease:
```bash
python -m aryan_implementation.engine.cli release-lease hunter
```
This forces `lease.json` to expire immediately, allowing the highest priority active tier to claim it on its next tick.

---

## 3. Upwork OAuth Token Re-seeding & Recovery

### Why Tokens Fail
Upwork tokens have a 24-hour lifetime. Refresh tokens rotate on every refresh call (single-use).

### Automatic Early Refresh
The active lease holder automatically refreshes the token when it is older than 12 hours.

### Manual Re-seeding when W2 Alerts Fire
If `W2 auth_failed` alerts occur:
1. In your local IDE / terminal, run:
```bash
python -m aryan_implementation.engine.cli upwork-login
```
2. Or sync existing IDE tokens into the state store:
```bash
python -m aryan_implementation.engine.cli reseed-token
```
3. Verify token validity:
```bash
python scripts/upwork_refresh_once.py
```

---

## 4. Switching Telegram Inbound Mode

The engine supports two inbound approval modes:
- `webhook`: Vercel serverless webhook receives 1-click approvals and commands at `/api/telegram`.
- `polling:<tier>`: A specific tier (e.g. `polling:railway` or `polling:local`) performs long polling.

### To Change Inbound Mode
Update `inbound_mode` in `state.json` via the store or StateManager:
```python
from aryan_implementation.engine.state_manager import StateManager
from aryan_implementation.engine.config import STATE_DIR

sm = StateManager(STATE_DIR)
state = sm.load_state()
state["inbound_mode"] = "webhook"  # or "polling:railway"
sm.save_state(state)
sm.push()
```

---

## 5. Cloud Backup & Disaster Recovery (Development Rule #3)

### Backup Directory
All cloud data is backed up to local custody at:
`%USERPROFILE%\upwork_engine\cloud_backup\`
- `store/`: Full git clone of state repository.
- `railway/service.json`: Current Railway configuration, restart policy, and environment variable names.
- `railway/logs/`: Raw deployment logs.
- `vercel/project.json`: Vercel project configuration.
- `manifest.json`: Cursor tracking and backup timestamps.

### Running On-Demand Backup
```bash
python -m aryan_implementation.engine.cli backup-cloud --now
```

### Checking Backup Status
```bash
python -m aryan_implementation.engine.cli backup-status
```

### Restoring Railway Service from Backup
If Railway service is accidentally deleted:
1. Read `%USERPROFILE%\upwork_engine\cloud_backup\railway\service.json`.
2. Deploy container with Dockerfile: `railway up`.
3. Re-create volume: mount 1 GB at `/app/state`.
4. Set environment variables listed in `service.json`.

---

## 6. Running a Manual Tick

To execute an immediate tick on any tier:
```bash
# Run local tick
python -m aryan_implementation.engine.tick --tier local

# Run with specific time budget (seconds)
python -m aryan_implementation.engine.tick --tier local --budget 30
```
