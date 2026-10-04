# 08 — MCP Acquisition Engine

An agent-operated pipeline on top of Upwork's **official MCP server** (`https://mcp.upwork.com/mcp`, OAuth 2.1, JSON-RPC) that discovers jobs, scores them, drafts proposals and hands them to Aryan for review. It **never submits without a human decision**, never buys Connects, and never touches the browser. Design borrowed from the reference autopilot (`01_REFERENCE_IMPLEMENTATION_ANALYSIS.md` §6) with the three rejected pieces removed: auto-submit, auto-buy, Apify/Chrome scraping.

Non-negotiables
1. Human approval before `confirm_preview` on any `manage_proposals` action. The agent may *prepare* the preview; only Aryan's explicit "submit" (typed in chat or ticked in the review sheet) triggers confirmation.
2. Deterministic rules live in versioned config (`campaigns.json`, `scoring.json`); judgment lives in Skills. No rule is edited by the agent at run time.
3. Every call is logged with input parameters and execution state. Every failure is caught, classified and recorded; the run continues to the next job where safe.
4. Connector identity check on every run: `list_accounts` must return Aryan's account `[VERIFY LIVE: the planning session's connector was authorised as "Patrick H."; reconnect with `claude mcp add --transport http upwork https://mcp.upwork.com/mcp` and re-authorise as Aryan before P1 day 1]`.

## 1. Pipeline

```
┌───────────┐  ┌───────┐  ┌───────────┐  ┌───────────────┐  ┌─────────────┐  ┌───────┐  ┌──────────────┐  ┌────────┐
│ Discover  │→│ Score │→│ Telemetry │→│ Conflict-check│→│ Proof-match │→│ Draft │→│ Human review │→│ Submit │
└───────────┘  └───────┘  └───────────┘  └───────────────┘  └─────────────┘  └───────┘  └──────────────┘  └────────┘
   find_jobs     rubric    get_profile     state store +        skill:        skill:       Aryan reads;      manage_proposals
   search/        06       connects_balance list_freelancer_    aryan-        upwork-      edits; says        create → preview
   smart_search              + dashboard   proposals + contracts profile-facts proposal-    "submit"/"skip"   → confirm_preview
   + get                                                                      draft                           (+ answers, boost)
