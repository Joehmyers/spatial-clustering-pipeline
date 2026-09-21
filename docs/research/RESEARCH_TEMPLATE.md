# Research: <question in one line>

> **Status:** Draft | Complete | Partial (say what is missing) | Superseded by <file>
> **Date:** YYYY-MM-DD. Findings decay; a reader needs to know how old this is.

## Question

<!--
The sharpened question, not the vague one that started it. Include the
constraints that decide the answer: version, platform, scale, budget.
Bad:  "Which job queue?"
Good: "Which Postgres-backed job queue supports delayed retries and
       at-least-once delivery at 10k jobs/minute?"
-->

## Summary

<!--
Five sentences at most. What the sources support, and what they do not.
Lead with the answer. If the sources do not settle it, say that here; do not
make the reader reach the end to find out.
-->

## Definitions

<!--
Every term of art used below, defined once. Delete this section only if the
document genuinely introduces none.
-->

## Findings

<!--
One subsection per sub-question. Every claim carries a source: a URL, or a
`path:line` for code in this repository. Date the source where you can.
-->

### <Sub-question>

- <claim> ([source](url), <date>)
- <claim> (`src/file.py:42`)

## Options compared

<!--
Delete this section if the question is not a choice between options.
Score only on criteria the question named. An empty cell means "not
established"; never guess to fill the table.
-->

| Option | <criterion> | <criterion> | Evidence |
|--------|-------------|-------------|----------|
| A | | | [link](url) |
| B | | | [link](url) |

## Contradictions

<!--
Where sources disagree, with both cited. Do not resolve them silently; the
disagreement is itself a finding, and often the most useful one.
-->

## Not established

<!--
What was searched for and not found, and where you looked. "No published
benchmark above 1k rps" is a finding. Silence is not.
-->

## Not checked

<!--
The bounds of this document. What is out of scope, what nobody had time for,
what needs a test rather than a search. A reader who trusts a gap they did not
know about is worse off than one who had no research at all.
-->

## Recommendation

<!--
Optional, and clearly marked as the author's judgement rather than a finding.
Say which evidence carries it, and what would change your mind.
-->

## Sources

<!-- Every source consulted, including the ones that turned out useless. -->

1. [<title>](url): <what it is, and how far to trust it>

---

_Next step: `/decision <title>` if this settles a hard-to-reverse choice, `/spec <feature>` if it clears the way to build._
