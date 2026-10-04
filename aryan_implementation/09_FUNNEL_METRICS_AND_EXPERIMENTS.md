# 09 — Funnel Metrics & Experiments

The reference implementation's single biggest gap: 3,767 jobs tracked, 76 applied, **zero outcome fields** (no views, replies, interviews or hires recorded). Aryan's engine records outcomes from day one and reassesses after **20–30 qualified proposals**.

## 1. Funnel definition

```
Discovered → Scored ≥70 (qualified) → Drafted → Approved by Aryan → Submitted → Viewed → Replied → Interview/call → Offer → Hired → Completed (review) → Repeat/upsell
```

| Stage | Source | Field |
|---|---|---|
| Discovered | `find_jobs` | `jobs.json` count by `first_seen_at` |
| Qualified | rubric | `decision in {APPLY, REVIEW}` |
| Drafted / Approved / Rejected | review loop | `status`, `review.outcome`, `review.reject_reason` |
| Submitted | `confirm_preview` | `submission.*` |
| Viewed / Replied / Interview | `list_freelancer_proposals get`, `get_room` | `outcome.*` `[VERIFY LIVE: which statuses the MCP returns; "viewed" may not be exposed]` |
| Offer / Hired | `list_offers`, `list_contracts` | `outcome.offer_at`, `outcome.hired_at`, `contract_value` |
| Profile views / invites | `get_freelancer_dashboard check` | `state.telemetry` daily |
| Connects | `connects_balance` + ledger | `state.connects_*` |

## 2. Metrics and starting targets (all targets are assumptions until the first 20–30 proposals are in)

| Metric | Formula | P1–P2 target | Alarm |
|---|---|---|---|
| Qualified rate | qualified / discovered | 5–10% (reference ICP rate was 2.6% with hard floors) | <2% → queries too narrow or rubric too strict; >20% → too loose |
| Draft approval rate | approved / drafted | ≥ 70% | <50% → fix prompt/rubric, read reject reasons |
| Proposals/day | submitted / working day | 3 (max 5) | <2 for 3 days → discovery/campaign issue; Connects? |
| View rate | viewed / submitted | ≥ 50% | <30% → letter openers / freshness / pile-ons |
| Reply rate | replied / submitted | ≥ 15% | <8% after 20 proposals → reposition letters, lower price band, or change clusters |
| Interview rate | interview / submitted | ≥ 8% | |
| Hire rate | hired / submitted | ≥ 4% (≈1 per 25) | <2% after 50 → gate G2 review |
| Cost per reply | Connects spent × $0.15 / replies | ≤ $25 | |
| Cost per hire | Connects × $0.15 / hires | ≤ $150 | |
| Avg contract value | sum / hires | ≥ $600 P2; ≥ $2,000 P3 | |
| Effective hourly | earned / hours logged (incl. unpaid proposal time) | ≥ $50 P2; ≥ $80 P3 | |
| Profile views / week | dashboard | up 3× from baseline (0 in last 7 days) within 30 days | |
| Invites / week | dashboard | ≥ 1 by day 30 | |
| JSS | insights page | stays 100% | any drop → stop new risky jobs; review |
| Response time | Upwork metric | < 24 h | |

## 3. Reassessment gate (after 20–30 submitted qualified proposals, ≈ day 25–35)

Compute: reply rate by score band (70–79 / 80–89 / 90+), by campaign, by letter opener type, by rung proposed (fixed Sprint vs hourly), by price band, by proposals-at-apply bucket, by client spend bucket. Decisions:
- Keep the two best campaigns at full caps; halve the Connects of any campaign with 0 replies on ≥ 8 proposals.
- Move the threshold ±5 per `06` §6.
- If fixed-price Sprint proposals reply ≥ 1.5× hourly ones, make fixed the default on all hourly posts ≤ 10 h/week (and vice versa).
- If reply rate < 8% overall: pause for 48 h; Aryan reviews 10 letters against the checklist; rewrite the opener pattern; relaunch. Do **not** raise volume to compensate.

## 4. Experiments (one at a time, 2 weeks each unless noted)

| # | Experiment | Metric | Design |
|---|---|---|---|
| E1 | Availability badge ON vs prior 4 weeks | profile views, invites/week | 4 weeks on, compare with 4-week baseline; cost = Connects/week `[VERIFY LIVE]` |
| E2 | Title primary vs Alt A | profile views, search impressions (if visible), invites | 2 weeks each; change nothing else |
| E3 | Opener: mirror-situation vs explicit-ask-first (only where both are valid) | view→reply rate | alternate by job parity |
| E4 | Fixed Sprint offer vs hourly bid on hourly posts ≤ 10 h/week | reply, hire | alternate |
| E5 | Boost (≤10 Connects) on score ≥ 85 vs none | view rate, cost per reply | alternate within the ≥85 band |
| E6 | Consultation price $75 vs $100 | consultation bookings/month | after ≥ 2 bookings at $75 |
| E7 | Letter length 120–160 vs 180–220 words | reply rate | alternate |
| E8 | Specialized profile "AI Training & Coaching" live vs not | invites from training posts | 4 weeks |

Record each experiment in `templates/weekly_funnel_review.md` with start/end, variant, n, result, decision.

## 5. Weekly review (Sunday 20:00 IST, 30 minutes)
Template: `templates/weekly_funnel_review.md`. Sections: numbers vs targets; top 3 wins; top 3 losses with reject/lost reasons; Connects ledger; incidents; experiment status; campaign changes (via `upwork-campaign-editor` Skill); next week's 3 priorities; profile/ladder changes (rate gate check).

## 6. Monthly review (day 30/60/90)
- Funnel totals, revenue, effective hourly, JSS, Top Rated status.
- Decision gates G2–G5 (`02_MASTER_IMPLEMENTATION_PLAN.md` §4).
- Case-study count and demo-video status (proof machine).
- Revedor handoff: which Upwork clients are candidates for Revedor-scale engagements; what was learned about demand.
