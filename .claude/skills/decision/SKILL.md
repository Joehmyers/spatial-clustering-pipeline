---
description: Record a decision in docs/decisions/, the durable why behind a significant, hard-to-reverse choice (also called an ADR). Use when a change picks a database, protocol, cloud provider, framework, or boundary, or when someone asks to record a decision, an ADR, its rationale, or the alternatives considered.
argument-hint: [short-title]
---

# Record a decision

Decision: `$ARGUMENTS`

A decision record captures **why** a hard-to-reverse choice was the right answer
at the time, which constraints applied, and what was rejected. A commit message
records what changed; a decision record explains why nobody should quietly
change it back.

## Steps

1. **Confirm it is architecturally significant**: costly to change, or reversing
   it would need coordination, migration, or risk management. If it is trivial or
   already covered by a linter or convention, say so and write nothing. A log
   full of small decisions hides the load-bearing ones.
2. **Read `docs/decisions/README.md`** and the most recent records, so the new
   one is consistent and does not silently contradict an `accepted` decision.
3. **Follow the README's "Writing a new decision" steps.** The README owns the
   mechanics (template, `D-NNNN` numbering, index row, supersession, pull
   request), so they are stated once and cannot drift.
4. **List the real alternatives that were on the table.** "We just picked it" is
   not a rationale, and the alternatives are what a future reader needs to
   reopen the question honestly. Follow `docs/style-guide.md`: a record is read
   years later by someone who was not there, so define every term of art on
   first use and state consequences as concrete outcomes.
