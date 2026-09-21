# Style guide

Plain English, everywhere. This guide applies to everything written in this
repository: README, specs, plans, decision records, diagrams, commit messages,
PR descriptions, code comments, identifiers, error messages, and UI copy.

The test for every sentence: **could a competent outsider understand it on the
first read?** If not, rewrite it.

---

## Orwell's rules

From George Orwell's *Politics and the English Language* (1946). Apply them to
everything you write here:

1. **Never use a metaphor, simile, or figure of speech you are used to seeing
   in print.** Stale phrases ("low-hanging fruit", "move the needle",
   "paradigm shift") are thinking someone else did. Say the actual thing.
2. **Never use a long word where a short one will do.**
   *Utilize* → use. *Functionality* → feature. *Methodology* → method.
3. **If it is possible to cut a word out, always cut it out.**
   "In order to" → "to". "It should be noted that" → delete.
4. **Never use the passive where you can use the active.**
   "The file is read by the parser" → "The parser reads the file".
   Passive voice hides *who does what*, the one thing technical writing
   must never hide.
5. **Never use a foreign phrase, a scientific word, or a jargon word if you
   can think of an everyday English equivalent.** Jargon is fine when it is
   the precise term of art (*idempotent*, *mutex*), but only after you have
   defined it (see below).
6. **Break any of these rules sooner than say anything outright barbarous.**
   The rules serve clarity; clarity does not serve the rules.

**Orwell's razor**, in one line: *if a simpler phrasing carries the same
meaning, the simpler phrasing is correct.*

---

## Define your terms

Undefined terms are where readers get lost and where teams silently disagree.

- **Define every term of art on first use**: one sentence, in place.
  "The worker *hydrates* the cache (loads it from R2 before serving requests)."
- **One name per concept.** Pick a name and use it identically in code, docs,
  commits, and UI. If the code says `job`, the docs must not say "task".
- **Name the concept, not the implementation.** A term should survive a
  refactor.
- **If a doc introduces three or more terms, add a Definitions section** at
  the top. Specs and decision records almost always need one.
- **Never redefine an established term.** If your "session" differs from the
  codebase's existing "session", choose a new word.

---

## Plain-English rules

- **One idea per sentence.** If a sentence needs two commas and a semicolon,
  it is two or three sentences.
- **Lead with the point.** Conclusion first, then reasoning. Readers skim;
  put the thing they came for in the first line.
- **Concrete beats abstract.** "Retries three times, then drops the message",
  not "implements a robust retry strategy".
- **Numbers, not adjectives.** "Cuts p95 latency from 800 ms to 120 ms",
  not "significantly improves performance".
- **No hedging filler.** Delete "basically", "essentially", "quite",
  "somewhat", "arguably". If you are genuinely unsure, say what you are
  unsure about: "untested above 10k rows".
- **One spelling convention.** This repository uses British English
  (*behaviour*, *summarise*). Quoted text, established technical terms
  (a build *artifact*), and the `LICENSE` file keep their conventional
  spelling.
- **Write for the reader who wasn't there.** No unexplained abbreviations,
  no references to conversations or context the reader can't see.

### Words to avoid

| Avoid | Prefer |
|---|---|
| utilize, leverage | use |
| in order to | to |
| prior to | before |
| subsequent to | after |
| at this point in time | now |
| a number of | some, three, many |
| facilitate | help, enable, or say what it does |
| performant, robust, scalable (bare) | the measurement that shows it |
| going forward | from now on, or delete |
| it should be noted that | (delete) |

### No em dashes

The em dash (—) is banned in this repository. It splices loosely related
clauses into one sentence and leaves the relationship between them unstated.
Name the relationship instead:

- Two ideas: write two sentences.
- An explanation or an example follows: use a colon.
- An aside: use parentheses, or cut it.
- A pause: use a comma.

Do not swap in an en dash (–) as a lookalike; pick real punctuation. Hyphens
in compound words (`tool-agnostic`, `hard-to-reverse`) are unaffected.

---

## Applying it

- **Code identifiers**: full words, no cleverness (`retry_count`, not `rc`).
  A name is a definition the reader never has to look up.
- **Comments**: state what the code cannot say (the constraint, the invariant,
  the *why*). Never narrate the *what*.
- **Commit messages**: imperative, present tense, plain. What changed and
  why in the first line.
- **Error messages**: say what happened, what it means, and what to do.
  "Config file not found at ./config.toml. Copy config.example.toml to start."
- **Specs, plans, decision records**: the templates in `docs/` already lead with
  context and decision. Fill them in the same register: short sentences,
  defined terms, active voice.

---

## Checklist

Before committing anything written, ask:

- [ ] Could a competent outsider follow it on the first read?
- [ ] Is every term of art defined on first use, and used consistently?
- [ ] Is every sentence active, and as short as it can be?
- [ ] Is every claim concrete (a number, a behaviour, a file), not an adjective?
- [ ] Are there zero em dashes?
- [ ] Is there a single word or phrase you could cut? Cut it.
