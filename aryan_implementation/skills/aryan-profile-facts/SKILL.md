---
name: aryan-profile-facts
description: The single source of truth for what may be claimed about Aryan in Upwork proposals, profile text, catalog listings and client messages: verified profile numbers, past contracts, proof inventory with permission levels, tools allowlist, rates and offers, voice rules and the never-claim list. Every drafting skill must load this first and must not state anything about Aryan that is not here. Aryan maintains it; placeholders in {{}} must be filled before the engine drafts.
---

# aryan-profile-facts

**Maintained by:** Aryan. **Last verified against the live profile:** 2026-10-05 (via Upwork MCP API live profile inspection). If any `{{}}` remains in §1–§4, drafting skills must refuse to draft and list the missing items.

## 1. Profile numbers (snapshot 2026-10-05; verified live via Upwork MCP)
| Fact | Value | Verified on |
|---|---|---|
| Name shown on profile | Aryan P. (Account: Aryan Pegwar) | 2026-10-05 |
| Profile URL | https://www.upwork.com/freelancers/~01c405f48e970fd854 (never pasted in letters) | 2026-10-05 |
| Badge | Top Rated | 2026-10-05 |
| Job Success Score | 100% | 2026-10-05 |
| Total earned | $20K+ | 2026-10-05 |
| Completed jobs | 38 (23 fixed, 15 hourly; 21 reviews) | 2026-10-05 |
| Hours billed | 395 | 2026-10-05 |
| Earnings last 12 months | $2,172 | 2026-10-04 |
| Hourly rate (sticker) | $65 (target per plan; currently $120 on profile) | 2026-10-05 |
| Connects balance | 110 (110 free, 30 rollover, 0 paid) | 2026-10-05 |
| Location / time zone | India (MP) / UTC+05:30 (Mumbai, New Delhi) | 2026-10-05 |
| Education | BEng Computer Engineering, RNS Institute of Technology (2017–2021); Intel Edge AI Nanodegree, Udacity (2020) | 2026-10-05 |
| Employment history start | 2020 (Machine Learning Engineer, TillyBilly; Intern, Deloitte) | 2026-10-05 |
| Company | Revedor (Revedor AI) — may be mentioned as "my company" | 2026-10-05 |
| Languages | English (Native or bilingual) | 2026-10-05 |
| Certifications | Intel® Edge AI for IoT Developers Nanodegree (Udacity, 2020) | 2026-10-05 |

## 2. Past Upwork contracts usable as proof (from the 2026-10-04 audit; confirm titles/values; set permission)
| id | Contract (as titled on Upwork) | Year | Value | Rating | Permission (`named` / `anonymised` / `do_not_use`) | One-line description Aryan approves |
|---|---|---|---|---|---|---|
| C1 | `{{Enterprise client project}}` ($7,000 fixed; same client on ≥ 6 contracts incl. $1,950, $300) | 2023–2025 | $7,000+ | `{{}}` | `{{}}` | `{{what was built, scale}}` |
| C2 | Finetune GPT-3 model | 2023 | $590 | `{{}}` | `{{}}` | `{{}}` |
| C3 | Scraping and warehousing of Data | 2023 | $1,175 | `{{}}` | `{{}}` | `{{}}` |
| C4 | AI chat-bot development | 2023 | $900 | `{{}}` | `{{}}` | `{{}}` |
| C5 | AI Solutions Designer and Prompt Engineer | 2023 | $175 | `{{}}` | `{{}}` | `{{}}` |
| C6 | Phase 1 of Web App Scraper | 2024 | $120 | `{{}}` | `{{}}` | `{{}}` |
| C7 | WordPress plugin ($4,408) | 2024 | $4,408 | 3.8 | `do_not_use` as proof; lesson: state risks up front | — |
| C8 | AutoGPT plugin | `{{}}` | $125 | 3.8 | `do_not_use` | — |
| C9 | Trading bot | `{{}}` | `{{}}` | 3.8 | `do_not_use` | — |
| C10… | `{{other 5.0 contracts in the last 24 months}}` | | | | | |

