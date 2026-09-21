#!/usr/bin/env bash
#
# setup.sh: bring a fresh clone to the point where ops/check.sh can run.
#
# A cloud or web agent session starts from a bare clone with no dependencies
# installed, so it cannot run your tests and has to guess whether a change
# works. This script installs them. A SessionStart hook in
# .claude/settings.json runs it automatically at the start of every session.
#
# Usage:
#   ops/setup.sh          Install dependencies; fail loudly if something breaks.
#   ops/setup.sh --auto   Hook mode: exit 0 silently when nothing is configured.
#
# Configure the command below. An empty value means "not configured yet", so a
# fresh clone of this template does nothing and reports nothing. The
# environment variable of the same name overrides the value here.
set -uo pipefail

# shellcheck source=ops/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

cd "$(ops_repo_root)" || exit 1

# --- Configure your project here -------------------------------------------
# Installs the nca package and its test tools. Editable, so a change in src/
# takes effect without reinstalling.
: "${SETUP_INSTALL:=python3 -m pip install --editable '.[dev]'}"
# ---------------------------------------------------------------------------

auto=0
for arg in "$@"; do
  case "$arg" in
    --auto) auto=1 ;;
    *)
      echo "error: unknown argument: $arg" >&2
      echo "usage: ops/setup.sh [--auto]" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$SETUP_INSTALL" ]]; then
  (( auto )) && exit 0
  echo "Nothing to do. Set SETUP_INSTALL in ops/setup.sh to your install command."
  exit 0
fi

echo "Setting up: ${SETUP_INSTALL}"
status=0
bash -c "$SETUP_INSTALL" || status=$?

if (( status == 0 )); then
  echo "Done. Run ops/check.sh to verify the repo."
  exit 0
fi

# Never block the session on a failed install: report it and let the agent
# decide. A hook that hard-fails here would make the repo unusable offline.
echo "setup: '${SETUP_INSTALL}' failed (exit ${status})." >&2
(( auto )) && exit 0
exit "$status"
