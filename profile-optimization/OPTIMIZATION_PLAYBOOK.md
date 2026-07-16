# GitHub Profile Optimization Playbook — `ikatyal2110`

**Current grade: C-. Target: A-.** The substance already exists (three genuinely strong original projects); the presentation buries it. This playbook is ordered by impact — do it top to bottom. P0 takes about an hour and fixes ~80% of the problem.

---

## The core diagnosis

A recruiter spends ~30 seconds and one click on your profile. Today those 30 seconds land on:

- No display name, no bio, no location, no links, no profile README
- **Six pinned repos that are all unmodified forks** of famous AI projects (aider, pydantic-ai, fastmcp, llm, hermes-agent, omnigent) — zero commits ahead, showing borrowed star counts. This is the single most damaging thing on the profile: it reads as prestige-borrowing, and five of the six were forked in a tight recent window, which sophisticated reviewers will notice.
- Meanwhile `openclaw-to-hermes` (13 tagged releases, 180+ tests, ADRs, strict mypy CI) sits invisible at position ~9 in the repo list.

You don't have a substance problem. You have a curation problem.

---

## P0 — Do today (~1 hour)

### 1. Unpin all six forks, pin your own work
Order matters — most visitors click only the first pin:

1. **openclaw-to-hermes** (Praxis) — your strongest artifact
2. **prod-graph-rag** — add a description first (see table below)
3. **skillgap** — fix the description; GitHub currently labels it a template repo
4. *(hold the 4th–6th slots empty until market-lens and stock-charts are cleaned up — an empty slot beats a weak pin)*

> If you have real merged PRs upstream in aider/pydantic-ai/etc., that's a *great* signal — but the way to show it is a "Contributions" line in your profile README linking to the merged PRs, never an untouched fork.

### 2. Fill in profile metadata (Settings → Profile)
- **Name:** your real, resume-matching name
- **Bio (160 chars, keyword-dense):** `AI Systems Engineer | Python · FastAPI · Neo4j · LLM agents | <City or Remote>`
- **Location, Company/status, Website** (portfolio or LinkedIn)

### 3. Create the profile README
Create a public repo named exactly **`ikatyal2110`**, and copy in the three files from [`profile-repo/`](profile-repo/) in this folder:

- `README.md` — one-screen profile README (identity line → current focus → featured-work table → contact). Search for `TODO` and fill in name/LinkedIn/site.
- `build_readme.py` + `.github/workflows/build-readme.yml` — a self-updating "Recently shipped" section, rebuilt daily by a GitHub Action from your real releases and pushes. This is your **uniqueness play**: research consistently shows technical reviewers respect *self-built automation* (the Simon Willison pattern) and discount copy-pasted stat widgets. A 60-line script you can explain in an interview beats any snake animation.

### 4. Delete the throwaways
These add zero value and dilute everything else: `git_test`, `homework1` (fork), `snipz-copy`, and whichever of `cas-app` / `cas-app-git` is the stale duplicate. Delete or make private.

---

## P1 — This week (~2–3 hours)

### 5. Repo-by-repo cleanup

| Repo | Action | Suggested description | Topics |
|---|---|---|---|
| openclaw-to-hermes | Tighten description into a portfolio blurb | `Praxis — architecture-aware migration engine between agent frameworks. Typed IR, 180+ tests, strict mypy CI.` | `llm-agents`, `code-migration`, `python`, `static-analysis` |
| prod-graph-rag | Add description + topics | `GraphRAG for Kubernetes incident reasoning — Neo4j + FastAPI with provenance-enforced retrieval and CI-gated evals.` | `graphrag`, `neo4j`, `fastapi`, `kubernetes`, `rag` |
| skillgap | Fix description; clarify template status | `Skill-gap tracker: fork it, add your resume + target roles, get a living gap report via GitHub Actions.` | `github-actions`, `career`, `llm`, `automation` |
| market-lens | Description + **add iterative commits** (it's a 1-commit dump) | `Full-stack market analysis MVP — FastAPI backend, Next.js frontend.` | `fastapi`, `nextjs`, `typescript`, `fintech` |
| stock-charts | Same — description + real commit history | `Telegram bot for technical-analysis stock charting in Python.` | `telegram-bot`, `python`, `technical-analysis` |
| personal-site | Description; link it from your bio once live | `Personal site and portfolio.` | — |
| aider, llm, sqlite-utils, fastmcp, pydantic-ai, hermes-agent, omnigent, trino, teammates | **Delete forks with no changes.** Keep only ones you're actively hacking on, and never pin them. | — | — |
| CodePath-*, codepath-prework, Codedex-Hackathon-*, headstarter-pantry-tracker | Make private or archive — coursework naming is a known recruiter red flag | — | — |

### 6. Make every kept repo pass the "one click" test
For each pinned repo's own README: what it does + why it exists in the first paragraph, tech stack, a **screenshot/GIF or live demo link**, run instructions, and honest "what's next / known limits." Add a **license** (MIT default; Praxis already has Apache-2.0) — an unlicensed public repo reads as an oversight.

### 7. Grow market-lens and stock-charts into pins 4–5
Single-commit repos read as code dumps. A week of real, well-messaged commits (`Fix race in websocket reconnect` beats `update`) makes them pin-worthy and fills your recent contribution activity honestly at the same time.

---

## P2 — Ongoing habits

- **Contribution graph:** don't game it — reviewers detect backdated/mass-commit padding and treat it as a trust violation, which is *worse* than a sparse graph. Just keep the last 1–3 months showing substantive work on real projects.
- **Real upstream contributions:** one merged PR to a project you actually use (aider, fastmcp, sqlite-utils…) is worth more than all six forks were pretending to be. Your Pull Shark / Pair Extraordinaire badges suggest you've done this before — surface it in the README.
- **Cross-link:** GitHub ↔ LinkedIn ↔ resume ↔ portfolio, same name and same story everywhere. A stack/seniority mismatch between resume and GitHub is itself a screening red flag.
- **Coherence check:** everything visible should point at one narrative — *"AI/LLM systems engineer who ships tested, production-shaped infrastructure."* Praxis, prod-graph-rag, and skillgap all already tell that story; the cleanup just lets it be heard.

## What NOT to add (research was unambiguous)

- ❌ Stacked stat widgets (github-readme-stats + streak + trophies + WakaTime together reads as "assembled a template")
- ❌ Visitor counters ("signal insecurity, not success")
- ❌ Snake animation / 3D contribution calendar as a centerpiece — recognized as 15-minute copy-paste
- ❌ Badge walls of 20 languages — 3–5 technologies you can defend in an interview
- ❌ "Passionate lifelong learner" bio filler — wastes the 160-character keyword budget
- ✅ At most **one** flourish beyond the self-updating section, if any — restraint is the differentiator in 2026

---

*Sources behind this playbook: a recruiter-style audit of the live profile, plus web research across GitHub's own docs, hiring-manager write-ups (HN threads, Ben Frederickson, dev.to recruiter posts), and the awesome-github-profile-readme ecosystem. One honest caveat from the research: plenty of hiring managers never open GitHub at all — but for early-career candidates at product-driven companies (your situation), it's checked most often, and it costs one afternoon to fix.*
