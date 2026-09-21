# Test fixtures

A **fixture** is a file a test reads as input or compares its output against:
a sample request, a config file, ten rows of CSV, the expected result of a
transform. This folder holds them. Nothing in here runs; the tests in `tests/`
load these files by path.

## What belongs here

- Small files a test needs, hand-written or trimmed from real data. Keep each
  under 100 KB. Anything larger is data, not a fixture: keep it in the
  project's Cloudflare R2 bucket (its cloud storage) and fetch it with
  `ops/fetch-data.sh`, as
  [D-0001](../../docs/decisions/D-0001-use-cloudflare-r2-for-project-storage.md)
  decides.
- Files a reviewer can read in a diff. Prefer text (JSON, CSV, YAML, plain
  text) to binary. When a test needs a binary file, keep it as small as the
  test allows.
- Made-up values only: no real credentials, tokens, or personal data.

## Layout and naming

- One folder per module or feature under test, named after it:
  `tests/fixtures/invoice-parser/`.
- Name each file for the case it exercises, not for how it was made:
  `missing-total.json`, not `test1.json`.
- When a test compares an input with an expected output, keep the pair
  together: `missing-total.input.csv` and `missing-total.expected.json`.

## Rules

- A fixture is part of the test, so the testing rules in `AGENTS.md` apply:
  never change one to make a failing test pass. Fix the implementation.
- Nothing machine-specific: no absolute paths, no clock-dependent timestamps,
  no locale-specific number or date formats.
- The repository `.gitignore` drops files that look like build output
  (`*.log`, `build/`, `dist/`, `tmp/`, `data/`, `assets/`). A rule at the
  bottom of `.gitignore` re-includes everything under this folder, so a sample
  log file used as test input is committed like any other file. The one
  exception: `.env` files stay ignored here as everywhere (`.env.example` is
  allowed, as at the root).
