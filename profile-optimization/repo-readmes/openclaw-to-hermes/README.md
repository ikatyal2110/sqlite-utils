# Praxis

> **Migrate an agent system from OpenClaw to Hermes** — workflows, plugins, prompts, memory, schedules, secrets, and the structural decisions behind them. Not a config converter; an architecture-aware translator.

Praxis exists because migrating an agent system between frameworks is normally a manual, error-prone slog: someone reads through workflows, plugins, and prompts by hand, guesses at what maps cleanly, and hopes they didn't miss a schedule or a secret. Praxis automates the part that's mechanical (scanning, classifying, emitting portable pieces) and is explicit about the part that isn't (a Markdown migration playbook listing exactly what needs human judgment). It reads your OpenClaw project, builds a typed intermediate representation (IR), and emits a Hermes project plus that playbook — **the playbook is the product**, not a side effect.

```
┌─────────────────┐    Praxis IR    ┌─────────────────┐
│  OpenClaw repo  │ ─────────────▶  │  Hermes project │
│  (workflows,    │   analyze →     │  (skills,       │
│   plugins,      │   translate →   │   schedules,    │
│   prompts, …)   │   emit          │   tools, …)     │
└─────────────────┘                 └─────────────────┘
                       +
              MIGRATION_REPORT.md
              architecture.mmd (Mermaid)
              ir.json (replayable)
```

