---
name: add-trade
description: Adapt canopy-based-leads to another field-service trade (landscaping, roofing, paving, irrigation, pest control, pressure washing...) by writing a trade.yaml with its own segments, fit, score weights, buyer titles and outreach angles. Use when someone wants a territory list for a trade other than tree care.
---

# Add a trade

Copy `src/canopy_leads/configs/trades/tree_care.yaml` (repository root = two folders above
this skill) and change what differs. Everything about a trade lives in that one file.

## Interview the user (5 questions)

1. Which property types buy this work, and which buy the most of it?
2. Who signs the contract at each (title)? Who influences it?
3. What makes a property a better prospect: acreage, building size, tree cover, age, storm
   exposure, number of sites under one buyer?
4. What is the smallest property worth a visit?
5. What is the seasonal or event hook (pre-storm season, spring cleanup, budget season)?

## What to change

- `id`, `name`.
- `segments`: keep, drop or add. Each needs `label`, `fit` (0–1), `unit`, `buyer_titles`,
  `angle`, and `people_search: false` for any segment run by volunteers or public bodies.
  Angle templates can use `{name} {properties} {acres} {canopy_acres} {storm_hook} {sites}
  {area} {operator}`.
- `rules`: usually reusable; add rules for new segments using tags and keywords. A new
  segment id must appear in `segments`.
- `score`: set `canopy.points: 0` when trees don't matter (roofing, paving), raise
  `storm.points` for storm-driven work (roofing after hail: add a hail event in county.yaml
  with `method: nearest_report` and `typecodes: [H]`), raise `acreage.points` for
  acreage-priced work (mowing). Keep the points summing to 100.
- `filters.min_acres`: the smallest property worth a visit.
- `contact_titles`: regexes for the buyer titles, best first.

## Test

```bash
canopy-leads init runs/<county>-<trade> --county <county> --trade path/to/trade.yaml
canopy-leads run runs/<county>-<trade>
```

Read the top 20 accounts and their angles with the user. If the ranking feels wrong, adjust
`fit` and `score` and rerun from `score` (`canopy-leads run ... --from score`).
