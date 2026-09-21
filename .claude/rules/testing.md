---
# Path-scoped rule: applies whenever an agent touches files matching the paths below.
# Remove or update the `paths` frontmatter to change the scope.
paths:
  - "tests/**"
  - "**/*.test.*"
  - "**/*.spec.*"
---

# Testing rules

The same rules live in the Testing section of `AGENTS.md`; keep the two lists
identical.

- NEVER modify a test to make it pass; fix the implementation instead.
- NEVER mock a module that exists in this repo; test it directly.
- Every test asserts a concrete outcome. A test that cannot fail is not a test.
- Write the test before the implementation when the file does not exist yet.
- Run `ops/check.sh` after every implementation change to catch regressions.
