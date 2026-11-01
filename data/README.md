# data folder

This folder holds the opportunity data for FuturePath AU. It covers my tasks SAM-01 to SAM-06.

## What is in here

| File or folder | What it is |
|---|---|
| `opportunities.json` | The main data file. It has 30 real records. 28 of them were checked against the official page. |
| `source_verification_notes.csv` | One row per record. It says who checked it, when, and what was changed. |
| `PROFILE_MAPPING.md` | A draft of how each condition is matched to a field in the student's profile. Stefano and Hakm need to confirm it. |
| `source/` | The files the build script used: two team CSV files and my hand-read records. |
| `scripts/` | Three small Python scripts. See below. |

The record format is in `SCHEMA.md`, and there is an example in `opportunities.template.json`. Both are in this folder in the repository.

## The scripts

Run them from this folder.

| Command | What it does |
|---|---|
| `python scripts/validate_dataset.py` | Checks the data file and the test scenarios against the rules (required fields, types, deadlines, profile field names). Run this after every change. |
| `python scripts/freshness_check.py --today 2026-11-28` | Lists records with a passed deadline, no deadline, or an old check. It saves a report in `reports/`. |
| `python scripts/build_dataset.py` | Built the data file from the CSVs. **Do not run it again.** It would overwrite the hand-checked records. |

## The demo date

The demo date is **28 November 2026**. The scripts and tests use it as "today". If the date changes, only the date setting needs to change. No date is written into the app code.

## Tests

The test scenarios are in `tests/synthetic_scenarios.json`. The test log is in `docs/JOURNEY_TESTS.csv`. The scenarios are made up and labelled synthetic. Nothing here is real student data.

## How a record is checked

1. I open the official page and save it as a PDF.
2. Each condition and date in the record is compared with the PDF.
3. If they match, the record is marked `verified`. If not, I fix the record or leave it flagged.

Two records are still flagged on purpose:
- **OPP-002 (UNSW):** its page says the round is closed and gives no closing date.
- **OPP-005 (UNE):** its page is out of date.

## Rules I follow

- If a page does not say something, I write `unknown`. I never guess.
- A passed deadline is shown as closed. A missing deadline is shown as unknown.
- Identity conditions, such as being Aboriginal or Torres Strait Islander, are shown as written. The app never works them out and never scores them.