## 3. Proof inventory (what drafting skills may cite)
| id | type | one_line (measurable where true) | permission | asset (case study / video / repo / screenshot) | portfolio_project_id `[VERIFY LIVE]` |
|---|---|---|---|---|---|
| P1 | chatbot | `{{e.g. "AI chatbot for a services client over business documents, 2023, still in use"}}` | `{{}}` | `{{}}` | `{{}}` |
| P2 | agent-mcp-engine | "An agent system I run for my own company that discovers, scores and drafts with human approval, on an official MCP server, with full run logs" (internal; never framed as a client result; never say it is for Upwork in client-facing text) | internal | case study 2 + 2-min video | `{{}}` |
| P3 | scraping-warehouse | `{{"Scheduled scraping and warehousing pipeline, 2023, N records/day"}}` | `{{}}` | `{{}}` | `{{}}` |
| P4 | fine-tune | `{{"Fine-tuned GPT-3 for <task>, 2023"}}` | `{{}}` | `{{}}` | `{{}}` |
| P5 | n8n-workflow | `{{only if Aryan has shipped one; else leave out}}` | `{{}}` | `{{}}` | `{{}}` |
| P6 | enterprise-build | `{{C1 description}}` | `{{}}` | case study 3 | `{{}}` |
| P7 | audit | `{{if any review/audit work exists}}` | `{{}}` | `{{}}` | `{{}}` |
| P8 | training | `{{if any training/coaching delivered}}` | `{{}}` | `{{}}` | `{{}}` |
| P9 | repair | `{{plugin/integration fixes on existing codebases, 2024}}` | `{{}}` | `{{}}` | `{{}}` |

Client quotes usable verbatim (copied from visible reviews): `{{"quote" — first name/role, year}}` (≤ 3).

## 4. Tools allowlist (may be named as hands-on)
Claude (API, Claude Code, Cowork, Skills, MCP), OpenAI API, n8n `{{confirm}}`, Make `{{confirm}}`, Zapier `{{confirm}}`, Python, LangChain/LlamaIndex `{{confirm}}`, vector stores `{{which}}`, PostgreSQL/SQLite, Google Workspace APIs, HubSpot API `{{confirm}}`, Notion API, Slack API, Airtable `{{confirm}}`, WordPress/PHP (plugin work), web scraping (Playwright/Scrapy `{{confirm}}`), Docker `{{confirm}}`, cloud `{{AWS/GCP/Azure — which}}`.
Anything not listed → "I have not used X in production; the closest I have used is Y."

## 5. Offers and prices (must match 03/04 exactly)
Consultation $75/30 min · Setup Sprint $299/$599/$1,200 · Audit $750/$1,500 (credited against build) · Implementation $3,000–$7,500 in 3 milestones · Care Plan $1,000/$1,500/$2,500 per month · Hourly $65 (step-ups by gate).

## 6. Voice
Plain, specific, calm. Short sentences. Business nouns before technology nouns. One risk stated per letter. No adjectives about self. No exclamation marks. No em dashes. Sign "Aryan".

## 7. Never claim
"8+ years"/"over a decade" · GxP/HIPAA/SOC2 compliance or "compliant" · "enterprise-grade" · guarantees or outcome promises · certifications not in §1 · client names without `named` permission · results not in §3 · experience with tools not in §4 · that any system is "fully automated" without an approval step · anything about Upwork automation, this engine, or OpenClaw (unless the post uses it) · availability "immediately" (say "this week").

## 8. Scheduling facts
Working hours for calls: `{{e.g. 10:00–22:00 IST}}`; preferred client call windows: US morning (18:30–23:00 IST), EU afternoon (14:00–19:00 IST). Response-time commitment: within 24 h, usually same day.
