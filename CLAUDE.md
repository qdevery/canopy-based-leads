# canopy-based-leads

Python pipeline (`src/canopy_leads/`, CLI `canopy-leads`) plus a Claude Code plugin (`skills/`,
`commands/`, `hooks/`, `.claude-plugin/`) that turns a county tax roll into a ranked account
list for a field-service company.

- To build a list, follow `skills/build-territory-list/SKILL.md`. Contacts:
  `skills/find-contacts/SKILL.md`. New county: `skills/add-county/SKILL.md`. New trade:
  `skills/add-trade/SKILL.md`. Storm alerts: `skills/storm-alerts/SKILL.md`.
- Ground rules: research and files only (no sends, sequences or CRM writes); public data only;
  business contacts only, never volunteers or board members; state the count and credit
  estimate and wait for approval before any paid enrichment; never guess a missing value.
- Projects live in `runs/` (git-ignored). Never commit raw county data, contacts or lead lists.
- Test: `pip install -e ".[test]" && pytest` (runs the offline demo).
- County- and trade-specific facts belong in YAML (`src/canopy_leads/configs/`), not code.
