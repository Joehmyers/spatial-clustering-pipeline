---
status: "accepted"
date: 2026-08-04
decider: []
tags: [storage, infrastructure, cloud]
supersedes: []
superseded: null
---

# D-0001. Use Cloudflare R2 for project storage

## Context

Projects built from this template need somewhere to keep two kinds of file that
do not belong in git: input data an agent reads (datasets, fixtures, dumps) and
created assets an agent produces (reports, renders, build outputs) that should
outlive the machine that made them. Committing either bloats the repository;
leaving both on disk means work vanishes when a cloud or web agent session ends.

An agent cannot pick a storage provider per session; it needs one answer that
holds on a fresh clone, with no interview and no per-project configuration. So
the template has to choose, and record why.

The choice is deliberately easy to walk away from: the whole surface is three
shell scripts and one config file, all speaking the S3 API. This record exists
because the *default* is load-bearing, not because the coupling is deep.

## Options

- **Cloudflare R2**, driven by wrangler for bucket lifecycle and the
  S3-compatible API for bulk transfer.
- **Amazon S3**: the reference implementation, the widest tooling support.
- **Git LFS**: keep large files in the repository itself.
- **No default**: leave storage unconfigured and make every project choose.

## Decision

We will use **Cloudflare R2** as the assumed cloud storage for projects built
from this template.

- The bucket is named after the repository, so a fresh clone can provision
  storage with no configuration. `R2_BUCKET` overrides it.
- Bucket lifecycle is managed with **wrangler** (`ops/create-bucket.sh` runs
  `wrangler r2 bucket create <repo-name>`). The R2 binding lives in
  `wrangler.jsonc`.
- Bulk transfer uses the **S3-compatible API** through the AWS CLI
  (`ops/fetch-data.sh` down, `ops/push-assets.sh` up), because wrangler has no
  recursive sync.
- Storage stays **optional**. Without R2 credentials in `.env`, the scripts and
  the `Stop` hook are silent no-ops, so a fresh clone needs no cloud account.

## Consequences

- **Benefits:** no egress fees, so an agent can pull the same dataset on every
  run without a bill that scales with how often it works.
- **Benefits:** the S3-compatible API means the standard AWS CLI works, and the
  two transfer scripts would port to any S3-compatible provider by changing one
  endpoint URL.
- **Benefits:** naming the bucket after the repository removes a configuration
  step an agent would otherwise have to ask a human about.
- **Costs:** two tools instead of one (wrangler for lifecycle, AWS CLI for
  transfer) because neither covers both jobs. A Cloudflare account is needed to
  use the storage features at all.
- **Costs:** R2 has no region pinning in the S3 sense; every request uses
  `region=auto`. Projects with data-residency requirements should revisit this.
- **Costs:** the transfer scripts carry a checksum workaround
  (`AWS_REQUEST_CHECKSUM_CALCULATION=when_required`) because R2 rejects the
  newer AWS CLI default integrity checksums. Remove it if R2 adds support.
