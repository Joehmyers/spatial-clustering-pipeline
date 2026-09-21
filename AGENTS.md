# AGENTS.md

Agent context for this repository. This is the canonical, tool-agnostic
instruction file, auto-loaded at the start of every agent session (Claude Code,
Cursor, Copilot, Codex, Aider, Gemini CLI, and other [AGENTS.md](https://agents.md)-aware
tools). Claude Code reads it via a one-line `@AGENTS.md` import in `CLAUDE.md`.

Keep this file under ~200 lines. Include only what an agent cannot infer from
reading the code.

---

## Commands

```bash
# Verify the repo: lint, tests, build. THE command; CI runs this exact script.
ops/check.sh

# Install dependencies (also runs automatically via SessionStart hook)
ops/setup.sh

# Run locally
<fill-in>

# Create the project's Cloudflare R2 bucket (wrangler; bucket = repo name)
ops/create-bucket.sh [bucket-name]

# Fetch project data from Cloudflare R2 into ./data (config via .env; see .env.example)
ops/fetch-data.sh [prefix]

# Push created assets from ./assets to Cloudflare R2 (runs automatically via Stop hook)
ops/push-assets.sh [prefix]
```

`ops/check.sh` and `ops/setup.sh` each hold a short configuration block at the
top; fill in your project's lint, test, build, and install commands there. Put
them in the script, not in this file: one place that agents, humans, and CI all
read means the answer to "is this green?" cannot drift between them.

---

## Architecture

- `src/`: product source code
- `tests/`: test suite (the agent's verification target)
- `tests/fixtures/`: files tests read as input or compare output against;
  its README has the size and naming rules
- `docs/research/`: sourced findings behind a decision (the evidence)
- `docs/specs/`: feature specs (what/why)
- `docs/plans/`: implementation plans (how/steps)
- `docs/decisions/`: decision records (the durable *why*)
- `docs/diagrams/`: architecture diagrams (`system-diagram.md`: Mermaid graph + timeline views)
- `ops/`: infrastructure, verification, and deployment scripts
- `.claude/`: Claude Code configuration (committed to git): `skills/` (workflows,
  also usable as `/name`), `agents/` (subagents), `rules/` (path-scoped instructions),
  `settings.json` (permissions and hooks)
- `.github/`: CI workflow and pull request template

---

## Code style

<fill-in>

---

## Writing style

**All prose in this repo follows [`docs/style-guide.md`](docs/style-guide.md)**:
docs, specs, plans, decision records, commit messages, PR descriptions, code
comments, identifiers, and error messages. Read it before writing anything longer than a
sentence.

The test for every sentence: could a competent outsider understand it on the
first read? If not, rewrite it. Orwell's six rules, in short:

1. No stale metaphor or figure of speech you are used to seeing in print.
2. Never a long word where a short one will do (*utilize* → use).
3. If you can cut a word, cut it ("in order to" → "to").
4. Never the passive where the active works; passive hides who does what.
5. No jargon where everyday English exists; define the terms of art you keep.
6. Break any of these sooner than say anything outright barbarous.

**Orwell's razor:** if a simpler phrasing carries the same meaning, the simpler
phrasing is correct.

Also: define every term of art on first use, use one name per concept, prefer
numbers to adjectives ("cuts p95 from 800 ms to 120 ms", not "significantly
faster"), spell in British English, and never use an em dash (—); use a comma, a colon, parentheses, or
two sentences instead.

The same rules live in `.claude/rules/writing.md`, which Claude Code loads when
you touch a Markdown file. They are repeated here so tools without path-scoped
rules still see them, and because they apply to prose that is not a file at
all: commit messages, PR descriptions, error strings.

---

## Testing

`tests/` is the agent's verification target. `ops/check.sh` is how you run it.

- NEVER modify a test to make it pass; fix the implementation instead.
- NEVER mock a module that exists in this repo; test it directly.
- Every test asserts a concrete outcome. A test that cannot fail is not a test.
- Write the test before the implementation when the file does not exist yet.
- Run `ops/check.sh` after every implementation change to catch regressions.

The same rules live in `.claude/rules/testing.md`, which Claude Code loads only
when you touch a test file. They are repeated here so tools without path-scoped
rules still see them.

---

## Repo etiquette

- Branch naming: `<your-username>/<short-description>` (e.g., `alice/add-login`)
- Commit style: imperative mood, present tense (`add feature`, not `added feature`)
- Open a PR for every change, even solo work; it creates a review artifact
- YOU MUST run `ops/check.sh` and see it pass before pushing
- NEVER commit `.env`, secrets, or generated build artifacts

---

## Decisions

`docs/decisions/` holds the project's **decision records**: short, immutable
Markdown files, numbered `D-0001` and up, that record *why* a significant,
hard-to-reverse choice was made. They are the historical "why"; this file is the
active "what". `docs/decisions/README.md` owns the format and workflow; the
rules below are repeated here so agents see them without opening it.

- **Before proposing an architectural change, consult `docs/decisions/README.md`
  and read any relevant record.** Do not contradict an `accepted` decision.
- If a decision genuinely needs to change, ask a human first, then write a
  **new** record that supersedes the old one (copy `docs/decisions/template.md`).
  Never rewrite an accepted record.
- Log only **architecturally significant** decisions (costly to change; would
  need coordination, migration, or risk management to reverse). Skip trivial,
  easily-reversed choices a linter or convention already covers.

---

## Architecture decisions in force

Each line is the rule; the linked record carries the reasoning. Read it before
proposing a change to any of these.

- **Cloud storage is Cloudflare R2**, bucket named after the repository (override
  with `R2_BUCKET`). Lifecycle via wrangler, bulk transfer via the S3-compatible
  API. See [D-0001](docs/decisions/D-0001-use-cloudflare-r2-for-project-storage.md).

---

## Environment / gotchas

- Put created assets (generated files meant to outlive this machine) in `./assets/` (gitignored).
  A `Stop` hook in `.claude/settings.json` uploads them to Cloudflare R2 after each agent turn,
  so they are accessible from anywhere; retrieve them with `ops/fetch-data.sh assets`.
  Without R2 credentials in `.env` the hook is a silent no-op, so a fresh clone needs no configuration.
  Symlinks and secret-looking files (`.env*`, `*.pem`, `*.key`, `id_rsa*`, `secrets/`) are never uploaded.
- Reading `.env` (and its variants), `*.pem`, `*.key`, `id_rsa*` and `secrets/`
  is blocked by deny rules in `.claude/settings.json`; `.env.example` stays
  readable on purpose. That is enforcement, not advice; do not work around it.
  If a task genuinely needs a secret, ask for it.

---

## Planning workflow

For any change touching more than one file:
1. **Explore**: read relevant files in plan mode (no edits)
2. **Plan**: write a plan to `docs/plans/<feature>.md` (`/plan <feature>`)
3. **Implement**: code against the plan, run `ops/check.sh` after each step
4. **Commit**: descriptive commit message, reference the plan file

For larger features, start with a spec in `docs/specs/<feature>/spec.md` first
(`/spec <feature>`). One-sentence diff? Skip the plan.

When the choice needs evidence rather than recall (which library, which
protocol, what the prior art is), run `/research <question>` first. It fans out
subagents over real sources and writes cited findings to `docs/research/`.

When a change makes an architecturally significant decision, record it in
`docs/decisions/` (`/decision <title>`). Cite the research document in it.

`docs/plans/examples/` holds a filled-in plan from this template's own history;
read it for the level of detail a plan should reach.

---

## Personal overrides

Add your personal notes, local commands, and machine-specific settings to
`AGENTS.local.md` (gitignored). Tools that support local override files pick
it up; Claude Code does not, and instead auto-loads `CLAUDE.local.md`, so put
overrides there (or make it one line: `@AGENTS.local.md`).
