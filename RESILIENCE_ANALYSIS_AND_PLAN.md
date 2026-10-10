# Upwork Engine: Downtime Root Cause and Three-Tier Fail-Safe Implementation Plan (v2)

Prepared 2026-10-10 from the local codebase, the local state directory, read-only Railway API queries made with the project token in `.env`, and one Upwork OAuth refresh run from this machine. Nothing was written anywhere except this file, a token backup under `C:\Users\Aryan\upwork_engine\backup`, and the IDE's own token file (updated with the rotated token so the IDE keeps working).

---

## Part A. What happened (now confirmed, not inferred)

### A1. Confirmed timeline from Railway's own logs

| When (UTC) | Fact | Source |
|---|---|---|
| 2026-10-06 14:42 | Railway service `upwork-engine` deployed with a static `UPWORK_ACCESS_TOKEN` env var, `UPWORK_ENGINE_DIR=/app/state`, no volume | Railway API: deployments list, variables (names only), `volumes: []` |
| 2026-10-07 14:22 | Last successful discovery on Railway: 20 candidates | Railway deployment log `996a3fdf` |
| **2026-10-07 14:37** | **First empty pass: 0 candidates. Every pass since then is 0.** This is 24 h 00 min after the token was injected. Upwork access tokens live exactly 86 400 s (verified today by refreshing one). | Railway deployment logs `996a3fdf` and `738d15ca` |
| 2026-10-07 14:37 → 2026-10-10 01:52 | 199 consecutive passes, 0 candidates, 0 new, 0 staged; **zero WARNING or ERROR lines in the entire log**; Telegram and Notion syncs reported success every time | Railway deployment log `738d15ca` |
| 2026-10-08 00:13 | Last deployment (`738d15ca`, still live). The Oct 10 commits (`5b2ccea`, `7ca695f`, `c50fd3f`, the "web dashboard on Railway") were **never deployed**; deployments are manual `railway up`, not GitHub-linked | Railway API: deployments carry no commit hash |
| 2026-10-06 23:39 | Last pass of the local Windows task, removed 2026-10-07 05:15 IST | local `state.json`, dev log; task confirmed absent |
| 2026-10-10 01:13 | Local daily report says "Downtime 3.1 days, last scan 2026-10-06 23:39" | computed from local state only |

**So the engine has been blind for about 2.5 days, exactly as you said.** Railway was "up" (health check green, 96 passes a day, startup message sent) while every Upwork call failed with 401. The local report noticed a different thing (the local runner you had switched off), which happened to coincide.

### A2. Root cause chain (code references)

1. `mcp_client.py:100` reads `UPWORK_ACCESS_TOKEN` from the environment and never refreshes it. Verified today: access tokens expire after 24 h and **refresh tokens rotate** (each refresh returns a new refresh token and invalidates the old one).
2. `logger.py:220` classifies the 401 as `auth` and returns `{"ok": False}`; `hunt.py:89` only checks `ok` and moves on. The failure is written to `runs.jsonl` inside the container (ephemeral) and appended to `state["incidents"]`, never logged to stdout, never alerted.
3. `hourly_runner.py:203` stamps `last_hunt_pass_at` after every pass regardless of outcome, so `web_report.py:151` and the Telegram daily report say "Hunter Online".
4. `state_manager.add_incident` (the function that trips the kill switch after 3 incidents) is never called by runtime code. Nothing stops a blind loop, and nothing tells you.

### A3. Other Railway facts that change the plan

- **No public domain** on the service (`serviceDomains: []`, no `RAILWAY_PUBLIC_DOMAIN` variable). The "Open Web Dashboard" button in Telegram points to `http://localhost:8080/report`.
- **No volume.** `/app/state` is wiped on each deploy (12 deploys on Oct 6 alone). Ledger, blacklist and `last_daily_report_date` reset each time.
- Restart policy `ON_FAILURE`, max 10 retries; no replicas; no sleep.
- Railway log API works with the project token (`deploymentLogs`, up to 5000 lines per call, date filters available). This is what makes the local backup idea in Part E feasible.

