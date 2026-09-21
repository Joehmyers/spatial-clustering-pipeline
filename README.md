# template-repo

A template repository structured for agent-driven development. Instructions live
in a tool-agnostic `AGENTS.md`, so it works with Claude Code, Cursor, Copilot,
Codex, Aider, and other [AGENTS.md](https://agents.md)-aware tools, not just one.
Clone, fill in the `<fill-in>` placeholders in `AGENTS.md`, and start building.

---

## Repository layout

```
my-project/
├── AGENTS.md                 # Agent context (tool-agnostic), auto-loaded every session (committed)
├── CLAUDE.md                 # Thin pointer that imports AGENTS.md for Claude Code (committed)
├── AGENTS.local.md           # Personal overrides (gitignored, never commit)
├── README.md                 # This file: human-oriented overview
├── .gitignore
├── .editorconfig             # Indentation and line endings, for every editor
├── .claude/
│   ├── settings.json         # Team permissions and hooks (committed)
│   ├── settings.local.json   # Personal overrides (gitignored)
│   ├── rules/                # Path-scoped instructions, loaded on matching files
│   │   ├── writing.md        # Orwell's rules; loads when touching any Markdown
│   │   └── testing.md        # Test-file rules; loads when touching a test
│   ├── skills/               # Workflows: auto-loaded when relevant, or run as /name
│   │   ├── research/         # /research: investigate a question against real sources
│   │   ├── spec/             # /spec: write a feature spec
│   │   ├── plan/             # /plan: write an implementation plan
│   │   └── decision/         # /decision: record an architecture decision
│   └── agents/               # Specialised subagent definitions
│       ├── researcher.md     # Investigates one question in its own context
│       └── code-reviewer.md  # Adversarial, read-only diff reviewer
├── .github/
│   ├── workflows/ci.yml      # CI: runs ops/check.sh on every pull request
│   ├── CODEOWNERS            # Who reviews what; replace the handles on clone
│   └── pull_request_template.md
├── LICENSE                   # MIT; replace with your own terms
├── docs/
│   ├── research/             # Sourced findings behind a decision (the evidence)
│   │   └── RESEARCH_TEMPLATE.md
│   ├── specs/                # Feature specs: the "what/why"
│   │   └── SPEC_TEMPLATE.md  # Copy this when writing a new spec
│   ├── plans/                # Implementation plans: the "how"
│   │   ├── PLAN_TEMPLATE.md  # Copy this when writing a new plan
│   │   └── examples/         # A filled-in plan, for reference
│   ├── decisions/            # Decision records: the durable "why"
│   │   ├── README.md         # Index table + how to write a decision
│   │   ├── template.md       # Copy this when recording a new decision
│   │   └── D-0001-use-cloudflare-r2-for-project-storage.md  # One record per decision
│   ├── diagrams/             # Architecture diagrams (Mermaid, rendered by GitHub)
│   │   └── system-diagram.md # System diagram: graph + timeline views (placeholder)
│   └── style-guide.md        # THE writing standard: plain English, Orwell's rules, defined terms
├── wrangler.jsonc            # Cloudflare wrangler config: R2 bucket binding (bucket = repo name)
├── src/                      # Product source code
├── tests/                    # Test suite
│   └── fixtures/             # Files tests read as input or compare against (README inside)
└── ops/                      # Verification, infrastructure, deployment
    ├── check.sh              # THE verification command: lint, tests, build
    ├── setup.sh              # Install dependencies (runs on session start)
    ├── lib.sh                # Shared helpers for the scripts below
    ├── create-bucket.sh      # Create the project's R2 bucket via wrangler
    ├── fetch-data.sh         # Sync R2 bucket data into ./data (S3-compatible)
    └── push-assets.sh        # Push ./assets up to R2 (runs after each turn)
```

---

## Getting started

1. **Clone** this template and rename the project.
2. **Fill in the two ops scripts**: the configuration block at the top of
   `ops/check.sh` (lint, test, build) and `ops/setup.sh` (install). Everything
   else reads from these: agents, humans, and CI all run `ops/check.sh`, so
   there is one answer to "is this repo green?" instead of three.
3. **Edit `AGENTS.md`**: fill in the remaining `<fill-in>` sections (how to run
   the project locally, code style). `CLAUDE.md` just imports it, so there is
   nothing to edit there.
4. **Add your source code** to `src/`, tests to `tests/`, and the files those
   tests read to `tests/fixtures/`.
5. **Cloud storage (optional)**: storage is assumed to be [Cloudflare R2](https://developers.cloudflare.com/r2/),
   and the bucket is named after the repository
   ([D-0001](docs/decisions/D-0001-use-cloudflare-r2-for-project-storage.md)).
   - **Create the bucket** with [wrangler](https://developers.cloudflare.com/workers/wrangler/):
     run `wrangler login`, then `ops/create-bucket.sh` (creates a bucket named after the repo).
     The R2 binding is pre-wired in `wrangler.jsonc`.
   - **Fetch data**: copy `.env.example` to `.env`, fill in your Cloudflare R2
     credentials, and run `ops/fetch-data.sh` to sync the bucket into `./data/` (gitignored).
   - Anything created in `./assets/` (gitignored) is pushed back to the bucket automatically
     at the end of each Claude Code turn, so created assets are accessible from anywhere
     (manual push: `ops/push-assets.sh`).
6. **Start your agent** (e.g. `claude` from the project root); it loads `AGENTS.md` automatically.

---

## One verification command

```bash
ops/check.sh          # lint, tests, build; skips whatever you haven't configured
ops/check.sh --strict # also fails on steps that are still unconfigured
```

An agent is only as reliable as the check it can run to prove its work. This repo
gives it exactly one: `ops/check.sh`. `AGENTS.md` tells agents to run it before
pushing, `.github/workflows/ci.yml` runs the same script on every pull request,
and you run it by hand. Nothing can pass locally and fail in CI because of a
command someone forgot to keep in sync.

It works before you configure anything: the shell scripts in `ops/` are syntax-
checked and, if [shellcheck](https://www.shellcheck.net/) is installed, linted.
Unconfigured steps report `SKIP` rather than pretending to pass.

`ops/setup.sh` is the matching install step. A `SessionStart` hook runs it
automatically, so a cloud or web agent session starts with dependencies present
instead of guessing whether its change works.

---

## One writing standard

Everything written in this repo (docs, specs, plans, decision records, commit
messages, PR descriptions, code comments, identifiers, error messages) follows
**[`docs/style-guide.md`](docs/style-guide.md)**: plain English, Orwell's rules,
active voice, every term of art defined on first use.

The test for every sentence: *could a competent outsider understand it on the
first read?* If not, rewrite it. **Orwell's razor**, in one line: if a simpler
phrasing carries the same meaning, the simpler phrasing is correct.

This matters more with agents than without them. A model will happily produce
fluent, confident prose that says nothing: "implements a robust retry strategy"
instead of "retries three times, then drops the message". The style guide is
what makes the difference reviewable. Three mechanisms keep it in force:

| Where | What it does |
|-------|--------------|
| `docs/style-guide.md` | The full standard, with examples and a words-to-avoid table |
| `AGENTS.md` | Summarises Orwell's six rules for every agent, every session |
| `.claude/rules/writing.md` | Loads the rules automatically whenever Claude touches a Markdown file |

The pull request template makes it a checklist item, so nobody merges prose
nobody read.

---

## Recommended workflow (explore → plan → code → commit)

| Step | What to do |
|------|-----------|
| **Research** | `/research <question>` when the choice needs evidence, not recall |
| **Explore** | Enter plan mode (`Shift+Tab`); ask Claude to read relevant files |
| **Plan** | Use `/plan <feature>` to write an implementation plan to `docs/plans/` |
| **Implement** | Exit plan mode; Claude codes against the plan |
| **Verify** | `ops/check.sh` must pass before the change is done |
| **Commit** | Claude commits with a descriptive message and opens a PR |

For larger features, start with `/spec <feature>` to write a spec first.

> **One-sentence diff?** Skip the plan. **Touching > 4 files or unclear scope?** Write a spec.

When a change makes a significant, hard-to-reverse choice, record it in
[`docs/decisions/`](docs/decisions/) with `/decision <title>`. These decision
records give both humans and agents the durable *why* behind the code, so past
decisions aren't silently contradicted.

---

## Deep research

```bash
/research "which Postgres-backed job queue survives 10k jobs/minute?"
```

Writes cited findings to `docs/research/<topic>.md`, which then feeds `/decision`
and `/spec`. It is not a web search with better manners; four things make it
different:

- **Parallel, isolated contexts.** The question is decomposed into
  sub-questions, and a `researcher` subagent takes each one. Every subagent gets
  a full context window, so ten pages of documentation get read and returned as
  five cited lines. The raw pages never touch your conversation.
- **Primary sources, actually read.** Documentation, source code, release notes,
  issue threads: opened, not skimmed from search snippets. A snippet is a
  pointer, not evidence.
- **Disagreement survives.** When two sources conflict, both are cited and the
  conflict is reported. Averaging them into one confident sentence destroys the
  most useful finding in the document.
- **The gaps are written down.** Every findings document has a **Not
  established** and a **Not checked** section. A reader who trusts a gap they
  did not know about is worse off than one who had no research at all.

The failure mode this exists to prevent is a model answering a library-choice
question from memory, fluently and out of date. If the network is unavailable,
the skill says so and marks the document partial rather than falling back on
recall.

---

## Key files to edit first

| File | Purpose |
|------|---------|
| `ops/check.sh` | Fill in your lint, test, and build commands (the one verification entrypoint) |
| `ops/setup.sh` | Fill in your dependency install command |
| `AGENTS.md` | Fill in code style, how to run locally, gotchas (the canonical instructions) |
| `.claude/settings.json` | Permissions and hooks; the `deny` list already blocks reading secrets |
| `.github/workflows/ci.yml` | Add your language toolchain step before `ops/setup.sh` |
| `.github/CODEOWNERS` | Replace `@Joehmyers` with your own handles or teams |
| `LICENSE` | MIT by default; replace the copyright line, or the whole file |
| `docs/specs/SPEC_TEMPLATE.md` | Copy and fill for each new feature spec |
| `docs/plans/PLAN_TEMPLATE.md` | Copy and fill for each implementation plan |
| `docs/decisions/template.md` | Copy and fill to record each significant decision |

---

## Extending the agent

Everything under `.claude/` is committed, so your whole team gets the same setup.

| Add | Where | What it does |
|-----|-------|--------------|
| **Skill** | `.claude/skills/<name>/SKILL.md` | A workflow Claude loads when its `description` matches the task, or you run `/<name>`. This is where `/research`, `/spec`, `/plan`, and `/decision` live. |
| **Subagent** | `.claude/agents/<name>.md` | A specialist with its own context window and tool list, for work that would otherwise flood the main conversation: `researcher` and `code-reviewer`. |
| **Rule** | `.claude/rules/<topic>.md` | Instructions that load only when Claude touches files matching the `paths` frontmatter; keeps `AGENTS.md` short. Ships with `writing.md` (any Markdown) and `testing.md` (test files). |
| **Hook** | `.claude/settings.json` | A shell command at a lifecycle event. Unlike an instruction, a hook runs whether or not the agent decides to. |

Custom slash commands and skills are the same thing now, so this template uses
`.claude/skills/` throughout. A legacy `.claude/commands/*.md` file still works if
you have one.

---

## Resources

- [AGENTS.md](https://agents.md): the open, tool-agnostic instruction-file standard
- [Architecture Decision Records](https://adr.github.io/): the ADR/MADR pattern behind `docs/decisions/`
- [Claude Code documentation](https://docs.anthropic.com/en/docs/claude-code)
- [Claude Code best practices](https://www.anthropic.com/engineering/claude-code-best-practices)

---

## License

[MIT](LICENSE). Projects cloned from this template are yours; replace the
`LICENSE` file with whatever terms you want.