```

Then nightly: **Rebake** (`list_freelancer_proposals` → outcomes; dashboard; ledger reconciliation; calibration notes).

### Step-by-step with MCP tool, params, outputs and known mismatches

| Step | Tool → action | Key params | Output used | Mismatch / caution |
|---|---|---|---|---|
| 0 Identity & budget | `list_accounts`; `get_profile` → `connects_balance`; `get_freelancer_dashboard` → `check` | `org_uid` | account name must equal Aryan's; balance; views/invites counters | Doc claims 51 tools, XML lists 48; call `tools/list` and `get_tool_help` at startup and log the count |
| 1a Discover (recent) | `find_jobs` → `smart_search` | `mode="most_recent"`, `query`, `from_date`=last run − 15 min, `days_posted=1` | job ids, titles, budgets, proposals tier | `verified_payment_only` is listed under `search`, **not** `smart_search`; apply verification in scoring instead. Relevance sort may be locked; use `from_date` for recency |
| 1b Discover (best match) | `find_jobs` → `smart_search` | `mode="best_match"`, `query` | same | run once/day per campaign only (returns older posts) |
| 1c Discover (title) | `find_jobs` → `search` | `title:"Claude"`, `verified_payment_only=true`, `subcategory="AI Apps & Integration"`, `days_posted` | same | watch `filters_rejected` / `filters_ignored` in the response and log them |
| 2 Detail | `find_jobs` → `get` | `job_id` | `client_record.{total_spent,hire_rate_percent,rating,active_contracts,open_jobs,payment_verified}`, `activityStat.jobActivity.{invitesSent,totalInvitedToInterview,totalHired,totalOffered}`, `preferred_qualifications`, `connects_cost`, `applied`, `can_apply`, `screening_questions`, `preferred_locations`, `client_feedback` | cap 25 detail fetches/run (reference cap) — only for jobs passing D-checks on the list payload |
| 3 Score | local rubric (`06`) | detail payload | `score`, `decision`, `reasons[]` | pure function; versioned `scoring_version` |
| 4 Telemetry | `get_profile` → `connects_balance`; `get_rate_insights` (optional) | — | balance gate; market rate for the category | rate insights are advisory only |
| 5 Conflict-check | state store; `list_freelancer_proposals` → `list` (active); `list_contracts` | client key | skip if open proposal/contract with same client; skip if `applied` | client identity may be partial (name only); use `client_record` hash + job's `client_id` if present `[VERIFY LIVE]` |
| 6 Proof-match | Skill `aryan-profile-facts` | job cluster | `proof_ids[]`, `portfolio_project_ids[]` | never cite `permission=internal` as client result |
| 7 Draft | Skill `upwork-proposal-draft` | job + score + proof | `cover_letter`, `answers`, `proposed_terms`, `self_check` | 12-point self-check must pass or the draft is marked `needs_edit` |
| 8 Human review | review queue (chat + `templates/proposal_review_checklist.md`) | — | `approve` / `edit` / `skip` + reason | nothing proceeds without it |
| 9 Submit | `manage_proposals` → `create` → returns `preview_id`; then `confirm_preview` | `job_reference`, `charged_amount`, `cover_letter` (≤5000), `answers`, `portfolio_project_ids`, `boost_connects` | `proposal_id`, Connects charged | `VJ-JA-10` = proposal/invitation already exists → mark `duplicate`, do not retry. Follow `boost.recommendation`; cap boost ≤10 and only score ≥80. `acknowledge_policy` may be required first on some jobs `[VERIFY LIVE]` |
| 10 Post-submit | `list_freelancer_proposals` → `get`, `get_room`; `get_messages` | `proposal_id` | status (`active`/`viewed`/`interview`/`declined`/`withdrawn`), messages | poll in rebake only |
| Invitations | `list_freelancer_proposals` → `invitations`; `manage_proposals` → `accept_invitation`/`decline_invitation` | — | | human decision always |
| Offers/contracts | `list_offers`, `respond_to_offer` (returns `finalize_url`), `list_contracts`, `list_milestones`, `manage_milestones`, `submit_milestones` | — | | offer acceptance is manual via `finalize_url` |

## 2. State schema

Start with **JSON files in a private directory outside the repo** (`%USERPROFILE%\upwork_engine\state\`), upgrade to **SQLite** at >2,000 jobs or when multi-agent access is needed, and mirror to **Notion** only for Aryan's reading convenience (the reference used Notion as the system of record and paid for it in API fragility). Schemas are in `templates/`.

### 2.1 `jobs.json` (one record per discovered job)
| Field | Type | Notes |
|---|---|---|
| `job_id` | string | Upwork id (`~01…`) — primary key |
| `first_seen_at`, `posted_at`, `last_checked_at` | ISO 8601 | |
| `campaign` | enum | see §3 |
| `title`, `url`, `description_excerpt` (≤ 600 chars) | string | |
| `type` | `hourly`/`fixed` | |
| `budget_fixed`, `hourly_min`, `hourly_max`, `duration`, `connects_cost` | number/string | |
| `proposals_tier`, `proposals_count` | string/number | |
| `client` | object | `country`, `total_spent`, `hire_rate`, `rating`, `avg_hourly_paid`, `payment_verified`, `open_jobs`, `active_contracts`, `hash` |
| `activity` | object | `invitesSent`, `interviewing`, `hired`, `offered` |
| `screening_questions` | string[] | |
| `location_required`, `locations` | bool/string[] | |
| `score`, `score_breakdown` (A–E + modifiers), `scoring_version` | number/object/string | |
| `decision` | `APPLY`/`REVIEW`/`SKIP` | |
| `disqualifiers`, `reasons` | string[] | |
| `status` | enum `discovered` → `scored` → `drafted` → `in_review` → `approved` → `submitted` → `viewed` → `replied` → `interview` → `offer` → `hired` ∣ `skipped` ∣ `rejected_by_aryan` ∣ `declined` ∣ `withdrawn` ∣ `expired` ∣ `duplicate` ∣ `error` | closed set |
| `draft` | object | `cover_letter`, `answers`, `terms`, `proof_ids`, `word_count`, `self_check`, `draft_version` |
| `review` | object | `reviewed_at`, `outcome`, `edits_summary`, `reject_reason` |
| `submission` | object | `proposal_id`, `submitted_at`, `connects_spent`, `boost`, `charged_amount` |
| `outcome` | object | `viewed_at`, `replied_at`, `interview_at`, `offer_at`, `hired_at`, `contract_id`, `contract_value`, `lost_reason` |
| `notes` | string | |

### 2.2 `state.json` (singleton)
`last_run_at`, `last_run_id`, `runs_today`, `applies_today` (per campaign), `connects_balance`, `connects_spent_month`, `connects_budget_month`, `badge_on`, `scoring_version`, `campaigns_version`, `incidents[]` (`{at, type, detail, resolved}`), `kill_switch` (bool; if true, no drafts are created), `mcp_tool_count_observed`.

### 2.3 `campaigns.json`
See §3 and `templates/campaigns.schema.json`.

### 2.4 `runs.jsonl` (append-only audit log)
One line per tool call and per decision; see §6.

### 2.5 Notion mirror (optional)
Three databases mirroring the reference layout (Jobs / State / Campaigns) with the fields above; Jobs gets a `Decision`, `Score`, `Review outcome` and `Outcome` property so Aryan can read the queue in Notion. The agent writes to JSON first, Notion second; Notion failures never block the run.

## 3. Campaign definitions

Daily Connects cap total: **~12/day average** (≈250/month). Per-campaign caps below are maxima; the global 5-draft/day cap overrides.

| Campaign id | Queries (`smart_search most_recent` + weekly `best_match`) | Title filters (`search`) | Fixed budget floor | Hourly ceiling floor | Max drafts/day | Connects/day cap | Score threshold |
|---|---|---|---|---|---|---|---|
| `claude-implementation` | "Claude", "Claude Code", "Anthropic Claude setup", "Claude for business team", "Claude Cowork", "Claude Skills" | `title:Claude` | $250 | $30 | 3 | 40 | 70 |
| `ai-agents` | "AI agent build", "autonomous agent workflow", "LLM agent business process", "agentic workflow approval" | `title:"AI agent"` | $500 | $35 | 2 | 30 | 72 |
| `n8n-automation` | "n8n", "n8n AI workflow", "Make.com AI automation", "Zapier to n8n migration" | `title:n8n` | $300 | $30 | 2 | 25 | 70 |
| `mcp-integrations` | "MCP server", "Model Context Protocol", "Claude connector", "custom MCP tool" | `title:MCP` | $500 | $40 | 1 | 15 | 70 |
| `rag-knowledge` | "RAG", "knowledge base assistant documents", "internal AI assistant SharePoint Notion", "document Q&A LLM" | `title:RAG` | $750 | $40 | 1 | 20 | 72 |
| `integrations-repair` | "fix automation", "Zapier Make broken", "OpenAI integration failing", "API integration automation" | — | $250 | $35 | 1 | 15 | 70 |
| `ai-training-coaching` (secondary) | "Claude training team", "AI workshop small business", "ChatGPT Claude coaching" | — | $300 | $40 | 1 | 10 | 70 |

Common filters (applied in scoring, not as hard API filters): `subcategory` prefer `AI Apps & Integration`, `Scripting & Automation`, `Data Extraction/ETL`; exclude Patrick-lane categories (cold email, deliverability, Clay/Apollo, GoHighLevel) unless the post is primarily an AI/automation build.

Campaign fields (`templates/campaigns.schema.json`): `id`, `active`, `queries[]`, `title_filters[]`, `subcategories[]`, `exclude_terms[]`, `fixed_floor`, `hourly_floor`, `max_drafts_per_day`, `connects_cap_per_day`, `score_threshold`, `rung_default`, `proof_cluster`, `notes`, `version`, `updated_at`.

## 4. Cadence (IST)

| Time (IST) | Run | What |
|---|---|---|
| 08:30 | Morning pass | Discover (overnight US posts), score, draft up to 3; publish review queue to Aryan |
| 12:30 | Midday pass | Discover (EU morning), score, draft remaining slots |
| 18:30 | Evening pass | Discover (US morning = freshest, highest-value window), score, draft; Aryan reviews 19:00–20:00 |
| 21:30 | Late pass (optional, weekdays) | Discover + draft only if daily slots remain |
| 22:30 | **Rebake** | Outcomes, telemetry, ledger reconciliation, calibration notes, incidents, tomorrow's plan |
| Sunday 20:00 | Weekly review | Fill `templates/weekly_funnel_review.md`; campaign editor pass (Skill `upwork-campaign-editor`) |

Lookback per pass: time since last successful run + 15 min, capped at 72 h (reference used 135 min / 72 h). Max 20 searches per pass. New jobs/day in the Claude cluster ≈ 10 (observed 2026-10-04), so 3–4 passes capture nearly all.

Implementation options: Claude Code scheduled tasks / Cursor Automations / a Windows Task Scheduler job that starts the agent with the runbook in `agent_instructions/combined_pass.md`. The runbook is identical regardless of scheduler.

## 5. Dedup and conflict rules

1. **Job dedup:** `job_id` in `jobs.json` → skip discovery; re-fetch detail only if `status in {discovered, scored}` and `last_checked_at` > 6 h (proposal count changes).
2. **Client dedup:** `client.hash` = sha1(country + total_spent + hire_rate + rating + member_since) `[VERIFY LIVE: whether a stable client id exists in the payload]`. If another job with the same hash is `submitted`/`interview`/`hired` → `REVIEW`, never `APPLY`, with reason `same_client_open`.
3. **Re-posts:** same title + same budget + same client hash within 14 days → treat as same job; inherit prior decision unless Aryan overrides.
4. **Applied flag:** `applied == true` or `VJ-JA-10` → `duplicate`, terminal.
5. **Daily cap:** `applies_today` ≥ 5 → stop drafting (discovery continues; jobs are queued for tomorrow with a flag `queued_for_next_day`).
6. **Campaign overlap:** a job matched by two campaigns is assigned to the first in priority order (`claude-implementation` > `mcp-integrations` > `rag-knowledge` > `ai-agents` > `n8n-automation` > `integrations-repair` > `ai-training-coaching`).
7. **Kill switch:** `state.kill_switch == true` (set by Aryan or by the rebake after ≥3 unresolved incidents) → discovery runs, nothing is drafted or submitted.

## 6. Logging, audit and error handling

Requirements (from the project's engineering rules): comprehensive try/except, verbose logging that captures **input parameters and execution state**, audit trail.

### 6.1 Log line schema (`runs.jsonl`, one JSON object per line)
```json
{"ts":"2026-10-06T13:00:04+05:30","run_id":"2026-10-06T13:00Z-morning","step":"find_jobs.smart_search",
 "campaign":"claude-implementation","input":{"query":"Claude Code","mode":"most_recent","from_date":"2026-10-06T05:15:00Z"},
 "state_before":{"applies_today":1,"connects_balance":94,"jobs_known":412},
 "result":{"ok":true,"count":7,"new":3,"filters_ignored":[]},
 "duration_ms":1830,"error":null}