### A4. Findings that corrupt your evidence (fix in Phase 0)

- The test suite writes to the real `runs.jsonl` (`log_event` defaults to `RUNS_LOG_PATH`) and overwrote the committed `daily_report.md` with fixture data (`sample_job_2`, score 95, in commit `c50fd3f`).
- `state["incidents"]` grows without bound (47 identical entries locally).
- `jobs.json` holds the full Upwork payload per job (~11 KB each); it cannot be the thing that gets synchronised every 15 minutes.

---

## Part B. Decisions (your answers, with the reasoning applied)

| Question | Decision | Why |
|---|---|---|
| 1. Shared store | **Private GitHub repository as the store** (Contents API over plain `urllib`, token already in `.env`). Supabase kept as a documented alternative. | $0 forever, no new account, no "paused after 7 idle days" risk that the Supabase free tier carries (a paused store during an outage would block failover), every write is a commit so you get history, audit trail and off-site backup for free, and a `git clone` of it on this PC *is* the local backup required by the new rule in Part E. Compare-and-swap comes from the file `sha`. Limits (1 MB per file, ~5 000 requests/h) are handled by the layout in B3. |
| 2. Vercel Hobby | Vercel stays, but its 15-minute tick is triggered **externally by cron-job.org** (free, independent of all three tiers), with Railway and the local tier also pinging it as secondary triggers. Vercel Cron itself is only used for the once-a-day proof-of-life. | Hobby Cron allows one run per day. cron-job.org costs nothing, runs every 15 min, and emails you if the endpoint fails (a free extra monitor). Putting the trigger on Railway alone would defeat the purpose (Railway down = Vercel never wakes). Vercel usage: ~96 short invocations a day, far inside Hobby's free compute. |
| 3. healthchecks.io | **In.** | It is a free "dead man's switch": the engine pings a private URL after every healthy pass; if the pings stop for 30 minutes, the service emails you (and can post to Telegram). It is the one alert that still works when all three tiers and the store are down together, and it is one `urllib` GET. |
| 4. Railway volume | **Yes, 1 GB mounted at `/app/state`.** Verified: none exists today. | Railway volumes are billed per GB-month at a few cents; 1 GB is more than enough for the cache and raw logs. It keeps the ledger across deploys and lets Railway keep working from cache if GitHub is unreachable. Verify the current price in the Railway dashboard when creating it. |
| 5. Token refresh | Done once, safely: token file backed up to `upwork_engine\backup\mcp_oauth_tokens.before_refresh.20261010T020247Z.json`, refresh succeeded (HTTP 200), new token verified with a read-only `list_accounts` (returns Aryan Pegwar), IDE file updated. | Results: `expires_in = 86400`, **refresh token rotates**, no client secret (public PKCE client), token endpoint `https://www.upwork.com/api/v3/oauth2/token`. Consequences in B4. |

**Monthly cost of the whole design: $0 beyond what you already pay Railway, plus a few cents for the 1 GB volume.** No Supabase, no Vercel Pro, no paid monitors.

### B1. Principles

| # | Principle | Fixes |
|---|---|---|
| P1 | One shared source of truth outside all tiers; local files are caches | A1 split-brain, A3 state wipes |
| P2 | Exactly one active hunter, chosen by a lease with priority Railway → Vercel → Local; everyone else is a watchdog | duplicate cards and drafts |
| P3 | Heartbeat = proof of work (`auth_ok` and at least one search returned), never "the loop ticked" | A2.3 |
| P4 | The watcher is never the watched; plus one external dead-man's switch | A2.4, silence |
| P5 | Credentials refresh themselves; one owner of the refresh chain | A2.1 |
| P6 | Every abort path alerts, deduplicated; a daily proof-of-life is sent even when nothing happened | silence |
| P7 | Same commit on every tier, identified by `ENGINE_TIER`; capabilities declared per tier | Vercel read-only FS |
| P8 | Everything the cloud produces (state, structured logs, raw platform logs, config) has a local copy on this PC, refreshed at start-up and every 6 hours (Part E) | your new requirement |

### B2. Tier roles

