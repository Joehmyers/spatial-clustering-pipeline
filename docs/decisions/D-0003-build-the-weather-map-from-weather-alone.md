---
status: "accepted"
date: 2026-09-21
decider: [Joehmyers]
tags: [clustering, weather, evaluation, regionalisation]
supersedes: []
superseded: null
---

# D-0003. Build the weather map from weather alone

## Context

The AA splits the UK into National Climate Areas (NCAs), each made of Patrol
Group Areas (PGAs), each made of Rostering Areas (RAs). Demand forecasts run
per NCA, so an NCA works best when the places inside it feel the same weather
on the same day.

We want to draw candidate NCAs and then say whether they are better than the
ones in use. "Better" means the places inside an NCA are more alike, and the
NCAs are more different from each other, than today's map at the same count.
Demand is what NCAs exist to forecast, so demand is the test that matters.

That puts a constraint on the build. If demand helps draw the map, then
measuring the map on demand measures how well it was fitted, not how well it
works. The same goes for the current NCA, PGA and RA labels: a map built from
them would inherit whatever was right and wrong about past operational
choices, and comparing it with them would be close to comparing them with
themselves.

The clustering unit is another version of the same question. Clustering RAs or
PGAs would bake today's boundaries into the answer before the first merge.

## Options

- **Cluster the roughly 250 DTN virtual weather points, on weather only.**
  Map the resulting clusters onto whole PGAs afterwards.
- **Cluster PGAs directly on their average weather.** Fewer units, no mapping
  step, and the output is operational from the start.
- **Cluster on a demand-weighted weather index**, so places that generate more
  breakdowns pull harder on the boundaries.

## Decision

We will cluster the DTN virtual points on weather alone, and map the clusters
onto whole PGAs afterwards.

The build reads daily minimum and maximum temperature, rain and wind (plus
snow where DTN has it), turns each into a departure from that point's own
smoothed seasonal normal, removes each day's national mean, and z-scores each
point and variable using build-window values only. It sees no demand, no
breakdown weights, and no current NCA, PGA or RA labels.

The operational layers enter the build in one way only: their dissolved
outline, used to clip Voronoi cells to the area the AA serves. That is
geometry, not labels.

Two rules enforce this rather than trusting whoever runs the code:

- **The demand firewall.** Every input comes through one reader, built for one
  named stage. Only the evaluate stage's reader returns demand; every other
  one raises. A test fails if a build stage even mentions the demand reader.
- **The sealed window.** Data from 1 September 2025 on is blocked in code,
  and reaching it needs an override that every run records.

The mapping rule stays area majority. A breakdown-weighted majority would
bring demand into the build through the back door.

## Consequences

- **Benefits:** the demand test is independent, so a good result means the
  weather map works rather than that it was fitted. The map owes nothing to
  past operational choices, so it can disagree with them usefully. Clustering
  points rather than PGAs keeps the weather map separate from today's
  boundaries, which also gives each PGA a straddle score saying how far it
  sits across a weather boundary.
- **Costs:** a mapping step is needed, and it can strand a PGA, which then has
  to be moved and the move recorded. The clusters cannot be judged directly as
  an operational map; the ceiling measure exists to say how much of the
  RA-level variance any map of whole PGAs could ever reach. Places with heavy
  demand get no extra say in where boundaries fall, which is the price of the
  test being worth anything.
- **If this changes:** bringing demand into the build means the demand
  comparison stops being evidence. Anyone proposing it should say what would
  replace it as the test, and write a new record superseding this one.
