# Decisions

This folder holds the **decision records** for the project. By these we mean one short and immutable
Markdown file for each design choice that is hard to reverse. Crucially we capture *why* it was
made. This format is inspired by Michael Nygard's
[Architecture Decision Record](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
pattern and simplified from [MADR](https://adr.github.io/madr/). Here the records
are plain decisions and are numbered `D-0001` and up.

A record holds one decision: the context that forced it, the alternatives that
were rejected, and the consequences. Records can only be **appended** to this list. When a
decision changes, you must write a *new* record that supersedes the old one by following the steps below.  
Each record was true on the day it was written and the chain of supersession tells the whole story of how the system evolved and why.

## Why this exists

A commit message records *what* changed while a decision record explains *why* it was
the right answer at the time, which constraints applied, and what alternatives
were rejected. A human can compensate for missing rationale by asking a
colleague while an agent cannot. Without recorded rationale an agent infers intent
from code patterns and will faithfully reproduce a convention without knowing
whether it is deliberate, deprecated, or accidental.

This folder provides the historical "why" while `AGENTS.md` provides the active "what" and so these are
complementary: a record says *"we chose Postgres because we needed transactional
consistency"*; an `AGENTS.md` rule says *"all data access goes through the
existing Postgres pool; never add a new database dependency without approval."*
So one explains the past while the other governs the future.

## For agents

- Before proposing any deep change to this project you must **read this index and any relevant
  record.**
- **You must not contradict an `accepted` decision.** If it genuinely needs to change then you 
  can supersede it by following the steps below but only after asking a human and never edit the accepted record.
- When retrieving decisions always **filter on `status`** so superseded/deprecated
  records never outrank the current one. The frontmatter values are lowercase
  (`accepted`, `superseded by D-NNNN`; see [`template.md`](template.md)).

## Index

| ID | Title | Status | Date |
|----|-------|--------|------|
| [D-0001](D-0001-use-cloudflare-r2-for-project-storage.md) | Use Cloudflare R2 for project storage | accepted | 2026-08-04 |
| [D-0002](D-0002-platform-neutral-skill-format-for-agent-marketplaces.md) | Platform-neutral skill format for agent marketplaces | accepted | 2026-08-19 |
| [D-0003](D-0003-build-the-weather-map-from-weather-alone.md) | Build the weather map from weather alone | accepted | 2026-09-21 |

<!-- Add a row for every new record. Keep it sorted by number. -->

## Writing a new decision

1. Copy [`template.md`](template.md) to `D-NNNN-short-title.md`, where `NNNN` is
   the next zero-padded number.
2. Fill in the YAML frontmatter and sections. Keep it to a page or two: one
   decision per record.
3. Add a row to the index table above.
4. Open it in a pull request and review it like code; merge when the status is
   `accepted`.
5. To change a past decision, write a new record, set the old one's `status` to
   `superseded by D-NNNN` and its `superseded` field, and set `supersedes` on
   the new one.

Log only **architecturally significant** decisions, ones that are costly to
change or would need coordination, migration, or risk management to reverse.
Skip trivial and reversible choices a linter or convention already covers.