[![CI](https://github.com/ikatyal2110/openclaw-to-hermes/actions/workflows/ci.yml/badge.svg)](https://github.com/ikatyal2110/openclaw-to-hermes/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](packages/core-py/pyproject.toml)

## Key features / architecture

- **Typed intermediate representation (IR)** — the single contract everything hangs off. It's framework-neutral in its node fields, framework-tagged in provenance, capability-based (not class-based) so translators match on what a node *can do*, and round-trippable (Hermes → IR → Hermes must converge). Versioned and schema-locked (`schemas/praxis-ir.schema.json`, frozen at `1.0`, additive-only per [ADR-0003](docs/adr/0003-v1-stability-commitment.md)).
- **Four-tier portability classifier** (`portable` / `partial` / `needs_review` / `unsupported`) stamps every node so the report tells you exactly what was auto-translated versus what needs a human call. Rule-based by design — see [Design decisions](#design-decisions--tradeoffs).
- **17-command CLI** spanning discovery (`scan`, `stats`, `doctor`), read-only analysis (`graph`, `report`, `explain`, `skills extract`, `check`, `roundtrip`), translation (`migrate`), and IR utilities (`ir validate`, `ir diff`, `ir to-mermaid`).
- **Skill/prompt consolidation** — `praxis skills extract` clusters near-duplicate prompts (Jaccard similarity on token bigrams) and detects repeated maximal tool-call sequences across workflows, surfacing candidates to merge into a single Hermes skill.
- **Six-stage pipeline** (scan → analyze → resolve → score → translate → emit), documented in [`docs/architecture.md`](docs/architecture.md).
- **180+ tests**, strict mypy in CI, two golden-file regression fixtures locking known-good migrations.

## Screenshot / Demo

<!-- VERIFY / TODO(owner): Praxis is a CLI tool, so the highest-value "demo" here is a terminal recording, not a static screenshot. Capture (asciinema or a GIF via terminalizer/vhs) the sequence: `praxis scan examples/openclaw-sample` → `praxis report examples/openclaw-sample` → `praxis migrate examples/openclaw-sample --target hermes --out ./out`, ending on the printed "Migrated → ./out" summary line and a `tree ./out` of the emitted files. Embed the GIF here, or link an asciinema recording. A second good option: a screenshot of the rendered `MIGRATION_REPORT.md` playbook (the tier table + TODO checklist) opened in GitHub's Markdown preview, since that file is the actual product. -->

## Quick start

Praxis ships as a Python package with a CLI. (A TypeScript wrapper lives in `packages/cli` and shells out — same surface area, optional.)

```bash
# Install from a clone (PyPI release coming with v1.0)
git clone https://github.com/ikatyal2110/openclaw-to-hermes
cd openclaw-to-hermes
pip install -e packages/core-py

# Sanity-check the install
praxis doctor

# Scan a project — print a summary table
praxis scan examples/openclaw-sample

# Generate a Mermaid graph of the architecture
praxis graph examples/openclaw-sample --format mermaid > arch.mmd

# Produce a Markdown migration feasibility report
praxis report examples/openclaw-sample > REPORT.md

# Materialize a Hermes project
praxis migrate examples/openclaw-sample --target hermes --out ./out

# Cluster prompts to surface candidate skills
praxis skills extract examples/openclaw-sample --report extract.md

# Inspect the IR directly
praxis scan examples/openclaw-sample --emit-ir ir.json
praxis ir validate ir.json
```

### What you get from `praxis migrate`

```
out/
├── MIGRATION_REPORT.md     ← your playbook (checklist + tier table + TODOs)
├── architecture.mmd        ← Mermaid graph (paste into mermaid.live)
├── ir.json                 ← portable IR (diff between runs, validate)
└── hermes/
    ├── skills/             ← one YAML per workflow
    ├── tools/              ← one YAML per plugin
    ├── schedules/          ← one YAML per cron trigger
    ├── memory/             ← one YAML per store
    └── prompts/            ← prompts copied verbatim
```

The CLI prints a one-line summary so you know what was emitted:

```
Migrated → ./out
  files : {'skills': 3, 'tools': 6, 'schedules': 2, 'memory': 2, 'prompts': 6}
```

### Repository layout

```
praxis/
├── schemas/praxis-ir.schema.json    # The IR — the public contract
├── docs/                            # Architecture, IR spec, ADRs, user guides
├── examples/openclaw-sample/        # A realistic fixture project
├── packages/
│   ├── core-py/                     # Python: analyzers, translators, emitters
│   ├── ir/                          # TypeScript types + zod schema for IR
│   └── cli/                         # Thin TS CLI (shells to core-py)
└── tools/fixtures/                  # Golden migration fixtures (regression tests)
```

See [`docs/architecture.md`](docs/architecture.md) for how each pipeline stage exchanges IR, and [`docs/migrating-real-projects.md`](docs/migrating-real-projects.md) for a first-day walkthrough on a real project.

## Design decisions & tradeoffs

*(In my own words — the reasoning behind the choices that shaped v1.0.)*

- **The report is the product, not the migrated code.** I deliberately don't try to make `praxis migrate` a drop-in autopilot. Roughly 30–50% of common patterns translate deterministically; for the rest, I'd rather hand you a specific, reviewable TODO than silently guess and ship something subtly wrong. A migration tool that pretends to handle every dialect of every framework lies; one that exposes its assumptions and gives you an inspectable IR is honest infrastructure.
- **Rule-based classification, not an LLM gate.** The four-tier classifier (`portable`/`partial`/`needs_review`/`unsupported`) is intentionally deterministic. An opaque LLM call deciding "is this portable?" would kill the debuggability the whole tool depends on — you can't set a breakpoint in a model's judgment. Tradeoff: the classifier needs new rules added by hand as I encounter new OpenClaw/Hermes dialects, rather than generalizing for free.
- **One source, one target per release.** v1.0 supports exactly OpenClaw → Hermes. I scoped it this narrowly on purpose — a general "any agent framework to any other" converter is a much bigger and vaguer problem, and I wanted the IR and classifier proven on one real pair before generalizing (LangGraph as a third target is planned for v1.3, explicitly framed as the first stress test of the IR's "additive-only" promise).
- **Capability-based IR, not class-based.** Translators match on what a node can *do* (has a schedule, has memory) rather than its OpenClaw type name. This is more code up front but means adding a new OpenClaw construct doesn't require touching every translator.
- **IR schema frozen, internals not.** Per [ADR-0003](docs/adr/0003-v1-stability-commitment.md), the JSON schema, CLI command names, and public Python API are stable within 1.x; specific classifier verdicts, inferred-intent prose, and generated metadata blocks are explicitly *not* — those improve as heuristics improve, and I didn't want to over-promise stability on things that are still heuristic.
- **Golden-file regression fixtures over unit tests alone.** Two full fixture projects (`tools/fixtures/`) are migrated end-to-end and diffed against known-good output on every CI run, catching regressions that unit tests on individual translators would miss.

<!-- VERIFY: I haven't run Praxis against a production OpenClaw project outside the bundled examples/fixtures — if you have, the "30–50% deterministic translation" figure and the classifier's real-world hit rate are worth re-validating and citing here with concrete numbers. -->

## Status & roadmap

**v1.0 — stable.** Production-ready CLI with 17 commands, IR schema `1.0` (stability commitment per ADR-0003), 180+ tests, strict mypy in CI, two golden-file regression fixtures.

Planned (see [`CHANGELOG.md`](CHANGELOG.md) for the full v0.1–v1.0 history):

- **v1.1** — LLM-assisted intent inference with content-addressed caching.
- **v1.2** — Hybrid bridge, read-only (Hermes introspects OpenClaw tools).
- **v1.3** — Hybrid bridge, read-write; LangGraph as a third target.
- **v1.4** — VS Code extension surfacing the migration report as inline annotations.
- **v2.0** — reserved for "the IR shape was wrong," not feature work; none currently planned.

**Known limits:** supports one source and one target framework at a time; assumes specific OpenClaw/Hermes YAML conventions (documented in [`docs/openclaw-format.md`](docs/openclaw-format.md) / [`docs/hermes-format.md`](docs/hermes-format.md) — projects with different dialects need analyzer/emitter customization); generated Hermes files are a starting point requiring human review, not production-ready output on their own.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Good first issues: extend the prompt tokenizer for Hermes placeholders, add a real-world fixture that doesn't round-trip yet, or help add LangGraph as a third target ([`docs/authoring-a-backend.md`](docs/authoring-a-backend.md)).

## License

Apache-2.0. See [`LICENSE`](LICENSE).