| Capability | Railway (1) | Vercel (2) | Local PC (3) |
|---|---|---|---|
| Hunt pass every 15 min | in-process loop | `/api/tick`, time-budgeted, triggered by cron-job.org | Task Scheduler at logon/unlock and every 15 min |
| Watchdog of other tiers | yes | yes | yes |
| Telegram inbound | long-polling fallback | **webhook** (primary) | polling, last resort |
| Alerts | Telegram | Telegram | Telegram + Windows toast |
| Daily report, Notion sync | lease holder | lease holder | lease holder |
| Monthly strategy engine (edits markdown) | yes | no (read-only FS) | yes |
| Dashboard | `/report` (needs a public domain, see Phase 0) | `/api/report` from the store | optional |
| Cloud backup to disk (Part E) | no | no | **yes** |

### B3. GitHub store layout (repo `upwork-engine-state`, private, branch `main`)

Two rules make it conflict-free and fast: **shared files that several tiers write use compare-and-swap** (write with the current `sha`, retry on 409); **append-only data is written to per-tier files**, so tiers never collide.

| Path | Writer | Size | Notes |
|---|---|---|---|
| `state.json` | lease holder | < 20 KB | mirror of today's `state.json`, incidents capped at 50, plus `last_success_at`, `inbound_mode` |
| `lease.json` | any tier, CAS | tiny | `{holder, acquired_at, expires_at, run_id}`; acquiring is a CAS write, so two tiers can never both win |
| `heartbeats/<tier>.json` | each tier | tiny | `{seen_at, commit_sha, ok, detail}`; no CAS needed |
| `jobs/<YYYY-MM>.json` | lease holder, CAS | ~17 KB/day | compact rows only: id, status, decision, score, campaign, title, url, timestamps, `alerted_at`, draft; **no raw payload** |
| `jobs/rejected.json` | lease holder, CAS | ids only | the permanent blacklist |
| `jobs/open.json` | lease holder, CAS | small | non-terminal jobs (drafted, in_review) so any tier can answer a Telegram button |
| `passes/<tier>/<date>.jsonl` | each tier | small | proof-of-work records: `auth_ok, searches_ok, searches_failed, candidates, new, staged, error_classes, duration` |
| `alerts.json` | any tier, CAS | small | dedupe and resend state |
| `secrets/upwork_oauth.json` | lease holder, CAS | tiny | `{access_token, refresh_token, expiry, token_url, client_id, updated_by}` (see B4 for the risk note) |
| `documents/*.md` | lease holder | < 1 MB | `daily_report.md`, `market_intelligence_digest.md`, `UPWORK_PROPOSAL_CRAFTING_GUIDE.md` |
| `logs/<tier>/<date>.jsonl.gz` | each tier, nightly | ~1-3 MB | the tier's full `runs.jsonl` for that day, uploaded with the Git blob API (Contents API caps at 1 MB) |
| `payloads/<YYYY-MM>/<job_id>.json` | lease holder | 11 KB each | raw Upwork detail, written once, never read by ticks |

Throughput: a hunting tick makes about 10 API calls (~5 s); a watchdog-only tick makes 3. With three tiers that is under 1 500 calls a day against a 5 000-per-hour limit. Expect roughly 300 commits a day; rotate to a new repo yearly.

Secret-at-rest note: the Upwork token lives in a private repo reachable only with a fine-grained PAT scoped to that one repository (contents read/write only). The exposure window is short by nature (access token 24 h, refresh token invalidated on every refresh). If you want it stronger later, encrypt that one file with a key shared through each tier's env vars; it is a contained change.

### B4. Upwork OAuth lifecycle (based on today's verified behaviour)

