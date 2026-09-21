---
description: Write an implementation plan (the how) to docs/plans/<feature>.md, from an existing spec or a description. Use before editing code for any change that touches more than one file, and whenever someone asks how a change will be carried out.
argument-hint: [feature-name]
---

# Write an implementation plan

Feature: `$ARGUMENTS`

A plan records **how** the change will be made, as steps someone can follow and
check off. It assumes the what and why are already settled, by a spec or by
the user's description for a change too small to need one.

## Steps

1. **Read the spec** at `docs/specs/$ARGUMENTS/spec.md` if it exists.
2. **Explore in plan mode.** Read the source files the change will touch. Make no
   edits at this stage; the plan is the artifact, not a first draft of the code.
3. **Check past decisions.** Read `docs/decisions/README.md` and any relevant
   record. If the plan contradicts an `accepted` decision, stop and propose a
   superseding record with `/decision` instead of working around it.
4. **Copy the template.** `docs/plans/PLAN_TEMPLATE.md` → `docs/plans/$ARGUMENTS.md`.
   The template is the single source of truth for the section layout.
5. **Write concrete steps.** Each step names the file to create or edit and the
   function to add or change. "Refactor the handler" is not a step; "split
   `handle_request` in `src/api.py` into parse and dispatch" is. Follow
   `docs/style-guide.md`: active voice, short sentences, numbers over
   adjectives.
6. **End with verification.** The last steps are always: write or update tests,
   run `ops/check.sh`, fix failures, commit.
7. **Ask the user to approve** before leaving plan mode.

## While implementing

Tick the checkboxes in the plan file as you go, and run `ops/check.sh` after each
step. If reality diverges from the plan, update the plan file: a stale plan is
worse than none, because the next reader trusts it.
