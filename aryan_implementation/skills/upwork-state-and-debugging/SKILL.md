---
name: upwork-state-and-debugging
description: Inspect and repair the Upwork engine's state store (jobs.json, state.json, runs.jsonl, payloads, backups), diagnose failed runs from the audit log, classify incidents (auth, rate_limit, validation, business, transient, data, tool_mismatch), verify MCP connector identity and tool count, and toggle the kill switch with Aryan's confirmation. Use when a run fails, numbers look wrong, the ledger drifts, or before a reconnect/migration.
---

# upwork-state-and-debugging

## Purpose
Operational safety net. Reads logs, explains failures, performs minimal repairs with a backup first, and never hides a problem.

## Common procedures

### A. "Why did the last run fail / do nothing?"
1. Read the last `run_id` from `state.json`; filter `runs.jsonl` by it.
2. Summarise: calls made, errors by class, `filters_rejected`/`filters_ignored`, duration, where it stopped.
3. Map to the error table in `08_MCP_ACQUISITION_ENGINE.md` §6.2 and give the fix: re-auth, wait/backoff, fix param, mark duplicate, retry, or schema change.
4. If `auth`: instruct Aryan to re-authorise the connector; verify with `list_accounts` and log the account name. The engine must only run when the account is Aryan's.

### B. Connector verification (run before day 1 and after any reconnect)
`list_accounts` → account name; `tools/list` → count and names; `get_tool_help` for `find_jobs`, `manage_proposals`, `confirm_preview`. Record `state.mcp_tool_count_observed` and any difference from the 48/51 documented set. Smoke test read-only: `find_jobs search` with one title filter; `get_profile connects_balance`; `list_freelancer_proposals list`.

### C. Ledger drift
Recompute expected balance from yesterday's telemetry and today's `submission.connects_spent` (+ credits). Compare with `get_profile connects_balance`. List today's submits with Connects; look for `submitted_manually` entries without Connects recorded; ask Aryan for any manual purchases/boosts. Record resolution in the incident.

### D. Duplicate / stuck records
- Two records with the same `job_id`: keep the one with the most advanced status; merge `draft`/`submission`; log.
- `in_review` older than 24 h: expire to `skipped (hold_expired)`.
- `drafted` with `needs_edit` > 48 h: expire to `skipped (needs_edit_expired)`.
- `submitted` with no `proposal_id`: check `list_freelancer_proposals` for a match by job; set `proposal_id` or mark `error`.

### E. Kill switch
Set `state.kill_switch=true` immediately on Aryan's instruction or when the rebake rule fires (≥ 3 unresolved incidents or any `auth`). Clear only on Aryan's explicit "clear kill switch" after incidents are marked resolved with notes.

### F. Backups and migration
Before any repair: copy the state directory to `state/backup/<timestamp>/`. SQLite migration (when `jobs.json` > 2,000 rows): create tables from `templates/jobs.schema.json`, import, verify counts and a sample of 20 records field-by-field, keep the JSON as read-only archive for 30 days.

## Guardrails
- Never delete records; mark them. Never edit `campaigns.json`/`scoring.json` (use the editor skill). Never submit, message, or purchase.
- Every repair logged as `repair` event with before/after summaries.
- Secrets never appear in logs; if a token is found in `runs.jsonl`, redact and record an incident `secret_in_log`.

## Output
```
DEBUG run 2026-10-13T13:00Z-midday | calls 31 | errors: rate_limit 2 (recovered), validation 1 (verified_payment_only on smart_search → ignored), transient 0
Cause: none fatal; 14 jobs scored, 3 drafted. Fix applied: none. Suggest: move verified_payment_only to search step (already in runbook v1.1).
Kill switch: off | incidents unresolved: 0 | connector: Aryan (tools observed 48)
```
