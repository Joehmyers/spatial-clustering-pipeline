# Fixture: NCA regionalisation

A made-up map and two years of made-up weather with a planted answer, so the
whole pipeline can run end to end and be checked against something known.
Follows the rules in [`../README.md`](../README.md): every file is text, under
100 KB, made up, ISO dates, dot decimals, no absolute paths.

**Nothing here is random.** Every value comes from sums of sine waves of fixed
period, written by `src/nca/fixture.py`. Regenerate the set with:

```bash
nca fixture --out tests/fixtures/nca-regionalisation
```

`tests/test_fixture.py` regenerates it and compares byte for byte, so the files
cannot drift from the formulas without a test failing.

## The map

Sixteen weather points on a 4 by 4 grid at 25 km spacing, over a 100 km square
of land, plus two points off it.

| Point | Where | What it is for |
| --- | --- | --- |
| `P01` to `P16` | The grid, numbered from the south-west, row by row | The clustering unit |
| `P17` | Far to the south-east, in open sea | Its clipped cell is empty, so the graph must drop it |
| `P18` | On a 10 km island to the east | Its cell shares no edge with the mainland, so the graph reaches it only through the manual link `P18`-`P12` |

The land splits into eight RAs, which group into four PGAs (north-west,
north-east, south-west, south-east), which group into two "current" NCAs
running north and south. The island belongs to `RA-NE-1`, which makes that RA,
its PGA and its NCA two-part shapes on purpose.

The 16 grid cells tile the land exactly, so the neighbour graph is a 4 by 4
lattice: 24 edges. The diagonals touch at a single corner and are **not**
neighbours, which is what the "shared edge of at least 1 metre" rule is for.

## The weather

Daily minimum and maximum temperature, rain and wind, from 1 September 2023 to
31 August 2025, one file per variable in `weather/`, one row per day and one
column per point, to one decimal place. Each value is:

```
base + season + national swing + regime swing + the point's own wobble
```

| Term | Period | What it does |
| --- | --- | --- |
| Season | 365.25 days | The annual cycle, warmest in mid-July. The seasonal normal removes it |
| National swing | 97 days | The same at every point, so removing each day's mean across points removes it exactly |
| Regime swing | 53 days | **The planted answer.** Plus at every eastern point, minus at every western one |
| The point's own wobble | 29 days, phase shifted 7 days per point | Small, so points inside one half are alike but not identical. Without it, z-scoring would make them identical and the merge order would be a coin toss |

The regime swing is six to seven times the size of the wobble, so west and east
separate cleanly. The island carries the eastern swing.

Three awkward cases are planted deliberately:

| Case | Where | What it exercises |
| --- | --- | --- |
| Leap day | 29 February 2024 | It must use 28 February's normal (R2) |
| A spell of zero rain | 1 to 14 July 2024, every point | `log(1 + x)` on zeros |
| One missing reading | `P07`, `tmax`, 15 March 2024 | The missing-data setting. The fixture settings say `drop_day`, so that date goes at every point and variable, and the run records it |

## Demand

`demand.csv` holds a daily percentage deviation per PGA, following the same
53-day west and east swing. Today's north and south map pairs a western PGA
with an eastern one in each NCA, so it explains almost none of that swing. The
planted map explains nearly all of it. Only the evaluate stage may read this
file (R12).

## The expected answer

`cluster-labels-k2.expected.csv` holds the planted labels at k = 2: the eight
western grid points in cluster `P01`, the eight eastern ones and the island in
cluster `P03`. Clusters take the name of the smallest point ID they hold. The
offshore point `P17` is absent, because the graph drops it before the tree.

`tests/test_cluster.py` compares the run's labels with this file exactly.
