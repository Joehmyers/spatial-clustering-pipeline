# AGENTS.md

Agent context for this repository: the canonical, tool-agnostic instruction
file, auto-loaded at the start of every agent session. Claude Code reads it
through a one-line `@AGENTS.md` import in `CLAUDE.md`.

Keep it short, and include only what an agent cannot infer from the code.

---

## Commands

```bash
# Verify the repo: lint, tests, build. THE command; CI runs this exact script.
ops/check.sh

# Install dependencies (also runs automatically via SessionStart hook)
ops/setup.sh

# Run locally: all seven stages on the committed fixture
SETTINGS=tests/fixtures/nca-regionalisation/settings.toml
nca run all --settings $SETTINGS --out runs/fixture

# One stage alone; it reads the earlier stages' saved outputs from --out
nca run cluster --settings $SETTINGS --out runs/fixture

# List the stages in order; rewrite the fixture from its formulas
nca stages
nca fixture --out tests/fixtures/nca-regionalisation

# Create the project's Cloudflare R2 bucket (wrangler; bucket = repo name)
ops/create-bucket.sh [bucket-name]

# Fetch project data from Cloudflare R2 into ./data (config via .env; see .env.example)
ops/fetch-data.sh [prefix]

# Push created assets from ./assets to Cloudflare R2 (runs automatically via Stop hook)
ops/push-assets.sh [prefix]
```

`ops/check.sh` and `ops/setup.sh` each hold their commands in a configuration
block at the top. Put them there, not in this file: one place that agents,
humans and CI all read means the answer to "is this green?" cannot drift.

---

## Architecture

- `src/nca/`: one module per stage (`geometry`, `graph`, `features`,
  `cluster`, `mapping`, `evaluate`, `report`), plus `settings`, `inputs`
  (the demand firewall and sealed-window gate), `runrecord`, `outputs`,
  `pipeline` and `cli`
- `tests/`: test suite (the agent's verification target)
- `tests/fixtures/`: files tests read as input or compare against; its README
  has the size and naming rules
- `docs/`: `research/` (evidence), `specs/` (what and why), `plans/` (how),
  `decisions/` (the durable why), `diagrams/`, `style-guide.md`
- `ops/`: infrastructure, verification and deployment scripts
- `.claude/`: Claude Code configuration, committed: `skills/`, `agents/`,
  `rules/` (path-scoped instructions), `settings.json` (permissions and hooks)
- `.github/`: CI workflow and pull request template

---

## Code style

Python 3.11, formatted and linted by `ruff` (settings in `pyproject.toml`,
line length 88). `ops/check.sh` runs `ruff check` and `ruff format --check`.

- **One module per stage** in `src/nca/`, each with
  `run(settings, run_directory, record)`. Stages never hand objects to each
  other: they read each other's saved files.
- **Full words in names**, and units on anything measured
  (`shared_edge_metres`, `area_square_metres`). Every length is metres.
- **Settings, not constants.** Anything a reviewer might want to change goes
  in `src/nca/settings.py` with a default. Only a tolerance that absorbs
  floating-point noise is a constant, named at the top of its module.
- **Errors say what to do.** Each class in `src/nca/errors.py` names the rule
  it protects; its message names the setting that changes the outcome.
- **Docstrings carry the why**, and cite the requirement by number.

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

The same rules live in `.claude/rules/writing.md`, repeated here so tools
without path-scoped rules see them, and because they apply to prose that is
not a file at all: commit messages, PR descriptions, error strings.

---

## Testing

`tests/` is the agent's verification target. `ops/check.sh` is how you run it.

- NEVER modify a test to make it pass; fix the implementation instead.
- NEVER mock a module that exists in this repo; test it directly.
- Every test asserts a concrete outcome. A test that cannot fail is not a test.
- Write the test before the implementation when the file does not exist yet.
- Run `ops/check.sh` after every implementation change to catch regressions.

The same rules live in `.claude/rules/testing.md`, repeated here so tools
without path-scoped rules see them.

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
Markdown files, numbered `D-0001` and up, recording *why* a hard-to-reverse
choice was made. They are the historical "why"; this file is the active "what".
`docs/decisions/README.md` owns the format; these rules are repeated here.

- **Read the index and any relevant record before proposing an architectural
  change.** Do not contradict an `accepted` decision.
- If one genuinely needs to change, ask a human, then write a **new** record
  that supersedes it. Never rewrite an accepted record.
- Log only **architecturally significant** decisions: ones costly to change or
  needing coordination, migration or risk management to reverse.

---

## Architecture decisions in force

Each line is the rule; the linked record carries the reasoning. Read it before
proposing a change to any of these.

- **Cloud storage is Cloudflare R2**, bucket named after the repository (override
  with `R2_BUCKET`). Lifecycle via wrangler, bulk transfer via the S3-compatible
  API. See [D-0001](docs/decisions/D-0001-use-cloudflare-r2-for-project-storage.md).
- **The weather map is built from weather alone**: DTN virtual points, no
  demand, no breakdown weights, no current NCA, PGA or RA labels. Operational
  layers enter the build only as a dissolved outline to clip cells to. See
  [D-0003](docs/decisions/D-0003-build-the-weather-map-from-weather-alone.md).

---

## Environment / gotchas

- Build stages never read demand; only evaluate may (R12). The firewall lives
  in `src/nca/inputs.py`, and a test fails if a build stage even mentions it.
- Never request data on or after `windows.sealed_start`; the override needs a
  human's say-so, and every run records that it was used (R13).
- Normals and scaling come from the build window only, are stored, and the
  held-out window reuses them unchanged (R14).
- Cut the tree by merge order, never by height (R6): a constrained tree can
  hold an inversion, and cutting one by height gives the wrong cluster count.
- Real inputs stay unconnected until their shape is described: ask rather than
  invent schemas (`RealInputsNotConnectedError` says what shape is expected).
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

For larger features, start with a spec in `docs/specs/<feature>/spec.md`
(`/spec <feature>`). One-sentence diff? Skip the plan. When the choice needs
evidence rather than recall, run `/research <question>` first: it writes cited
findings to `docs/research/`. When a change makes an architecturally
significant decision, record it with `/decision <title>`.

---

## Personal overrides

Put personal notes, local commands and machine-specific settings in
`AGENTS.local.md` (gitignored). Claude Code auto-loads `CLAUDE.local.md`
instead, so put overrides there (or make it one line: `@AGENTS.local.md`).
