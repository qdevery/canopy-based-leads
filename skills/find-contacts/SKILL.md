---
name: find-contacts
description: Find business contacts (named buyers, work emails, office lines) for the top accounts of a canopy-based-leads list using Apollo and/or Clay, cheapest first, behind a credit gate that states the record count and estimated cost and waits for approval. Use after a territory list is built, or when asked to enrich, find decision makers or add contacts to the list.
---

# Find contacts, cheapest first, behind a credit gate

Output is one file: `contacts.csv` in the project folder. `canopy-leads export` merges it into the
workbook (best contact per account), the call sheet and the Clay people table.

## Rules that never bend

- **No spend without a yes.** Before every paid batch, tell the user: how many records,
  which tool, the estimated credits (and the range if a lookup can fall through to a second
  provider), and what they get. Then wait. Report credits actually used after each batch.
  The plugin's hook will also ask before credit-spending tools run; that prompt is a second
  check, not a substitute for telling the user first.
- **Business contacts only.** Work emails and business / office phones. Drop personal
  addresses (gmail, yahoo...), personal cells and home addresses. `canopy-leads export` drops free-mail
  addresses automatically. No skip tracing.
- **No volunteers.** Never look up HOA board members, church volunteers or other private
  individuals. Self-managed associations get their public website / contact form and the
  association's own mailing address only. Districts (MUDs etc.) get their public website and
  operator firm.
- **Never contact anyone.** No emails, sequences, campaigns or CRM records. The hook blocks them.
- **Don't guess emails.** A pattern guess (first.last@) is not a contact. Leave it blank.

## Steps

1. **Shortlist (free).** `canopy-leads shortlist runs/<county> --tiers A` (add `B` if the user wants
   more). It writes `output/contacts/shortlist.csv` and prints an upper-bound estimate.
   Segments with `people_search: false` in `trade.yaml` are excluded by rule.
2. **Match companies (free).** Use Apollo's organization search / lookup to find each
   account's real company and domain (owner LLCs are often operated by a named firm). Record
   the domain. Ambiguous matches go back to the user, not into the file.
3. **Count people (free).** Apollo people search for the segment's `buyer_titles`
   (`trade.yaml`) at the matched companies returns names and titles without spending credits.
   Use the counts to give a precise estimate.
4. **Credit gate → enrich.** Present: "N people at M accounts, ~N Apollo credits (1 per
   person; check your plan), expected work emails for most." Wait for a yes. Enrich in
   batches of ~50 and report credits used and balance after each.
5. **Fill gaps (Clay, optional).** For accounts still missing a buyer, Clay people search
   on the company domain + titles, then its work-email lookup. Run 10 rows first, report the
   real cost per row, then ask before the rest.
6. **Verify (optional, paid).** Email verification on emails that didn't come from a verified
   source. Ask first. Mark results in `email_status`.
7. **Free public sources.** For remaining tier-A gaps, the organization's own website
   (facilities / leadership / contact pages), state facility directories and district
   websites. Office lines and role mailboxes are fine; mark them `contact_type: Office line`.
8. Write `contacts.csv`, run `canopy-leads export runs/<county>`, and summarize: contacts found per
   segment, accounts still missing one, credits used per tool.

## contacts.csv columns

`account_id, account, contact_type (Person | Office line | Operator firm), name, title, company,
business_email, email_status, business_phone, linkedin_url, city, source, found_on`

`account_id` comes from the workbook / shortlist; `source` says where each contact came from
(e.g. "Apollo people match 2026-11-02", "firm website /team page").
