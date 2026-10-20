# Ideal data set (comparison baseline)

The same seven hypothetical borrowers, the same 26 files and the same layouts as `seed/sample-files`,
with the data put right: every value correct, complete, current and consistent across sources.
Upload it instead of the fragmented set to see what Data360 reports when the data is not the problem.
All values are hypothetical. Regenerate with `python3 seed/make_ideal.py`.

## What is different

| | Fragmented (`sample-files`) | Ideal (`ideal-files`) |
|---|---|---|
| External records | Several per source, with history rows, duplicates and provider defect flags | One current record per source, validated, high confidence |
| Values across sources | Revenue, rating, registry status, facility, maturity and other fields disagree | Every source agrees with the reference value |
| Dates | Some extracts 15+ months old | Every extract inside its feed's refresh cycle |
| "Data Quality Defects" sheets | Listed defects | Empty |
| Internal dictionaries | Option lists ("Term loan / RCF / Bridge"), placeholders ("Name", "ISIN"), different values per record | One real value; identity and memo elements match the external sources |
| Coverage | Some borrowers lack whole categories (for example HarbourVest has no Legal systems entity records) | Every borrower has every category each system holds |
| Client identity | No LEI, Tax ID, incorporation date, segment or listing status | Held in CRM for every borrower |
| Credit state | Random noise: Chapter 11 proceedings, stage 3, missed-payment news, covenant breaches for borrowers the external sources show as performing | Matches the external truth: performing, stage 1, internal grade mapped from the external rating, no proceedings or breaches |
| Vendor CSV | Different names ("HarbourVest Inc.") and numbers | Same names and numbers as everything else, plus rate and margin |

Credit facts that are real stay real: Haneda is still BB+, every LTV is calculated from drawn ÷ collateral, and the memo still lists conditions.

## Result in Data360 (Assess before Clean, reference date 2026-10-09)

| Dimension | Fragmented (average of 7) | Ideal |
|---|---|---|
| Completeness | 83 | 96 |
| Accuracy | 57 | 100 |
| Consistency | 67 | 100 |
| Validity | 98 | 100 |
| Timeliness | 86 | 100 |
| Usage | 80 | 86 |
| Business relevance | 92 | 100 |
| **Data confidence** | **78–82** | **97** |
| Seeker attributes found | 3–5 of 13, 1–3 conflicts | 11 of 13, no conflicts |
| Draft memo decision | Refer (1–6 hard policy failures) | Approve With Conditions |

Why the ideal set is not 100:

- **SIC / NAICS code and Website** are never held as such; the Seeker reports them as "partly found" (internal industry code, email domain). That is a real gap in what the bank captures, not bad data.
- **Usage**: External news, Treasury systems and Physical records hold nothing the golden record or the memo reads. That is a governance question (connect them or stop sourcing), not a quality defect.
- **Approve With Conditions**: standard conditions remain, such as verifying the board resolution and quarterly covenant certificates.

## How to compare

1. Users & audit → Start again → delete uploaded files too (or use a fresh database).
2. Upload everything in `ideal-files` (internal, external, other-layouts).
3. Run Phase 1 for a borrower and compare it with the same borrower on the fragmented set: Assess barely changes after Clean, the Seeker has no conflicts and the fix plan is nearly empty.