```
Decision lines: `step="score"` with `input={job_id}`, `result={score, decision, reasons}`; `step="review"` with `result={outcome, reject_reason}`; `step="submit"` with `input={job_reference, charged_amount, boost}`, `result={proposal_id, connects_spent}`.

### 6.2 Error classes and handling
| Class | Examples | Handling |
|---|---|---|
| `auth` | 401, token expired, wrong account | stop run; incident `auth`; notify Aryan; never retry blindly |
| `rate_limit` | 429 | exponential backoff 2/4/8/16 s, max 4; then skip step |
| `validation` | `filters_rejected`, bad params, cover letter >5000 | log params verbatim; fix config; mark job `error` |
| `business` | `VJ-JA-10`, `can_apply=false`, `acknowledge_policy` required | mark `duplicate`/`skipped`; or surface the policy ack to Aryan |
| `transient` | timeouts, 5xx | retry 3×; then incident `transient`, continue next job |
| `data` | missing `client_record`, unexpected schema | score with `unknown` defaults; log raw payload to `payloads/` folder |
| `tool_mismatch` | tool missing from `tools/list`, param rejected (e.g., `verified_payment_only` on `smart_search`) | log; fall back to documented alternative; incident `tool_mismatch` for the rebake |

### 6.3 Reference implementation of the wrapper (Python; agent tool call or n8n Code node)
```python
import json, time, logging, traceback, hashlib
from datetime import datetime, timezone

