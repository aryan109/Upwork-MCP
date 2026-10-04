---
name: upwork-hunt
description: Discover new Upwork jobs for Aryan's campaigns through the official Upwork MCP server (find_jobs search / smart_search / get), deduplicate against the state store, and hand candidate jobs to the vetting step. Use at the start of every combined pass or when asked to "hunt", "find jobs", or "refresh the queue". Read-only; never applies.
---

# upwork-hunt

## Purpose
Turn the campaign definitions in `campaigns.json` into a deduplicated list of candidate jobs with enough detail for scoring. Discovery only. No drafting, no submitting, no purchases.

## Preconditions
- `list_accounts` returns Aryan's account (log the name). If it returns anyone else, stop and raise an `auth` incident.
- `state.json` loaded: `last_run_at`, `kill_switch`, `connects_balance`.
- `campaigns.json` loaded; only `active: true` campaigns run.
- Log every call with the wrapper in `08_MCP_ACQUISITION_ENGINE.md` §6 (inputs, state_before, result/error, duration).

## Procedure
1. **Lookback window:** `from_date = last_run_at − 15 min`, capped at 72 h ago. If no `last_run_at`, use 24 h.
2. **For each active campaign, in priority order** (`claude-implementation`, `mcp-integrations`, `rag-knowledge`, `ai-agents`, `n8n-automation`, `integrations-repair`, `ai-training-coaching`):
   a. For each `queries[]` item: `find_jobs` → `smart_search` with `mode="most_recent"`, `query`, `from_date`, `days_posted=1`. Record `filters_ignored` / `filters_rejected` if present.
   b. Once per day per campaign (morning pass): `smart_search` with `mode="best_match"` and the first two queries.
   c. For each `title_filters[]` item: `find_jobs` → `search` with `title:"<term>"`, `verified_payment_only=true` (search only; this param is **not** valid on `smart_search`), `days_posted=2`, `subcategory` from `campaigns.subcategories` when supported.
   d. Stop after **20 searches per pass** in total; carry remaining queries to the next pass (rotate start index in `state.json`).
3. **Dedup:** drop `job_id` already in `jobs.json` unless `status in {discovered, scored}` and `last_checked_at > 6 h` (then mark for re-fetch to refresh proposal count).
4. **List-level pre-filter (cheap D-checks from the list payload only):** drop if `applied == true`, obvious capability-gate terms in title, fixed budget < $100, hourly max < $25, or exclusion terms (cold email, deliverability, GoHighLevel, Clay, Apollo) dominate the title. Log each drop with `reasons`.
5. **Detail fetch:** `find_jobs` → `get` for the survivors, newest first, **max 25 per pass**. Store the detail fields listed in `templates/jobs.schema.json` (client_record, activityStat, screening_questions, preferred_locations, connects_cost, can_apply).
6. **Write** new/updated records with `status="discovered"`, `campaign`, `first_seen_at`, `last_checked_at`. Assign campaign by priority if several match.
7. **Return** to the caller: `{new: n, refreshed: m, pre_filtered: k, detail_fetched: j, searches_used: s, incidents: [...]}` and the list of `job_id`s ready for `upwork-vet`.

## Guardrails
- Never call `manage_proposals`, `save_job`, `boost_profile`, `update_profile` from this skill.
- If `kill_switch` is true, run discovery but add `"drafting_blocked": true` to the return.
- If any search returns a schema surprise (missing `client_record`, unknown fields), save the raw payload to `payloads/` and continue.
- Respect rate limits: back off 2/4/8/16 s on 429; abort the pass after 4 consecutive failures and raise `transient` incident.

## Output format (to chat, concise)
```
HUNT <run_id> | campaigns 7 | searches 18/20 | new 23 | refreshed 4 | pre-filtered 9 | detail 14 | incidents 0
Ready for vet: ~01abc…, ~01def…, …
Mismatches seen: none / "verified_payment_only ignored on smart_search"
```
