#!/usr/bin/env bash
#
# create-bucket.sh: create this project's Cloudflare R2 bucket with wrangler.
#
# Cloud storage is assumed to be Cloudflare R2. By default the bucket is named
# after the repository, so a freshly cloned project can provision its bucket
# with no configuration.
#
# Usage:
#   ops/create-bucket.sh [bucket-name]
#
#   bucket-name   Optional bucket name (overrides R2_BUCKET and the repo name).
#
# Auth: run `wrangler login` first, or set CLOUDFLARE_API_TOKEN /
#       CLOUDFLARE_ACCOUNT_ID in the environment (or .env).
#
# Requires wrangler: https://developers.cloudflare.com/workers/wrangler/install-and-update/
set -euo pipefail

# shellcheck source=ops/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

load_dotenv

if ! command -v wrangler >/dev/null 2>&1; then
  echo "error: wrangler is required but not installed." >&2
  echo "Install it: https://developers.cloudflare.com/workers/wrangler/install-and-update/" >&2
  echo "  npm install -g wrangler   # or run via: npx wrangler ..." >&2
  exit 1
fi

bucket="${1:-$(r2_bucket_name)}"

# R2 bucket names are 3 to 63 characters: lowercase letters, numbers and
# hyphens, starting and ending with a letter or number. repo_name (ops/lib.sh)
# normalises most repository names into this shape, but a name that is too
# short or too long cannot be fixed automatically.
# https://developers.cloudflare.com/r2/buckets/create-buckets/
if ! [[ "$bucket" =~ ^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$ ]]; then
  echo "error: '${bucket}' is not a valid R2 bucket name." >&2
  echo "Bucket names are 3-63 characters: lowercase letters, numbers, hyphens." >&2
  echo "Pass one explicitly (ops/create-bucket.sh <bucket-name>) or set R2_BUCKET in .env." >&2
  exit 1
fi

echo "Creating Cloudflare R2 bucket: ${bucket}"
if wrangler r2 bucket create "$bucket"; then
  echo "Done. Bucket '${bucket}' is ready."
else
  status=$?
  echo "error: 'wrangler r2 bucket create ${bucket}' failed (exit ${status})." >&2
  echo "If the bucket already exists this is safe to ignore; otherwise check" >&2
  echo "that you are authenticated (run 'wrangler login')." >&2
  exit "$status"
fi
