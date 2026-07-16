# skillgap

Fork this repo, drop in your resume and the roles you want, and get a living skill-gap report: the skills that keep appearing across your targets, the ones you're missing, and one buildable project per gap. I built it because a job search generates the same three questions over and over, and answering them by hand across ten job descriptions doesn't scale: **What keeps appearing?** (one posting demanding Kubernetes is noise, seven of ten is a signal worth two months of your time), **what am I missing?**, and **what do I build to prove it?** One-shot resume checkers compare against a single job description and stop; skillgap reads all your targets at once, ranks gaps by frequency and cost, and tracks how they change between runs.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## Key features

- **Cross-target analysis** — reads your entire `targets/` folder at once (job descriptions and, optionally, profiles of people already in the role) rather than comparing one resume against one posting.
- **Frequency + severity ranking** — surfaces the skill gap that costs you the most (appears in every senior posting, absent from your resume), not just the loudest one.
- **One scoped project per gap** — each top gap ships with a portfolio project sized weekend-to-two-weeks that reuses skills already on your resume, so the suggestion is actually buildable.
- **Model-agnostic runner** — works with an `ANTHROPIC_API_KEY` (local `.env` or GitHub Actions secret), or with no API key at all via an existing Claude Code, Codex CLI, or Gemini CLI subscription (`runner: claude` / `codex` / `gemini` in `skillgap.yml`).
- **Run-over-run tracking with anti-gaming built in** — each run diffs against the previous run's JSON and pins skill names to what was used last time, so a skill the model happens to rename between runs can't masquerade as progress in `GAP.md`.
- **Optional GitHub evidence** — add `github: your-username` to `skillgap.yml` and your public repos plus merged PRs to other people's repos count as skill evidence alongside your resume.
- **`/find-roles` helper** — if you don't want to hunt job postings by hand, running `/find-roles ai engineer, remote, new grad` in Claude Code (or pointing any agent CLI at `.claude/commands/find-roles.md`) searches the web, pulls full posting text, and writes the target files for you.

## Screenshot / Demo

<!-- VERIFY / TODO(owner): Capture a screenshot of a real, populated GAP.md rendered in GitHub's Markdown preview (the "Recurring skills" frequency table plus one full "Top gap" block with its Prove-it project), ideally from a real fork run rather than the example in this README. A second good option: a screenshot of the "skillgap" GitHub Action run in the Actions tab, showing it completing and committing an updated GAP.md — this demonstrates the automation angle at a glance. -->

Example trimmed `GAP.md`:

```markdown
## Recurring skills

| Skill              | Mentioned in | Frequency |
|---------------------|--------------|-----------|
| Python              | 5/6 targets  | 83%       |
| Prompt engineering  | 4/6 targets  | 67%       |
| Vector databases     | 3/6 targets  | 50%       |

## Top gap: Vector databases

- **Required by**: 3 of 6 target roles, including anthropic-ai-engineer.md
- **Your level**: Missing
- **Severity**: High — appears in every senior posting, absent from your resume

### Prove it
Build a small RAG service over your own notes: chunk and embed ~200 markdown files,
store them in a local vector DB (pgvector or Chroma), and serve retrieval-augmented
answers through a CLI. Weekend-to-one-week scope, uses the Python and API skills you
already have.
```

## Quick start

1. Click **Use this template** on GitHub (or clone the repo).
2. Fill in your data:
   - `me/resume.md` — paste your resume, any markdown format
   - `me/skills.yml` — optional self-declared skills and levels
   - `targets/roles/<company>-<role>.md` — one job description per file
   - `targets/people/<name>.md` — optional profiles of people already in the role

   Don't want to hunt postings by hand? Open your fork in Claude Code and run `/find-roles ai engineer, remote, new grad` — it searches the web, pulls the full posting text, and writes the files for you. Using another agent CLI? Point it at `.claude/commands/find-roles.md`; the instructions work anywhere.
3. Pick how the analysis runs:
   - **API key**: add `ANTHROPIC_API_KEY`, either in a `.env` file for local runs or as a repo secret for the GitHub Action.
   - **No API key**: logged into Claude Code, Codex CLI, or Gemini CLI? Set `runner: claude` / `codex` / `gemini` in `skillgap.yml` (or pass `--runner claude`) and skillgap runs through that subscription instead.
   - Optional: add `github: your-username` to `skillgap.yml` and your public repos, plus your merged PRs to other people's repos, count as skill evidence alongside your resume.
4. Run `npm install && node skillgap.js` locally (Node 20+), or trigger the **skillgap** Action from the Actions tab.
5. Read `GAP.md` at the repo root.

### How tracking works

Each run writes a dated report to `reports/YYYY-MM-DD.md`, stores its raw analysis as `reports/YYYY-MM-DD.json`, and rewrites `GAP.md` at the repo root. skillgap diffs the new analysis against the previous run's JSON, so `GAP.md` lists the gaps you closed and the gaps that appeared since last time. Re-run whenever `me/` or `targets/` change; the GitHub Action does this on push, or run it yourself.

## Design decisions & tradeoffs

*(My reasoning, in my own words.)*

- **A template repo you fork, not a hosted service.** I wanted your resume and target postings to stay in your own private/public repo under your control, not sent to and stored on a server I run. The tradeoff is a slightly clunkier onboarding (fork, edit files, run an Action) versus a slicker signup flow, but it means there's no third party holding your job-search data.
- **Runner-agnostic by design.** Supporting a raw API key *and* existing CLI subscriptions (Claude Code/Codex/Gemini) was more integration work than picking one, but it means you're not forced to pay for API credits if you already have a subscription that includes CLI usage.
- **Diffing against the previous run's JSON, with skill names pinned.** LLM output isn't perfectly stable between calls — the same underlying gap could get renamed slightly on a re-run. Pinning names to the prior run and diffing against stored JSON (not just re-prompting fresh each time) was a deliberate choice to make "gaps closed" in `GAP.md` mean something real, not just prompt noise.
- **Whole-`targets/`-folder analysis instead of one-posting-at-a-time.** The frequency signal (7 of 10 postings want X) is the entire value proposition over a generic resume checker; analyzing postings independently would lose that.
- **Project suggestions scoped to weekend-to-two-weeks.** I chose this range deliberately so the suggested proof-of-skill is actually achievable alongside a job search, rather than "learn Kubernetes" with no scope.

<!-- VERIFY: I haven't independently verified the per-run cost or exact model behavior across all three supported runners (Claude/Codex/Gemini) — see docs/faq.md for the owner's stated notes on cost, and treat any specific dollar figures there as the source of truth over this README. -->

## Status, roadmap & known limits

Template repository, JavaScript, Node 20+, MIT licensed. No packaged releases — it's used by forking, not installing.

**Known limits:**
- Gap analysis quality depends on the underlying model's read of your resume and job postings — it's a living report to iterate on, not a certified skills audit.
- GitHub evidence (when enabled) counts public repos and merged PRs; it doesn't currently account for private-repo contributions.
- No hosted/dashboard view — `GAP.md` in your own fork is the interface.

## More

- [FAQ](docs/faq.md): privacy, cost, running without Actions, fixing a bad analysis
- [How it works](docs/how-it-works.md): what skillgap sends to the model and how it builds the report
- [Contributing](CONTRIBUTING.md)

## License

MIT licensed. See [LICENSE](LICENSE).
