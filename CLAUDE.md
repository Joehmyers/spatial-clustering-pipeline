# CLAUDE.md

The instructions for this repository live in `AGENTS.md`, which is
tool-agnostic and is the one source of truth for every agent. Claude Code does
not read it natively, so the import below pulls it in.

Everything below the import is Claude Code's own: the configuration under
`.claude/`, what it does automatically, and what it refuses to do. None of it
changes a rule in `AGENTS.md`.

@AGENTS.md

---

## Configuration

All committed, so the whole team gets the same setup.

| Path | What it holds |
| --- | --- |
| `.claude/settings.json` | Permissions and hooks |
| `.claude/skills/` | Workflows, each also usable as `/name` |
| `.claude/agents/` | Subagents, each with its own context window and tool list |
| `.claude/rules/` | Instructions that load only when you touch matching files |

Personal overrides go in `CLAUDE.local.md`, which is gitignored. Claude Code
auto-loads that rather than the `AGENTS.local.md` other tools read, so make it
one line if you want both: `@AGENTS.local.md`.

---

## Skills

The planning workflow in `AGENTS.md` describes what to write and when. These
run it:

| Command | What it does |
| --- | --- |
| `/research <question>` | Fans subagents out over real sources and writes cited findings to `docs/research/` |
| `/spec <feature>` | Writes a feature spec to `docs/specs/<feature>/spec.md` |
| `/plan <feature>` | Writes an implementation plan to `docs/plans/<feature>.md` |
| `/decision <title>` | Records a decision in `docs/decisions/` |

`.claude/agents/code-reviewer.md` is a read-only adversarial reviewer. It
cannot run git, so paste the diff or the list of changed files into it.

---

## Rules that load themselves

`.claude/rules/writing.md` loads when you touch a Markdown file, and
`.claude/rules/testing.md` when you touch a test file. Both restate rules
`AGENTS.md` already carries, so nothing is lost for a tool that cannot scope
instructions by path.

---

## Hooks

A hook runs whether or not the agent decides to, so these are guarantees
rather than advice.

- **SessionStart** runs `ops/setup.sh --auto`, so a session that starts from a
  bare clone has its dependencies. It never fails the session: a broken
  install reports itself and lets the agent decide.
- **Stop** runs `ops/push-assets.sh --auto` after each turn, uploading
  anything in `./assets/` to Cloudflare R2. Symlinks and secret-looking files
  are never uploaded. Without R2 credentials in `.env` it is a silent no-op.

---

## Blocked reads

Deny rules in `.claude/settings.json` stop Claude Code reading `.env` and its
variants, `*.pem`, `*.key`, `id_rsa*` and `secrets/`. `.env.example` stays
readable on purpose.

That is enforcement, not advice: do not work around it. If a task genuinely
needs a secret, ask for it.
