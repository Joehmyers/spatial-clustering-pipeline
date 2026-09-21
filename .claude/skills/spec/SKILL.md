---
description: Write a feature specification (the what and why) to docs/specs/<feature>/spec.md. Use before implementing anything whose scope is unclear or that touches more than about four files, and whenever someone asks for a spec, a design doc, or acceptance criteria.
argument-hint: [feature-name]
---

# Write a feature spec

Feature: `$ARGUMENTS`

A spec records **what** we are building and **why**. It does not record how; that
is the plan (`/plan`). Write the spec first, get it approved, then plan.

## Steps

1. **Interview the user.** Ask until you can answer all four questions. Do not
   guess; a spec built on guesses sends the implementation the wrong way.
   - What problem does this solve, and for whom?
   - What are the acceptance criteria, the observable behaviour that proves it works?
   - What is explicitly out of scope?
   - What is the end-to-end verification step?
2. **Read the existing context** before writing: `docs/decisions/README.md` and
   any relevant record, so the spec does not contradict an `accepted` decision.
3. **Copy the template.** `docs/specs/SPEC_TEMPLATE.md` → `docs/specs/$ARGUMENTS/spec.md`.
   The template is the single source of truth for the section layout; do not
   retype it from memory here.
4. **Fill in every section.** Requirements must be numbered and testable: a
   requirement nobody can check is a wish. Follow `docs/style-guide.md`: plain
   English, active voice, every term of art defined on first use.
5. **Stop and ask for review.** Write no code until the user approves the spec.

## After approval

Run `/plan $ARGUMENTS` to turn the spec into an implementation plan.
