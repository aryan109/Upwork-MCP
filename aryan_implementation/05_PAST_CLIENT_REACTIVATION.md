# 05 — Past-Client Reactivation (Week 1 priority)

Why first: zero Connects, warm trust, and the fastest route to a JSS-weighted job and a fresh review. Aryan has 16 distinct clients in the 24-month JSS window and a repeat enterprise client with 6+ contracts (2023–2025) `[VERIFY LIVE]`. Reactivation must be done **by Aryan in the Upwork UI** (messages in existing rooms); the agent prepares the list, the messages and the tracker, and can read rooms via `get_messages` if the connector exposes them `[VERIFY LIVE]`.

## 1. Segments

| Segment | Who (from the v2 audit; confirm on the live Contracts page) | Count `[VERIFY LIVE]` | Approach |
|---|---|---|---|
| S1 Repeat enterprise client | The Upwork enterprise client with the $7,000 (2023) build and ≥6 contracts through 2025 incl. $1,950 and $300 | 1 | Personal note from Aryan; offer an Audit or a Care Plan on the systems built; propose a 20-minute catch-up |
| S2 Idle open contracts | Finetune GPT-3 model (Jan 2023, $590) · Scraping and warehousing of Data (Apr 2023, $1,175) · AI chat-bot development (Jul 2023, $900) · AI Solutions Designer and Prompt Engineer (Aug 2023, $175) · Phase 1 of Web App Scraper (Dec 2024, $120) | 5 | "Health check + what's new" message inside the open contract; offer a small paid milestone (upgrade to Claude, fix, extend). **Do not close** these contracts for JSS reasons (opus reviewer); closing with no feedback can hurt; leave open unless the client asks |
| S3 Completed 5.0 clients, last 24 months | Everyone with a 5.0 review 2024-10 → 2026-10 | ~8 | "Here is what I've built since; one idea for you" + Sprint/Audit offer |
| S4 Older clients (> 24 months) and sub-5 clients | 2023 one-offs; the 3.8/4.2/4.3 clients | rest | Lower priority; only the 3.8 WordPress-plugin client gets a careful "lessons learned + free 20-minute call" note if Aryan judges it safe; otherwise skip |
| S5 Open invitation | 2026-08-31 "Data Science & GenAI Instructors for Live Online Training" | 1 | Reply this week: accept to interview if hourly ≥ $65 or fixed workshop ≥ $750, else decline politely |

## 2. Sequence and timing (Days 1–10)

| Day | Action | Owner |
|---|---|---|
| 1 | Export client list from Contracts page into `templates/reactivation_tracker.csv` (name/first name, contract title, dates, value, rating, segment, room link) | Aryan (agent fills what `list_contracts` returns) |
| 1 | Reply to S5 invitation | Aryan |
| 2 | S1 message | Aryan |
| 2–3 | S2 messages (5), one per contract room, personalised with the system name | Aryan |
| 4–5 | S3 messages (max 4/day to keep them personal) | Aryan |
| 8–10 | One follow-up to non-responders (S1–S3), different value (a Loom or a one-line idea) | Aryan |
| 14 | Stop; log outcomes; no third touch | — |

## 3. Message templates (Upwork message; ≤ 110 words; no links; adapt the `{{}}`)

### S1 — Repeat enterprise client
```
Hi {{FIRST_NAME}}, hope the {{SYSTEM_BUILT}} is still earning its keep. I have spent this year building Claude-based agent and automation systems (connectors to Gmail/Drive/CRM, approval workflows, run logs) and wanted to offer two things: a short health check of what we built together, and a look at where Claude could take over the manual steps around it. If useful, a fixed-price audit is $750 to $1,500 with a written roadmap, credited if we build. Open to a 20-minute catch-up next week? Aryan
```

### S2 — Idle open contract (per system)
```
Hi {{FIRST_NAME}}, this contract is still open from the {{CONTRACT_TITLE}} work in {{MONTH YEAR}}. Two quick things: is the {{SYSTEM}} still running as you need, and would it help to upgrade it to current Claude models with proper logging and an approval step? I can scope that as a small milestone here (typically $300 to $1,200 depending on changes) so nothing new needs to be set up. If it is no longer in use, say so and I will leave the contract as is. Aryan
```

### S3 — Completed 5.0 client
```
Hi {{FIRST_NAME}}, you hired me for {{CONTRACT_TITLE}} in {{YEAR}}, thank you again for the review. Since then I have moved to Claude and agent-based automation for small teams: connecting Claude to the tools people already use, with Skills that encode how the team works. One idea for {{COMPANY_OR_CONTEXT}}: {{ONE_SPECIFIC_IDEA, e.g. "a triage agent for inbound enquiries that drafts the reply and waits for approval"}}. I run that as a fixed 3-to-5-day Setup Sprint ($299 to $1,200). Worth a 15-minute look? Aryan
```

### S4 — The 3.8 client (optional; Aryan's judgement)
```
Hi {{FIRST_NAME}}, the {{PROJECT}} in 2024 did not go as smoothly as it should have, and your feedback about stating risks up front changed how I scope work: every project now starts with written acceptance criteria and a risks list before a milestone is funded. If the plugin still needs attention, I would be glad to look at it in a free 20-minute call, no strings. Aryan
```

### S5 — Invitation reply (decline variant)
```
Thank you for the invitation. My current focus is implementation work (Claude, agents, automation) rather than scheduled training delivery, so I will pass on this one. If you ever need a hands-on workshop for a team adopting Claude, I run those as fixed-price sessions and would be glad to quote. Aryan
```
(Accept variant: "Thank you; I would be glad to discuss. For live training I work at ${{RATE}}/hr or a fixed fee per workshop; could you share the schedule and group size?")

### Follow-up (one, day 8–10)
```
Hi {{FIRST_NAME}}, one more thought and then I will leave it: {{ONE_NEW_VALUE, e.g. "I recorded a 2-minute walkthrough of the approval-based triage agent; happy to send it if useful"}}. Either way, good to see {{COMPANY}} doing well. Aryan
```

## 4. Offers for reactivated clients
- Default: **Audit Focused $750** (credited against build) or **Sprint Standard $599**.
- Idle open contracts: a **new milestone** inside the existing contract (fixed) — no Connects, no new JSS job but counts toward earnings and keeps the client in the 24-month window; if the work is substantial (> $1,000), ask the client to open a **new contract** so it counts as a new job and a new review `[VERIFY LIVE: how milestones on existing fixed contracts count in JSS]`.
- Care Plan for any system still in production.

## 5. Tracker (`templates/reactivation_tracker.csv`)
Columns: `client_key, first_name, segment, contract_title, contract_type, contract_value, last_active, rating, room_link, msg1_sent_at, msg1_template, reply_at, reply_summary, followup_sent_at, outcome (no_reply|declined|call_booked|milestone|new_contract|care_plan), value_won, notes`.

## 6. Success criteria (Day 14 gate G1)
- All S1–S3 clients messaged (≤ 14 messages).
- ≥ 3 replies; ≥ 1 call booked; target ≥ 1 paid milestone or new contract ≥ $251 by day 21.
- If 0 replies by day 14: no change to the plan (it costs nothing), but note it in the weekly review and check that the messages went to the right people.

## 7. Rules
- Never bulk-send; each message names the actual system or contract.
- No "I'm available now, got any work?" messages.
- No mention of the MCP engine or of Upwork automation.
- No discounts beyond the Audit credit.
- Log every message and reply in the tracker the same day.
