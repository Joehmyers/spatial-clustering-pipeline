# CLAUDE.md

Claude Code reads this file automatically at the start of every session, but it
does **not** read `AGENTS.md` natively. The canonical, tool-agnostic agent
instructions for this repository live in `AGENTS.md`; the import below pulls them
into Claude Code's context so every tool shares one source of truth.

Put anything Claude-specific below the import. Keep the shared instructions in
`AGENTS.md`.

@AGENTS.md
