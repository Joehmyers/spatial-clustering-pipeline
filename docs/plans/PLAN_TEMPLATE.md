# Plan: <Feature name>

> **Status:** Draft | Approved | In Progress | Done

Spec: [docs/specs/\<feature\>/spec.md](../specs/<feature>/spec.md) _(if applicable)_

## Overview

<!-- One paragraph summarising the implementation approach. -->

## Steps

- [ ] 1. <!-- Concrete action: file to create/edit, function to add/change -->
- [ ] 2. ...
- [ ] 3. Write / update tests for the above
- [ ] 4. Run `ops/check.sh`; fix any failures
- [ ] 5. Commit: `<imperative commit message>`

## Files changed

| File | Change |
|------|--------|
| `src/<file>` | <!-- what changes --> |
| `tests/<file>` | <!-- what tests are added --> |

## Verification

<!-- ops/check.sh is the baseline; add any feature-specific end-to-end command. -->

```bash
ops/check.sh
# e.g. plus: curl localhost:8080/health
```

---

_Related spec: [docs/specs/\<feature\>/spec.md](../specs/<feature>/spec.md)_
