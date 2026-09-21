---
status: "accepted"
date: 2026-08-19
decider: [joehmyers]
tags: [agents, skills, marketplace, portability]
supersedes: []
superseded: null
---

# D-0002. Platform-neutral skill format for agent marketplaces

## Context

This decision governs the `power-bi-workbench` repository (the Power BI plugin
marketplace). It is recorded here because this repository is the documentation
home for the project; see the spec at
`docs/specs/agent-agnostic-marketplace/spec.md`.

The marketplace began as a Claude Code plugin repository. Every piece of
content was expressed in Claude's format: skills as `SKILL.md` files with
Claude frontmatter, tools as `.mcp.json`, hooks as scripts that parse Claude's
stdin JSON protocol, and manifests under `.claude-plugin/`. Users on other
platforms (Databricks Genie for data questions, OpenAI assistants for hosted
chat) could not reuse any of it without hand-copying and rewriting.

The content itself is not Claude-specific: a skill is a name, a description,
an instruction body, and resource files; a hook is a script plus the events
that fire it; a tool is a server address. Only the packaging is
platform-specific. Locking portable content into one platform's packaging was
the problem.

## Options

- **Platform-neutral source tree plus per-platform adapters.** Skills, tools,
  and hooks live in a YAML-and-Markdown format that no platform reads
  natively; a small script per platform translates them into that platform's
  native format.
- **Parallel trees.** Maintain a copy of the content per platform, edited by
  hand.
- **Claude format as the source of truth.** Keep authoring in `SKILL.md` and
  write converters from Claude's format to the others.
- **A runtime translation service.** Serve one format over an API and adapt on
  request.

## Decision

We will restructure the marketplace around a platform-neutral source tree with
one adapter per target platform.

- `marketplace.yaml` holds the name, lockstep version, shared metadata, and
  group list. `skills/<group>/<skill>/` holds each skill as `skill.yaml`
  (name, description) plus `instructions.md` (plain Markdown) and resource
  directories. `tools/*.yaml` describes MCP servers. `hooks/<name>/` holds a
  `hook.yaml` event map plus plain shell scripts that take file paths or
  command text as arguments.
- `adapters/<platform>/build.py` translates the neutral tree into one
  platform's format. The Claude adapter's output (`plugins/`,
  `.claude-plugin/`) stays committed because Claude Code installs straight
  from the repository; CI regenerates it and fails on drift. The Genie and
  OpenAI adapters build to a gitignored `dist/` from a config that selects
  skills.
- Hooks stay executable shell scripts. Platform protocol handling (Claude's
  stdin JSON) lives in a shim inside the Claude adapter, not in the scripts.
- Adapters are deliberately plain scripts, copied per platform rather than
  abstracted into a framework. An adapter translates what its platform can
  express and documents what stays behind.

## Consequences

- **Benefits:** one authored source serves Claude Code, Databricks Genie, and
  OpenAI assistants; adding a platform means copying one adapter script, not
  rewriting 32 skills.
- **Benefits:** hook scripts run standalone (`bash validate-tmdl.sh <file>`),
  so the same checks work in CI and pre-commit hooks with no agent involved.
- **Benefits:** the Claude output is byte-for-byte reproducible from the
  neutral sources, so the migration itself was verifiable (the generated tree
  matched the previous hand-maintained one exactly, hooks excepted, and those
  were covered by 14 behavioural tests).
- **Costs:** contributors must run the Claude adapter after editing and commit
  generated output alongside sources; CI enforces this, but it is one more
  step.
- **Costs:** the repository carries content twice (neutral source and
  generated Claude output). Git stores identical blobs once, so the cost is
  checkout size, about 14 MB doubled.
- **Costs:** the Genie and OpenAI adapters are best-effort translations:
  Genie takes only instruction text, and OpenAI assistants cannot run the
  hooks or MCP tools. Each adapter's README states its losses.
