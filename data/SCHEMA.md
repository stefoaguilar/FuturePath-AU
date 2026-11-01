# Opportunity record format (draft v0.1)

Owner: Samer (SAM-01). Stefano (importer) and Hakm (display) need to agree to it before the dataset grows.

The data is a JSON file. One file holds a list of records under `opportunities`. There is an example in `opportunities.template.json`.

## Fields in a record

| Field | Required | What goes in it | Notes |
|---|---|---|---|
| `id` | yes | `OPP-001`, `OPP-002`, and so on | Must be unique. Never reuse an id. |
| `record_type` | yes | `real` or `synthetic` | A synthetic record must also say so in its `title`, for example "[SYNTHETIC] ...". |
| `title` | yes | text | The name the provider uses. |
| `provider` | yes | text | The organisation offering it. |
| `category` | yes | `scholarship`, `internship`, `cadetship`, `graduate_program`, `traineeship`, `course`, `certification`, `mentoring` or `other` | |
| `location` | yes | text | For example `National`, `Adelaide SA`, `Remote`, or `unknown`. |
| `study_level` | yes | `undergraduate`, `postgraduate`, `vocational`, `school_leaver`, `graduate`, `any` or `unknown` | |
| `summary` | yes | one or two plain sentences | Written in our own words. |
| `skills` | no | list of text | Skills or subjects the opportunity relates to. Empty means the page does not say. |
| `source_url` | yes | web address | Use the provider's own page when possible. |
| `eligibility_conditions` | yes | list (see below) | At least one. If the page lists none, add one condition of type `unknown`. |
| `deadline` | yes | object (see below) | |
| `verification` | yes | object (see below) | |
| `data_notes` | no | text | Anything a reviewer should know, such as conflicts or gaps. |

## Eligibility conditions

Each condition is one object in the `eligibility_conditions` list.

| Field | Required | Notes |
|---|---|---|
| `id` | yes | The record id plus `-E1`, `-E2`, and so on. |
| `type` | yes | `education`, `enrolment`, `field_of_study`, `citizenship_residency`, `identity_requirement`, `skill`, `experience`, `age`, `location`, `other` or `unknown` |
| `text` | yes | The condition in plain language, as the student will read it. |
| `evidence_summary` | yes | A short summary of what the official page says. Do not copy long text. |
| `source_url` | yes | The page where the condition is published. |
| `checkable_from_profile` | yes | `true` if a profile field can answer it. `false` if a person has to decide. |

## Deadline

| `status` | `date` | Meaning |
|---|---|---|
| `date` | `YYYY-MM-DD` | The page gives a closing date. |
| `rolling` | `null` | Open all year, with no fixed date. |
| `closed` | optional date | The round is closed. The next round is not announced. |
| `unknown` | `null` | The page gives no date. **Never guess.** |

A deadline can also have a `note`, for example "applications close 11:59pm AEDT", or what the page says about the next round.

### Closed rounds

Use `closed` only when the official page itself says the round is closed. Do not use it because a date has passed (use `date` for that).

1. A `closed` record must have a `note` that says what the page says, including what it says about the next round.
2. `date` on a closed record is optional. If it is there, it is the last closing date, it must be a real date, and it must not be in the future.
3. Never invent the date of the next round. If the page does not give one, the record has no next date.
4. The app shows the record as closed, keeps it out of the "apply now" list, keeps the eligibility conditions visible, and can offer "watch for the next round" with no date.

### How the app works out the deadline state

The app works this out from the reference date (28 November 2026 for the demo). It never reads the real clock for this.

| Record | State shown |
|---|---|
| `date`, on or after the reference date | future (closing soon if within a few days) |
| `date`, before the reference date | past |
| `closed` (with or without a date) | past, shown as closed |
| `rolling` | open all year |
| `unknown` | unknown, no date shown |

## Verification

| Field | Notes |
|---|---|
| `verified_on` | The date (`YYYY-MM-DD`) someone last checked the record against the official page. For a record that was only imported from a team CSV, it is the CSV's date. In that case `method` must say it was imported and not checked. |
| `status` | `verified`, `needs_recheck`, `conflicting` or `synthetic` |
| `method` | A short sentence saying how it was checked, for example "The official page was saved as a PDF and compared with the record." |

## What the validator checks

`scripts/validate_dataset.py` checks that every required field is there and has the right type (text, list, true/false, date), that words come from the allowed lists, that deadlines follow the rules above, and that the test scenarios use the profile field names from `PROFILE_MAPPING.md`.

## Rules for the data

These come from the project guide.

1. If something is missing, write `unknown`. Never guess, and never treat it as "not eligible".
2. The system never works out an `identity_requirement` condition (for example, a program for Aboriginal and/or Torres Strait Islander people). These are always `checkable_from_profile: false`. The student confirms them, or the result stays uncertain.
3. No suitability score based on identity. Conditions only describe what the provider published.
4. A real record needs an official `source_url` and a `verified_on` date. Anything else must be `synthetic` and labelled.
5. No personal data about real people anywhere in `data/`.

## Questions that were open

- Stefano: is nested JSON OK for the importer? **Answered: yes, no need to convert it to CSV.**
- Hakm: do the cards need any extra fields, such as a logo or a short tag list? **Still waiting for an answer.**
- Everyone: should the date of a closed round be kept for display? **Yes. The validator allows it, and checks that it is a real date that is not in the future.**
- Stefano and Hakm: the table above gives `rolling` its own state, "open all year". Is that OK, or do you want rolling shown as "unknown"? **Still waiting for an answer.**
