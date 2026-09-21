# Spec: Agent-agnostic plugin marketplace

> **Status:** Implemented

This spec governs the `power-bi-workbench` repository (the Power BI plugin
marketplace). It lives here because this repository is the documentation home
for the project. The architectural decision behind it is
[D-0002](../../decisions/D-0002-platform-neutral-skill-format-for-agent-marketplaces.md).

## Problem

The marketplace's 11 plugins (32 skills, 3 hook bundles, 3 MCP tools, 8
subagents, 2 commands) were expressed only in Claude Code's plugin format.
Skills were `SKILL.md` files with Claude frontmatter, hooks parsed Claude's
stdin JSON protocol, and manifests lived under `.claude-plugin/`. Users on
Databricks Genie or OpenAI assistants could not reuse the content, and every
new platform would mean another hand-maintained copy.

## Scope

### In scope

- A platform-neutral source layout: `skills/`, `tools/`, `hooks/`,
  `marketplace.yaml`.
- An adapter layer under `adapters/` with three adapters: Claude Code
  (regenerates the existing format), Databricks Genie, OpenAI assistants.
- Hook scripts refactored to take their input as arguments so they run on any
  platform and standalone.
- CI enforcement that the committed Claude output matches the neutral
  sources.

### Out of scope

- Rewriting skill content. Bodies move verbatim; only packaging changes.
- Translating subagents and commands beyond Claude (kept as Claude-consumed
  prompt files in the neutral tree).
- Publishing pipelines for Genie or OpenAI (the adapters emit payloads and
  documented apply steps, not live deployments).

## Requirements

1. A single skill definition (`skill.yaml` + `instructions.md`) feeds every
   adapter; no skill is authored twice.
2. Adapters translate the neutral sources into platform-native formats:
   Claude plugins, a Genie space request, an OpenAI assistant payload.
3. Hooks remain executable shell scripts, runnable as
   `bash <script> <args>` with no agent present.
4. All existing Claude functionality is preserved: the regenerated marketplace
   validates with `claude plugin validate`, and regenerated files are
   byte-identical to the previous tree except the deliberately refactored
   hooks.
5. Each adapter ships a README and an example config.
6. Simplicity over abstraction: adapters are standalone scripts; adding a
   platform means copying one.

## Interfaces / files involved

| File | Change |
|------|--------|
| `marketplace.yaml` | New: name, lockstep version, shared metadata, group list |
| `skills/<group>/<skill>/` | New: `skill.yaml` + `instructions.md` + resources, migrated from `SKILL.md` |
| `tools/<name>.yaml` | New: MCP server definitions, migrated from `.mcp.json` |
| `hooks/<name>/` | New: `hook.yaml` event maps + arg-driven scripts, migrated from plugin hooks |
| `adapters/claude/` | New: `build.py` (regenerates `plugins/` + `.claude-plugin/`), stdin shim, README |
| `adapters/genie/` | New: `build.py`, example space config, README |
| `adapters/openai/` | New: `build.py`, example assistant config, README |
| `plugins/`, `.claude-plugin/` | Now generated output, still committed |
| `.github/workflows/validate-plugins.yml` | Adds a drift job: rebuild and fail on diff, plus hook smoke tests |
| `scripts/test-hook-scripts.sh` | New: 14 behavioural tests for hook scripts and the Claude shim |

## Acceptance criteria

- [x] `python3 adapters/claude/build.py` regenerates `plugins/` and
  `.claude-plugin/` from the neutral sources; `git status` shows no diff on a
  clean tree.
- [x] `claude plugin validate` passes for the marketplace and all 11 plugins.
- [x] Regenerated skills, manifests, agents, commands, and resources are
  byte-identical to the pre-refactor tree (hooks excepted; they were
  refactored deliberately).
- [x] `bash scripts/test-hook-scripts.sh` passes: hooks work standalone and
  through the Claude shim with simulated payloads.
- [x] `python3 adapters/genie/build.py adapters/genie/examples/space-config.yaml`
  emits paste-ready instructions and a Genie spaces API request body.
- [x] `python3 adapters/openai/build.py adapters/openai/examples/assistant-config.yaml`
  emits instructions, Assistants and Responses API payloads, and a
  `file_search` upload manifest.

## End-to-end verification

1. Clone `power-bi-workbench`, install PyYAML, and run
   `python3 adapters/claude/build.py`; confirm `git status` is clean.
2. Run `bash scripts/test-hook-scripts.sh`; confirm `14 passed, 0 failed`.
3. Run `bash scripts/validate-plugins.sh` (needs the `claude` CLI); confirm
   all plugins pass.
4. Run both example adapter builds and inspect `dist/genie/` and
   `dist/openai/` outputs against their READMEs.
5. Edit any `instructions.md`, rerun the Claude build, and confirm the change
   appears in the matching `plugins/**/SKILL.md`.