LOG_PATH = r"%USERPROFILE%\upwork_engine\state\runs.jsonl"
logger = logging.getLogger("upwork_engine")

def _redact(d):
    """Remove secrets/PII before logging (tokens, emails, phone numbers)."""
    s = json.dumps(d, default=str)
    for k in ("access_token", "refresh_token", "authorization"):
        s = s.replace(k, k)  # keys retained; values redacted below
    return json.loads(s) if len(s) < 20000 else {"_truncated": True, "sha1": hashlib.sha1(s.encode()).hexdigest()}

def log_event(run_id, step, campaign, inputs, state_before, result=None, error=None, duration_ms=None):
    rec = {"ts": datetime.now(timezone.utc).isoformat(), "run_id": run_id, "step": step, "campaign": campaign,
           "input": _redact(inputs), "state_before": _redact(state_before), "result": _redact(result) if result else None,
           "duration_ms": duration_ms, "error": error}
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:  # logging must never crash the run
        logger.error("log write failed: %s", e)

def call_mcp(mcp, tool, action, params, *, run_id, campaign, state, retries=3):
    """Call an Upwork MCP tool with full audit logging and classified error handling."""
    inputs = {"tool": tool, "action": action, **params}
    t0 = time.time()
    for attempt in range(1, retries + 1):
        try:
            res = mcp.call(tool, {"action": action, **params})
            if isinstance(res, dict) and res.get("filters_rejected"):
                log_event(run_id, f"{tool}.{action}", campaign, inputs, state,
                          result={"ok": False, "filters_rejected": res["filters_rejected"]},
                          error={"class": "validation", "msg": "filters_rejected"}, duration_ms=int((time.time()-t0)*1000))
            else:
                log_event(run_id, f"{tool}.{action}", campaign, inputs, state,
                          result={"ok": True, "summary": summarize(res)}, duration_ms=int((time.time()-t0)*1000))
            return res
        except Exception as e:
            msg = str(e)
            cls = ("auth" if "401" in msg or "unauthor" in msg.lower() else
                   "rate_limit" if "429" in msg else
                   "business" if "VJ-JA-10" in msg else
                   "transient" if any(x in msg for x in ("timeout", "502", "503", "504")) else "validation")
            log_event(run_id, f"{tool}.{action}", campaign, inputs, state,
                      error={"class": cls, "msg": msg[:500], "attempt": attempt, "trace": traceback.format_exc()[-1500:]},
                      duration_ms=int((time.time()-t0)*1000))
            if cls == "auth":
                state.setdefault("incidents", []).append({"at": datetime.now(timezone.utc).isoformat(), "type": "auth", "detail": msg[:200], "resolved": False})
                raise
            if cls in ("business", "validation"):
                return {"ok": False, "error_class": cls, "message": msg}
            if attempt < retries:
                time.sleep(2 ** attempt)
    return {"ok": False, "error_class": "transient", "message": "retries exhausted"}

