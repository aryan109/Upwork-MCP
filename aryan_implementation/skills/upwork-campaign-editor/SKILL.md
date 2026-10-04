---
name: upwork-campaign-editor
description: Safely edit Aryan's Upwork campaign definitions (queries, title filters, floors, caps, thresholds, active flag) and scoring weights with versioning, validation against the JSON schema, a diff shown to Aryan, and explicit confirmation before saving. Use when asked to add/pause a campaign, change queries, adjust Connects caps, or apply a rebake suggestion. Never edits at run time inside a hunt pass.
---

# upwork-campaign-editor

## Purpose
The single, audited path for changing `campaigns.json` and `scoring.json`. Everything else treats those files as read-only.

## Procedure
1. Load current files; print `version`, `updated_at`, and a one-line summary per campaign (`id`, `active`, #queries, floors, caps, threshold).
2. Take the requested change (from Aryan or a rebake suggestion). Translate into a concrete patch; **one logical change per edit** (e.g., "pause ai-training-coaching", "add query 'Claude Cowork' to claude-implementation", "raise mcp-integrations connects cap to 20", "re-weight block D").
3. Validate the patched document against `templates/campaigns.schema.json` / `templates/scoring.schema.json`: required fields, enum values, weights still sum to 100, thresholds 0–100, caps non-negative, at least one active campaign, no duplicate ids, queries ≤ 8 per campaign, title filters ≤ 3.
4. Show a unified diff and the expected effect (which recent jobs would change decision, using the last 7 days of `jobs.json` as a dry run; report counts only).
5. Ask Aryan to confirm (`apply` / `cancel`). On `apply`: bump `version` (semver patch for queries/caps, minor for thresholds/weights), set `updated_at`, write `changelog[]` entry `{at, by:"aryan", change, reason}`, save, and log an `edit` event. Keep the previous file as `campaigns.v<old>.json` in `state/backup/`.
6. Never change more than one scoring block per calendar month; refuse and explain if asked.

## Guardrails
- No edits while a hunt pass is running (check `state.run_in_progress`).
- Never set `max_drafts_per_day` total > 5 across active campaigns' effective use; warn if sum of caps > 10.
- Never remove the `claude-implementation` campaign without an explicit "yes, remove".
- Never touch `kill_switch` here (that is `upwork-state-and-debugging`).

## Output
```
CAMPAIGNS v1.3 → v1.4 | change: add query "Claude Cowork setup" to claude-implementation | reason: 3 relevant posts missed this week
--- diff ---
+ "Claude Cowork setup"
Dry run (7d): +4 discovered, +1 APPLY, 0 SKIP→APPLY flips
Apply? (apply / cancel)
```