- Access token: 24 h. Refresh token: single-use, rotating. Public client (no secret). Endpoint `https://www.upwork.com/api/v3/oauth2/token`.
- Because the refresh token rotates, **two parties cannot share one chain**: whoever refreshes second gets `invalid_grant`. Today the engine (on Railway) and your IDE share one chain, and the IDE refreshes whenever you use the Upwork MCP there. That will break the engine again.
- Design: the engine owns its own chain in `secrets/upwork_oauth.json`. Only the hunter-lease holder refreshes, and it refreshes early (when the token is older than 12 h, not when it is about to expire), so a missed tick never leaves it expired. Refresh result is written with CAS; a 409 means another tier just refreshed, so re-read and use that one.
- Getting the engine its own chain: do a one-time authorization-code + PKCE login with the same `client_id` from a local script (`scripts/upwork_login.py`), redirecting to the same local port the IDE registered, and store the result in the store. If Upwork only permits one live refresh token per client and user, fall back to a shared chain with this rule: the local tier, on every tick, compares the IDE file and the store, pushes the newer one to the other side, and the IDE file always ends up holding the latest rotated refresh token (exactly what today's script did). Which case applies is the first task of Phase 0.
- Recovery when the chain is dead: W2 alert names the fix ("run `python -m aryan_implementation.engine.cli upwork-login`"); the local tier re-seeds from the IDE file if that file is newer.

### B5. Code to add or change (all under `aryan_implementation/engine/` unless noted)

| File | Purpose | Key functions |
|---|---|---|
| `tier.py` | tier identity, priorities, capabilities, commit sha | `current_tier()`, `PRIORITY`, `can(tier, capability)` |
| `state_backend.py` | pluggable store | `StateBackend` (abstract), `FileBackend` (offline/tests), `GitHubBackend` (Contents + Git blob API, CAS retry ×3, 10 s timeouts, no SDK) |
| `state_manager.py` (modify) | keep API; add `pull()`/`push()`; immediate per-job upsert on `save_jobs` for changed rows; conflict rule: newest `updated_at` wins, status may only move forward (`discovered < scored < drafted < in_review < submitted`; rejected states terminal) | |
| `job_ledger.py` (modify) | read/write `jobs/*.json` and `jobs/rejected.json` through the backend; same public API | |
| `lease.py` | 20-minute lease, CAS acquire, renew at pass end, **yield** (do not renew) when a higher-priority tier has a heartbeat fresher than 20 min; no mid-pass preemption | `try_acquire`, `renew_or_yield`, `force_release` (CLI) |
| `watchdog.py` | evaluate conditions W1-W9 from the store | `evaluate(now)` |
| `alerts.py` | deduplicated alerts with resend interval and "resolved" messages; channels Telegram, Windows toast, healthchecks ping; never raises | `raise_alert`, `resolve_alert`, `dead_man_ping` |
| `upwork_oauth.py` | token provider per B4 | `get_valid_access_token(lease_held)`, `refresh()`, `reseed_from_ide_file()`, `login_pkce()` |
| `mcp_client.py` (modify) | take a token provider; on 401 refresh once (if lease held) then set `auth_failed`; reset session id on 4xx | |
| `hunt.py`, `hourly_runner.py` (modify) | count `searches_ok/failed`, `auth_ok`; stamp `last_success_at` only on healthy passes; `time_budget_s`; alerts on kill-switch abort, auth failure, exception; stop issuing searches at 80 % of budget | |
| `logger.py` (modify) | `log_path` always comes from the `StateManager`; cap incidents at 50; log `auth` and `rate_limit` classes at WARNING to stdout so platform logs show them | |
| `tick.py` | **the single entrypoint for all tiers** (B6) | `run_tick(tier)`; CLI `python -m aryan_implementation.engine.tick --tier local` |
| `daily_report.py`, `web_report.py` (modify) | read from the store; health from `last_success_at`; repo-directory writes opt-in; dashboard link from `PUBLIC_DASHBOARD_URL` (Vercel) with Railway as second link | |
| `telegram_bot.py` (modify) | jobs loaded from the store; polling only when `inbound_mode == polling:<this tier>`; 409 Conflict → WARNING + alert; `send_interactive_proposal` sets `alerted_at` via CAS so one card per job ever | |
| `telegram_notifier.py`, `notifier.py` (modify) | never write `.env` on cloud tiers; toast only on local | |
| `cloud_backup.py` (new, local tier only) | Part E | `run_backup(providers)`, `backup_due()` |
| `service.py` (modify) | Railway: hunter thread calls `run_tick("railway")`; supervisor thread exits the process (`os._exit(1)`) if a tick has not finished in 2 × interval, so `ALWAYS` restart policy restarts it; `/health` returns 503 with reasons; startup message once per container start with tier, commit, token age, lease | |
| `api/tick.py`, `api/telegram.py`, `api/health.py`, `api/report.py`, `vercel.json` (repo root) | Vercel tier (Phase 3) | secret header on `/api/tick`; secret path segment on the webhook |
| `scripts/register_local_tier.ps1` | replaces `register_hourly_task.ps1`: at logon, on unlock, every 15 min, 10-min limit | |
| `scripts/github_store_init.py` | creates the repo layout and validates the PAT scope | |
| `scripts/migrate_state_to_store.py` | one-off: Railway container state (via Railway API `/app/state` is not readable, so use the volume after Phase 0 or accept Oct 7-10 as lost) + local history → store | |
| `scripts/drills.md`, `RUNBOOK.md` | Part F | |
| `aryan_implementation/tests/conftest.py` | `UPWORK_TEST_MODE=1`, temp `UPWORK_ENGINE_DIR`, `FileBackend` for every test | |

### B6. The tick (identical on every tier)

```
run_tick(tier):
  heartbeat(tier)                                  # first, always
  state, jobs = pull()                             # on store failure: alert "store_unreachable"; cloud tiers stop here, local continues from cache
  conditions = watchdog.evaluate(now)
  alerts.sync(conditions)                          # raise / resend / resolve
  if backup_due() and tier == "local": cloud_backup.run_backup()   # Part E
  if not lease.try_acquire("hunter", tier): return # someone healthier owns the hunt
  token = upwork_oauth.get_valid_access_token(lease_held=True)
  result = run_single_pass(time_budget_s)
  if daily_report_due() and can(tier, "daily_report"): generate_and_notify()
  if proof_of_life_due(): send_proof_of_life()
  push(); record_pass(result)
  if result.healthy: alerts.dead_man_ping()
  lease.renew_or_yield()
```

Takeover timing: Railway dies at T; its lease expires by T+20 min; the next Vercel tick (≤15 min later) takes over, so the worst case is 35 minutes without hunting, with alert W1 raised at the same moment. When Railway returns, Vercel sees a fresher higher-priority heartbeat and yields at its next pass end.

### B7. Watchdog conditions and alerts

| Key | Condition | Severity | Resend |
|---|---|---|---|
| W1 `hunter_silent` | no healthy pass in 35 min | critical | 2 h |
| W2 `auth_failed` | last pass `auth_ok=false`, or refresh failed | critical, message includes the fix | 1 h |
| W3 `tier_missing` | Railway or Vercel heartbeat older than 1 h; local older than 48 h | warning | 12 h |
| W4 `kill_switch_active` | `state.kill_switch` | critical | 6 h |
| W5 `empty_streak` | 6 healthy passes in a row with 0 candidates (normal is ~20) | warning | 6 h |
| W6 `store_unreachable` | GitHub API failing on a tier | warning | 2 h |
| W7 `version_skew` | tiers on different commits > 1 h | info | daily |
| W8 `token_stale` | token older than 18 h and no refresh in 20 min | warning | 1 h |
| W9 `telegram_inbound_broken` | 409 on polling, or webhook errors for 10 min | warning | 1 h |
| W10 `backup_stale` (local) | last cloud backup older than 12 h while the PC has been on | warning, toast | 6 h |
| `proof_of_life` | daily 09:00 IST from the lease holder: passes per tier, failures, token age, Connects, queue, last backup time | info | daily |

Every open alert sends a "✅ resolved" message when it clears. Healthchecks.io covers the case where nothing above can run.

### B8. Telegram inbound

Webhook on Vercel is primary (serverless, always on). `inbound_mode` in `state.json` is `webhook` or `polling:<tier>`; the watchdog flips it with 30-minute hysteresis (B5 `telegram_bot.py`). Until Phase 4 ships, the lease holder polls as today.

### B9. Vercel specifics (Hobby plan)

- Trigger: cron-job.org → `POST https://<app>.vercel.app/api/tick` every 15 min with header `X-Tick-Secret`. Railway and the local tier also POST it after their own ticks. The endpoint is idempotent (lease-protected), so duplicate triggers are harmless.
- Function budget: set `maxDuration` to the Hobby maximum (verify in the dashboard; 60 s is the safe assumption) and pass `time_budget_s = 0.8 × maxDuration`. On Vercel use `max_searches=8`, `max_details=5`; the next tick continues.
- `UPWORK_ENGINE_DIR=/tmp/upwork_engine`; all repo-directory writes guarded.
- Python 3.12 on Vercel vs 3.8 locally: run the test suite once on 3.12.

---

## Part C. Step 0: restore sight before building anything (first task of the implementation, ≈15 minutes)

The engine is blind until it has a valid Upwork token. The implementation starts here, in this order:

1. Run `scripts/upwork_refresh_once.py` (already in the repo; it is the script used on 2026-10-10 02:02 UTC). It backs up the IDE token file, refreshes the Upwork token, writes the rotated token back to the IDE file, and verifies it with a read-only `list_accounts` call. Output is a fresh 24-hour access token.
2. Push that access token into Railway's `UPWORK_ACCESS_TOKEN` variable through the Railway API or CLI (project token in `.env`) and restart the service. Railway finds jobs again within one pass.
3. Repeat steps 1-2 every 24 hours by hand until Phase 0 item 1 (automatic refresh) is deployed. Phase 0 is scheduled first precisely so that this manual loop runs at most once or twice.
4. Until Phase 0 ships, do not use the Upwork MCP inside the IDE: each IDE login rotates the refresh chain and invalidates the token the engine holds. Phase 0 removes this constraint by giving the engine its own chain (B4).

---

## Part D. Phased implementation

### Phase 0: stop the bleeding on Railway + local (≈1 day, $0)

1. `upwork_oauth.py` + `mcp_client.py`: refresh chain per B4, stored for now in `ENGINE_DIR/secrets/upwork_oauth.json` (volume on Railway, file locally). First task: try `login_pkce()` to get the engine its own chain; record the outcome.
2. Proof-of-work heartbeat (`hunt.py`, `hourly_runner.py`, `web_report.py`): `searches_ok/failed`, `auth_ok`, `last_success_at`; health computed from it.
3. `alerts.py` (file-based dedupe for now): alerts on auth failure, kill-switch abort, pass exception, Telegram 409, 6-pass empty streak; daily proof-of-life at 09:00 IST; healthchecks.io ping.
4. Railway: 1 GB volume at `/app/state`; `restartPolicyType: ALWAYS`; supervisor thread; `/health` 503 on unhealthy; **generate a public domain** so the dashboard links work; set `PUBLIC_DASHBOARD_URL`; redeploy the current commit (Railway is two commits behind).
5. Test hygiene: `conftest.py`; `log_path` from `StateManager`; `DailyReportEngine` repo write opt-in; regenerate `daily_report.md` from real state or drop it from git.
6. Local watchdog (temporary): Task Scheduler every 15 min running `hourly_runner --watchdog` that reads Railway's `/api/status` and alerts + toasts if `last_success_at` > 35 min old.

Exit test: set a junk token on Railway → alert within one pass; stop Railway → local alert within 35 min of the PC being on.

### Phase 1: GitHub store, tier identity, lease, unified tick (≈2-3 days)

1. `scripts/github_store_init.py` creates `upwork-engine-state` layout; fine-grained PAT scoped to that repo; env `STATE_REPO`, `STATE_REPO_TOKEN` on each tier.
2. `state_backend.py` (`FileBackend`, `GitHubBackend`, `FakeBackend` for tests), `tier.py`, `lease.py`, `watchdog.py`, full `alerts.py`, `tick.py`; `StateManager`/`JobLedger` on the backend with the conflict rule.
3. Switch `service.py` and the local task to `run_tick`; migrate local history into the store.
4. Nightly `logs/<tier>/<date>.jsonl.gz` upload from every tier.
5. Tests: CAS lease under simulated concurrency (two tiers tick in the same second → exactly one pass), yield to higher priority, watchdog thresholds, alert dedupe/resolve, status never regresses, offline `FileBackend` on local, 1 MB file guard.

Exit test: kill Railway → local takes the lease ≤35 min with alert; restart Railway → reclaims within two ticks, no duplicate cards.

### Phase 2: local cloud backup and the new project rule (≈1 day, Part E)

### Phase 3: Vercel tier (≈1-2 days, $0)

`api/*.py`, `vercel.json`, env vars, cron-job.org trigger, time-budgeted pass, dashboard from the store.
Exit test: Railway stopped, PC off → Vercel takes over ≤35 min, alert received, one card per staged job.

### Phase 4: Telegram inbound resilience (≈1-2 days)

Webhook on Vercel, `inbound_mode` with hysteresis, polling fallback, `alerted_at` CAS.
Exit test: Vercel down → buttons work via Railway polling within 10 min; Vercel back → webhook restored within 30 min.

### Phase 5: drills and runbook (half a day, then monthly) (Part F)

---

## Part E. Your idea: local backup of everything the cloud produces (analysis and design)

**Verdict: good, and it directly fixes the blind spot that made this incident unverifiable from your PC.** With it, today's question ("why was there downtime?") would have been answerable from `C:\Users\Aryan\upwork_engine\cloud_backup` without any API access. Two refinements make it actually reliable:

1. **Pull is not enough; the app must also push.** Platform log retention is short and plan-dependent (Vercel Hobby keeps runtime logs for about an hour; Railway's retention is limited too). A 6-hourly pull from a PC that is sometimes off will miss windows. So every tier **pushes** its own structured logs to the store (`passes/`, nightly `logs/*.jsonl.gz`, error events) on every tick, and the local backup pulls the store (complete, gap-free) plus the raw platform logs (best effort, cursor-based so nothing already fetched is fetched twice).
2. **Backup config, not just logs.** A disaster-recovery copy of each service's settings (variable names, start command, restart policy, domains, cron schedules) lets you recreate a service in minutes. Secret values are never written to disk unencrypted; names and hashes only.

### E1. What gets backed up, from where, to where

| Provider | Data | Method | Destination (`ENGINE_DIR/cloud_backup/`) |
|---|---|---|---|
| GitHub store | full state history | `git clone`/`git pull` (contains state, jobs, passes, alerts, documents, logs from all tiers) | `store/` (a real git clone; history included) |
| Railway | deployment list, service settings, variable names | GraphQL (verified working today) | `railway/service.json` (overwritten each run, previous kept as `.prev`) |
| Railway | runtime logs per deployment | `deploymentLogs` with `startDate` cursor, 5000 lines per page | `railway/logs/<deployment_id>/<date>.jsonl` (append-only) |
| Vercel | deployment list, project settings, cron config | REST with `VERCEL_PERSONAL_ACCESS_TOKEN` (already in `.env`) | `vercel/project.json` |
| Vercel | runtime logs | REST runtime-logs endpoint, best effort (short retention) | `vercel/logs/<deployment_id>/<date>.jsonl` |
| Telegram | nothing to pull (the engine already stores what it sent) | | |
| Any future provider | must implement the `BackupProvider` interface below | | `<provider>/...` |

Each run writes `cloud_backup/manifest.json` (`last_run_at`, per-provider cursor, bytes written, errors) and a one-line entry to `cloud_backup/backup.log`. Retention on disk: raw logs kept 180 days, rotated monthly into `.zip`; the store clone is kept forever (it is small).

### E2. Scheduling: "once at start-up, then every 6 hours until shutdown"

Implemented inside the local tier's tick (no second scheduled task to maintain): `backup_due()` returns true when `manifest.last_run_at` is older than 6 h **or** the PC booted after the last run. Because the local tick fires at logon and every 15 minutes, the first tick after boot runs a backup, and then one runs every 6 hours while the machine is on. A manual `python -m aryan_implementation.engine.cli backup-cloud --now` exists for on-demand runs. W10 alerts (toast) if a backup has not succeeded in 12 h of uptime.

### E3. Code

- `engine/cloud_backup.py`: `class BackupProvider` with `name`, `snapshot_config()`, `pull_logs(cursor) -> (records, new_cursor)`; implementations `GitHubStoreProvider`, `RailwayProvider`, `VercelProvider`; `run_backup()` runs each provider in isolation (one failing never blocks the others), with per-provider timeouts.
- `engine/cli.py`: `backup-cloud [--now] [--provider railway]`, `backup-status`.
- Tests with recorded API fixtures. `scripts/railway_probe.py` (already in the repo, read-only, used for today's diagnosis) is the starting point for `RailwayProvider`; its `details` and `logs` modes already produce the deployment list and cursor-free log pulls.

### E4. The rule (proposed as development rule #3, to sit next to rule #1 "log every change in `project_development_logs.md`" and rule #2 "commit and push")

> **Rule #3, Local custody of cloud data.** Every cloud service or hosted runtime this project uses must (a) push its structured logs and state to the shared store on every run, (b) be registered as a `BackupProvider` in `cloud_backup.py` before it goes live, so its raw logs and configuration are copied to this PC at start-up and every 6 hours, (c) never require a dashboard login to answer "what did the system do at time T", and (d) have its restore path exercised in a drill. A service that cannot satisfy (a) and (b) is not added.

---

## Part F. Drills and runbook

| Drill | Expected |
|---|---|
| Junk Upwork token in the store | W2 within one tick naming the fix; lease holder refresh fails → alert; local re-seeds from the IDE file next tick |
| Stop Railway | W1 + W3 within 35 min; next tier takes the lease; proof-of-life next morning lists the takeover |
| Redeploy Railway 3× in an hour | zero duplicate cards, zero duplicate daily reports |
| Fire `/api/tick` twice within 5 s | exactly one pass record |
| Rotate the store PAT (store unreachable) | W6 from every reachable tier; local continues from cache; cloud tiers idle |
| `kill_switch = true` | W4 every 6 h until cleared |
| Block Telegram outbound | healthchecks.io email still arrives; local toast still fires |
| PC off for 3 days | on first tick after boot: backup runs, store clone catches up, nothing lost because tiers pushed to the store |

`RUNBOOK.md`: reading `heartbeats/` and `passes/`, forcing a lease release, re-seeding the Upwork token, flipping `inbound_mode`, restoring from `cloud_backup/store`, recreating a Railway service from `railway/service.json`.

---

## Part G. External accounts and settings the implementation creates (no decisions pending)

All decisions are made (Part B). These items are created during the build, in the phase that needs them, using the credentials already in `.env` where an API exists:

| Item | Created in | How |
|---|---|---|
| Fresh Upwork token on Railway | Step 0 (Part C) | `scripts/upwork_refresh_once.py` + Railway API variable upsert + restart |
| Railway 1 GB volume at `/app/state`, `ALWAYS` restart policy, public domain | Phase 0 | Railway API/CLI with the project token; price confirmed in the dashboard at creation |
| healthchecks.io check (free) | Phase 0 | sign-up with your email; the ping URL goes into `HEALTHCHECK_PING_URL` on every tier |
| Private repo `upwork-engine-state` + fine-grained PAT (contents read/write, that repo only) | Phase 1 | `scripts/github_store_init.py` with the existing GitHub token creates the repo; the scoped PAT is generated in GitHub settings and stored as `STATE_REPO_TOKEN` on each tier |
| cron-job.org job hitting `/api/tick` every 15 min (free) | Phase 3 | sign-up with your email; `TICK_SECRET` set on Vercel and in the job's header |
| Vercel project linked to this repo | Phase 3 | Vercel API with `VERCEL_PERSONAL_ACCESS_TOKEN` from `.env` |

The two sign-ups (healthchecks.io, cron-job.org) are the only steps that need you present, because they require an email confirmation. Everything else runs from the implementation session.
