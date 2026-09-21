# Plan: Push created assets to Cloudflare R2 by default

> **Status:** Done

## Overview

The repo can pull project data down from R2 (`ops/fetch-data.sh`) but has no upload path, so
anything created locally stays local. Add the symmetric push side: a `./assets/` directory
convention for created assets, an `ops/push-assets.sh` script that syncs it to the R2 bucket,
and a Claude Code `Stop` hook that runs the script automatically at the end of every agent
turn, so created assets land in R2 by default and are accessible from any machine. The hook
runs the script in `--auto` mode, which exits silently when R2 is not configured or there is
nothing to push, so fresh clones of the template are unaffected; when R2 is configured but the
upload cannot happen, it fails loudly instead of losing assets silently.

## Steps

- [x] 1. Create `ops/push-assets.sh`, mirroring `ops/fetch-data.sh` (loads `.env`, validates
       `R2_*` vars, `aws s3 sync` with the R2 endpoint and checksum workarounds). Uploads
       `ASSETS_DIR` (default `./assets`) to `s3://$R2_BUCKET/<prefix>` (default prefix
       `assets`, override via arg or `R2_ASSETS_PREFIX`). Never passes `--delete`. Supports
       `--auto` (graceful no-op used by the hook).
- [x] 2. Register a `Stop` hook in `.claude/settings.json` running
       `"$CLAUDE_PROJECT_DIR"/ops/push-assets.sh --auto` (explicit timeout; 300 s today).
- [x] 2b. Harden for auto-run via hook (from adversarial review): parse `.env` for the
       expected keys instead of sourcing it (no arbitrary code execution, no leaking
       unrelated secrets into the `aws` process, env vars genuinely take precedence);
       `--no-follow-symlinks` and exclude secret-looking files (`.env*`, `*.pem`, `*.key`,
       `id_rsa*`, `secrets/`) so secrets can't be auto-exfiltrated; anchor a relative `ASSETS_DIR` to the repo root (hook cwd is not
       guaranteed); never exit 2 from the hook path (exit 2 from `aws s3 sync` would block
       the session from stopping); fail fast in `--auto` mode (`AWS_MAX_ATTEMPTS=2`,
       `--cli-connect-timeout 5`) so a degraded network can't stall every turn.
- [x] 3. Add `assets/` to `.gitignore`; document `R2_ASSETS_PREFIX` / `ASSETS_DIR` in
       `.env.example`.
- [x] 4. Document the convention in `CLAUDE.md` (Commands, Environment/gotchas) and
       `README.md` (Getting started).
- [x] 5. Verify: `bash -n` / shellcheck both scripts; exercise `--auto` no-op paths and a
       stubbed end-to-end sync (fake `aws` on `PATH`).
- [x] 6. Commit: `push created assets to Cloudflare R2 by default`

## Files changed

| File | Change |
|------|--------|
| `ops/push-assets.sh` | New: sync `./assets` up to R2 (manual + `--auto` hook mode) |
| `.claude/settings.json` | New `Stop` hook: auto-push assets after each agent turn |
| `.gitignore` | Ignore `assets/` |
| `.env.example` | Document `R2_ASSETS_PREFIX`, `ASSETS_DIR` |
| `CLAUDE.md` | Commands entry + gotchas note for the auto-push hook |
| `README.md` | Mention the assets convention in Getting started |

## Verification

```bash
bash -n ops/push-assets.sh
shellcheck ops/push-assets.sh   # if installed

# Hook mode is a silent no-op without config
ops/push-assets.sh --auto; echo "exit=$?"

# Manual mode fails loudly without config
ops/push-assets.sh || true

# End-to-end with a stubbed aws CLI (asserts the sync command line);
# see the fake-aws harness used during development
```

---

_Related spec: none (small, self-contained change)_
