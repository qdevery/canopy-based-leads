---
description: Build a ranked account list for a county and trade from public data
argument-hint: "<county, state> [trade]"
---

Build a territory account list for: $ARGUMENTS

Follow the `build-territory-list` skill end to end: state the ground rules, set up `tgtm`, confirm the county and trade (use `add-county` / `add-trade` if they aren't bundled), fetch, and stop at each checkpoint for the user's review. Do not research contacts or spend any credits in this command; offer the `find-contacts` skill at the end.
