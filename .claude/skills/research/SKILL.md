---
description: Research a technical question against real sources and write a findings document to docs/research/<topic>.md. Use before choosing a library, protocol, database, or approach; when asked what the prior art is, how something actually works, or what the trade-offs are; and whenever a decision needs evidence rather than recall.
argument-hint: [question or topic]
---

# Research a technical question

Question: `$ARGUMENTS`

Produce a **findings document**, not an answer in chat. The document outlives the
conversation, gets reviewed, and becomes the evidence behind a decision record.
Chat does not.

You are researching so that someone can decide. Do not decide for them. Present
what the sources support, what they do not, and what is still unknown.

## Steps

1. **Sharpen the question.** "Which job queue?" is not researchable. "Which
   Postgres-backed job queue supports delayed retries and at-least-once delivery
   under 10k jobs/minute?" is. If the request is vague, ask before searching;
   a wrong question wastes the whole run.

2. **Check what is already decided.** Read `docs/decisions/README.md` and any
   relevant record. If an `accepted` decision already settles this, say so and
   stop; the question is whether to supersede it, which is a different job
   (`/decision`).
   Also check `docs/research/`; this may already have been researched.

3. **Decompose into sub-questions.** Three to six, each independently
   answerable. Cover the dimensions that actually decide it: does it do the
   thing, what does it cost, how does it fail, who maintains it, what do people
   who adopted it report afterwards.

4. **Fan out.** Spawn one `researcher` subagent per sub-question, **in parallel,
   in a single message**. Each searches in its own context, so the raw pages
   never fill this conversation. Give each one the sharpened question, its
   sub-question, and any constraint that matters (version, platform, scale).

5. **Read the returned evidence, not just the answers.** A subagent's confidence
   is a claim like any other. Spot-check the load-bearing citations yourself,
   the ones a decision would actually rest on. If a source does not say what the
   report claims, that is the finding.

6. **Write the document.** Copy `docs/research/RESEARCH_TEMPLATE.md` to
   `docs/research/<topic>.md`. The template is the single source of truth for
   the layout. Follow `docs/style-guide.md`: numbers over adjectives, every term
   of art defined, no hedging filler.

7. **Be explicit about the edges.** The "Not established" and "Not checked"
   sections are the most valuable part of the document. A reader who trusts a
   gap they did not know about is worse off than one who had no research at all.

8. **Hand off.** Say which follow-up fits:
   - `/decision <title>`: the research settles a hard-to-reverse choice
   - `/spec <feature>`: the research clears the way to build
   - More research: name the specific gap that blocks a decision

## What makes this deep rather than a search

- **Parallel, isolated contexts.** Each sub-question gets a full context window.
  Ten pages of documentation get read and reduced to five cited lines.
- **Primary sources.** Documentation, source code, release notes, issue threads:
  read, not skimmed from snippets.
- **Disagreement survives.** Contradictions are reported with both citations
  rather than averaged into a confident sentence.
- **The gaps are written down.** What nobody could establish is recorded as
  plainly as what they could.

## When the network is unavailable

Sessions sometimes run without web access. Do not fall back on recall and
present it as research; that is the failure mode this whole workflow exists to
prevent. Say that web search was unavailable, research what the repository
itself can answer, and mark the document `Status: Partial (no web access)`.
