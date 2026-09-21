#!/usr/bin/env bash
#
# lib.sh: shared helpers for the ops/ scripts.
#
# Source this from another script:
#   source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
#
# Holds the helpers more than one ops/ script needs: locating the repository
# root, loading .env, and resolving the Cloudflare R2 bucket name (which
# defaults to the repository name; see docs/decisions/D-0001-*.md).

# Absolute path to the repository root (the parent of ops/). Runs in a
# subshell so the caller's working directory never changes.
ops_repo_root() {
  ( cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd )
}

# The keys the ops/ scripts read from .env. load_dotenv loads only these, so
# an unrelated secret in .env is never exported to a child process. Add a key
# here when a script starts reading it.
OPS_DOTENV_KEYS=(
  R2_ACCOUNT_ID R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY
  R2_BUCKET R2_PREFIX R2_ASSETS_PREFIX
  DATA_DIR ASSETS_DIR
  CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID
)

# Load the keys above from a .env file at the repo root, if present.
#
# The file is parsed line by line as KEY=VALUE (an `export ` prefix, quotes
# around the value, and an inline ` # comment` after an unquoted value are
# accepted), never sourced: some scripts run automatically via hooks, and
# sourcing would execute arbitrary shell from a gitignored file. A key already
# set in the environment (even to an empty value) wins over the file; within
# the file, the last line for a key wins, as it would under `source`.
load_dotenv() {
  local root keys_re preset=" " line key value
  root="$(ops_repo_root)"
  [[ -f "$root/.env" ]] || return 0
  keys_re="$(IFS='|'; printf '%s' "${OPS_DOTENV_KEYS[*]}")"
  for key in "${OPS_DOTENV_KEYS[@]}"; do
    [[ -n "${!key+set}" ]] && preset+="$key "
  done
  while IFS= read -r line; do
    key="${line%%=*}"
    value="${line#*=}"
    # Trim surrounding whitespace, take a quoted value up to its closing
    # quote, and drop an inline comment from an unquoted one: the values
    # `source` would have produced for the .env.example format.
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    case "$value" in
      \"*\"*) value="${value#\"}"; value="${value%%\"*}" ;;
      \'*\'*) value="${value#\'}"; value="${value%%\'*}" ;;
      *" #"*) value="${value%% #*}"
              value="${value%"${value##*[![:space:]]}"}" ;;
    esac
    if [[ "$preset" != *" $key "* ]]; then
      printf -v "$key" '%s' "$value"
      # shellcheck disable=SC2163
      export "$key"
    fi
  done < <(grep -E "^(export[[:space:]]+)?(${keys_re})=" "$root/.env" 2>/dev/null \
    | sed -E 's/^export[[:space:]]+//' || true)
}

# Derive the repository name (used as the default R2 bucket name).
#
# Order of preference:
#   1. The basename of the `origin` remote URL (matches the GitHub repo name).
#   2. The repository root directory name.
#
# The result is normalised for R2 bucket naming rules (lowercase letters,
# numbers and hyphens): uppercase is lowercased, and every other character
# becomes a hyphen. Names shorter than 3 or longer than 63 characters still
# break R2's rules; ops/create-bucket.sh validates and says how to fix them.
repo_name() {
  local name=""
  local url
  if url="$(git remote get-url origin 2>/dev/null)" && [[ -n "$url" ]]; then
    name="$(basename -s .git "$url")"
  fi
  if [[ -z "$name" ]]; then
    name="$(basename "$(ops_repo_root)")"
  fi
  printf '%s\n' "$name" \
    | tr '[:upper:]' '[:lower:]' \
    | tr -s -c 'a-z0-9\n' '-' \
    | sed -E 's/^-+//; s/-+$//'
}

# Resolve the R2 bucket name: the R2_BUCKET override if set, otherwise the
# repository name.
r2_bucket_name() {
  printf '%s\n' "${R2_BUCKET:-$(repo_name)}"
}