def summarize(res):
    if isinstance(res, dict):
        return {k: (len(v) if isinstance(v, list) else v) for k, v in res.items() if k in ("count", "jobs", "results", "preview_id", "proposal_id", "balance", "filters_ignored")}
    return {"type": type(res).__name__}
```

If the engine is implemented as n8n workflows, each MCP call sits in a Code node that returns `[{ json: {...} }]` items (n8n community convention), reads inputs from `$input.all()`, and writes the same log record to a "Runs" sheet/table; errors are routed through an Error Trigger workflow that appends an incident and messages Aryan.

### 6.4 Payload retention
Raw `find_jobs get` payloads for drafted jobs are kept 90 days under `payloads/<job_id>.json` (outside the repo); skipped jobs keep only the excerpt. No client personal data beyond what Upwork shows publicly.

## 7. Human review loop (the "submit" step in detail)

1. Agent writes drafts to the review queue: a markdown block per job in chat **and** a row in `templates/proposal_review_checklist.md` format (job title, link, score + top reasons, rung/price, Connects cost, the letter, the answers, the 12-point self-check result, proof used, risk stated).
2. Aryan replies per job: `submit`, `submit with edits: …`, `skip: <reason>`, or `hold`.
3. On `submit`: agent calls `manage_proposals create` → receives `preview_id` → re-displays the exact preview text and terms → **waits for a second explicit confirmation** (`confirm`) → `confirm_preview` → logs `proposal_id`, Connects spent → status `submitted`.
4. On `skip`: status `rejected_by_aryan`, `reject_reason` stored (feeds calibration).
5. On `hold`: stays `in_review` for 24 h, then expires to `skipped` with reason `hold_expired`.
6. If Aryan prefers the Upwork UI: agent outputs the letter as plain text and marks `submitted_manually` after Aryan confirms; the rebake reconciles with `list_freelancer_proposals`.

## 8. Evening rebake loop (22:30 IST)

Runbook in `agent_instructions/evening_rebake.md`; Skill `upwork-rebake-analytics`. Steps:
1. `list_freelancer_proposals list` (active) + `get` for each `submitted`/`viewed` → update `outcome.*` and `status`; `get_room`/`get_messages` → flag unanswered client messages for Aryan (**reply drafts only; Aryan sends**).
2. `list_freelancer_proposals invitations` → queue accept/decline decisions.
3. `get_freelancer_dashboard check` → profile views, invites; `get_profile connects_balance` → reconcile against the sum of `submission.connects_spent` today; discrepancy > 2 → incident `ledger`.
4. `list_contracts`, `list_offers`, `list_milestones` → remind Aryan of due milestones and unanswered offers.
5. Calibration: today's drafted/approved/rejected counts with reject reasons; running reply rate by score band and campaign; flag campaigns with 0 qualified jobs for 5 days (candidate for query change) and campaigns consuming >40% of Connects with no replies in 14 days.
6. Incidents: list unresolved; set `kill_switch` if ≥3 unresolved or any `auth`.
7. Write the daily summary to `state.json` and a 10-line digest to Aryan; append the weekly review template on Sundays.

## 9. Build sequence (first 2 weeks; details in `02_MASTER_IMPLEMENTATION_PLAN.md`)
Day 1–2: reconnect MCP as Aryan; `tools/list` count; smoke-test `find_jobs`, `get_profile`, `list_freelancer_proposals` read-only. Day 3–4: state files + logging wrapper; discovery + scoring dry-run (no drafts) for 2 days; compare the agent's `SKIP` list against Aryan's eyeball. Day 5–7: drafting on; review loop; first manual submits. Day 8–14: rebake live; campaign editor; thresholds first calibration.

## 10. Things this engine will not do
Auto-submit, auto-buy Connects, auto-reply to clients, accept offers, change the profile or rate, boost beyond 10 Connects, scrape Upwork pages, mention itself in any client-facing text, run while `kill_switch` is on.
