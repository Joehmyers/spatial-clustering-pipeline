# spatial-clustering-pipeline

Draws candidate **National Climate Areas** (NCAs) for the AA from weather
alone, then tests on data kept back from the build whether they beat the map in
use today.

The AA splits the UK into NCAs, each made of **Patrol Group Areas** (PGAs),
each made of **Rostering Areas** (RAs). Demand forecasts run per NCA, so an NCA
works best when the places inside it feel the same weather on the same day.

This pipeline clusters roughly 250 DTN virtual weather points into a tree,
maps the clusters onto whole PGAs, and reports whether the result is more alike
inside and more different between than today's map, at the same count.

**It is built from weather and judged on demand.** Demand never reaches the
build: if it helped draw the map, measuring the map on demand would measure how
well it was fitted, not how well it works. Two guardrails enforce that in code
rather than by trust ([D-0003](docs/decisions/D-0003-build-the-weather-map-from-weather-alone.md)).

---

## Run it

```bash
ops/setup.sh    # install the package and its test tools
ops/check.sh    # lint and tests: the one command that says whether this is green

SETTINGS=tests/fixtures/nca-regionalisation/settings.toml
nca run all --settings $SETTINGS --out runs/fixture
```

That runs all seven stages on a committed fixture with a planted answer, and
writes the maps, charts and a one-page summary to `runs/fixture/report/`. It
needs no network: no live data, no web basemaps.

To run one stage on its own, name it. It reads the earlier stages' saved
outputs from the same folder:

```bash
nca run cluster --settings $SETTINGS --out runs/fixture
```

The real inputs are described by their expected shape and wired to settings,
but not connected. A run with `data_source = "real"` stops and says what shape
it expects, rather than guessing at a schema nobody confirmed.

---

## The seven stages

Each reads the saved outputs of the stages before it and saves its own, so any
stage can rerun alone. Full picture in
[`docs/diagrams/system-diagram.md`](docs/diagrams/system-diagram.md).

| Stage | What it does |
| --- | --- |
| **geometry** | Reads the NCA, PGA and RA layers, moves them into British National Grid, repairs broken shapes, and checks they nest, both by ID column and by overlay |
| **graph** | Builds Voronoi cells round the weather points (the ground nearer one point than any other), clips them to the area the AA serves, and treats two points as neighbours when their cells share an edge of at least a metre |
| **features** | Turns raw weather into each point's departure from the country that day: transform, subtract the point's smoothed seasonal normal, subtract the day's national mean, then z-score |
| **cluster** | Grows Ward's tree over the neighbour graph, so every cluster is contiguous, and cuts it by merge order for each count asked for |
| **mapping** | Gives each PGA the cluster holding most of its area, scores how far it straddles a boundary, and moves any PGA its new NCA left stranded |
| **evaluate** | The only stage that reads demand. Compares today's map with the new one on the held-out window |
| **report** | Five maps, the tree with the cut marked, two charts and a one-page summary |

---

## The guardrails

The method's fairness rests on four rules, so tests and run-time checks enforce
them rather than trusting whoever runs the code.

| Rule | What it means | Where |
| --- | --- | --- |
| **Demand firewall** | Only the evaluate stage can read demand. A read from anywhere else fails, and a test fails if a build stage even mentions the reader | `src/nca/inputs.py`, `tests/test_firewall.py` |
| **Sealed window** | Data from 1 September 2025 on is blocked. Reaching it needs an override, and every run records that it was used | `src/nca/inputs.py`, `tests/test_sealed_window.py` |
| **No leakage** | Seasonal normals and z-score parameters come from the build window alone and are stored. Changing held-out weather leaves the tree and the labels unchanged | `src/nca/features.py`, `tests/test_leakage.py` |
| **Reproducible runs** | Every run records its settings, the commit, whether the tree was dirty, library versions, the random seed and a log. The same inputs give identical outputs, figures included | `src/nca/runrecord.py`, `tests/test_determinism.py` |

---

## Repository layout

```
spatial-clustering-pipeline/
├── AGENTS.md                 # Agent context; CLAUDE.md is a one-line import of it
├── src/nca/                  # One module per stage, plus settings, inputs, outputs, run record
├── tests/                    # One test file per stage, plus the cross-cutting ones
│   └── fixtures/             # The fixture set, with a README explaining its formulas
├── ops/                      # check.sh (the one verification command), setup.sh, R2 scripts
├── docs/
│   ├── specs/                # nca-regionalisation/spec.md: the what and why
│   ├── plans/                # nca-regionalisation.md: the how, and the library choices
│   ├── decisions/            # The durable why, numbered D-0001 and up
│   ├── diagrams/             # The stage flow and the guardrails, in Mermaid
│   └── style-guide.md        # Plain English, Orwell's rules, every term defined
└── .github/workflows/ci.yml  # Runs ops/check.sh on every pull request
```

---

## One verification command

```bash
ops/check.sh          # shell syntax, shellcheck, lint, tests
ops/check.sh --strict # also fails on unconfigured steps and warnings
```

Agents, humans and CI all run this same script, so nothing can pass locally and
fail in CI because of a command someone forgot to keep in sync. There is no
build step: this is a pure Python package that `ops/setup.sh` installs in place.

---

## Writing standard

All prose here follows [`docs/style-guide.md`](docs/style-guide.md): plain
English, Orwell's rules, active voice, British spelling, every term of art
defined on first use. The test for every sentence: could a competent outsider
understand it on the first read?

---

## License

[MIT](LICENSE).
