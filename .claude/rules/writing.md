---
# Path-scoped rule: loads whenever an agent touches a Markdown file, so the
# writing rules are in context at the moment prose gets written, not filed
# away in a document nobody opens.
#
# The rules apply to ALL prose, including commit messages, PR descriptions,
# code comments, and error messages, which are not files and cannot be matched
# by a path. Those are covered by the Writing style section of AGENTS.md.
paths:
  - "**/*.md"
  - "**/*.mdx"
  - "**/*.txt"
---

# Writing rules

Full guide: `docs/style-guide.md`. The operative rules are below; apply them
without needing to open it.

The test for every sentence: **could a competent outsider understand it on the
first read?** If not, rewrite it.

## Orwell's six rules

From *Politics and the English Language* (1946):

1. **Never use a metaphor, simile, or figure of speech you are used to seeing
   in print.** "Low-hanging fruit", "move the needle", "paradigm shift": that
   is thinking someone else did. Say the actual thing.
2. **Never use a long word where a short one will do.** *Utilize* → use.
   *Functionality* → feature. *Methodology* → method.
3. **If it is possible to cut a word out, always cut it out.** "In order to" →
   "to". "It should be noted that" → delete.
4. **Never use the passive where you can use the active.** "The file is read by
   the parser" → "The parser reads the file". Passive voice hides *who does
   what*, the one thing technical writing must never hide.
5. **Never use a foreign phrase, a scientific word, or a jargon word if you can
   think of an everyday English equivalent.** Jargon is fine when it is the
   precise term of art (*idempotent*, *mutex*), but only after you define it.
6. **Break any of these rules sooner than say anything outright barbarous.**
   The rules serve clarity; clarity does not serve the rules.

**Orwell's razor:** if a simpler phrasing carries the same meaning, the simpler
phrasing is correct.

## Define your terms

- Define every term of art **on first use**, in one sentence, in place.
- **One name per concept.** If the code says `job`, the docs must not say "task".
- If a document introduces three or more terms, add a Definitions section.
- Never redefine an established term. Pick a new word instead.

## Plain English

- One idea per sentence. Lead with the point, then the reasoning.
- Concrete beats abstract: "retries three times, then drops the message", not
  "implements a robust retry strategy".
- Numbers, not adjectives: "cuts p95 from 800 ms to 120 ms", not "significantly
  faster".
- No hedging filler: delete "basically", "essentially", "arguably". If you are
  genuinely unsure, say what you are unsure about: "untested above 10k rows".
- **British English spelling** (*behaviour*, *summarise*). Quoted text and
  established technical terms (a build *artifact*) keep their conventional
  spelling.
- **No em dashes (—).** Use a comma, a colon, parentheses, or two sentences.
  An en dash is not a fix; hyphens in compound words are fine.

| Avoid | Prefer |
|---|---|
| utilize, leverage | use |
| in order to | to |
| prior to / subsequent to | before / after |
| a number of | some, three, many |
| facilitate | help, enable, or say what it does |
| performant, robust, scalable (bare) | the measurement that shows it |
| it should be noted that | (delete) |

## Before you commit a document

- [ ] Could a competent outsider follow it on the first read?
- [ ] Is every term of art defined on first use, and used consistently?
- [ ] Is every sentence active, and as short as it can be?
- [ ] Is every claim concrete (a number, a behaviour, a file), not an adjective?
- [ ] Are there zero em dashes?
- [ ] Is there a single word you could cut? Cut it.
