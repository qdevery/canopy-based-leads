---
description: Run the territory-gtm demo on a synthetic county and walk through what it produced
argument-hint: "[folder, default runs/demo]"
---

Run the territory-gtm demo and explain the results.

1. If `tgtm` isn't installed, set it up as in the `build-territory-list` skill (venv + pip install of the repository root, two folders above that skill's base directory).
2. Run `tgtm demo ${ARGUMENTS:-runs/demo}`. It is offline and takes about a minute.
3. Walk the user through, briefly and in order: the checkpoint files in `output/checkpoints/`, the workbook tabs (Summary, a segment tab, Management Companies, Contacts, Method), `call_sheet_top50.md`, `clay/`, `contacts/shortlist.csv` with its credit estimate, and the storm alert in `output/alerts/`.
4. Point out that every name is invented, that one personal gmail address in the demo contacts was dropped on purpose (business contacts only), and that nothing was sent or spent.
5. Offer to build a real county next (`/territory-gtm:build`).
