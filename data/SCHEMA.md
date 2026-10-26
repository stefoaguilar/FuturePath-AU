# Opportunity record schema (draft v0.1)

Owner: Samer (SAM-01). Needs sign-off from Stefano (importer, STE-01) and Hakm (display, HAK-03) before the dataset grows.

File format: JSON. One file holds a list of records under `opportunities`. See `opportunities.template.json`.

## Fields

| Field | Required | Allowed values / format | Notes |
|---|---|---|---|
| `id` | yes | `OPP-001`, `OPP-002`, ... | Unique. Never reused. |
| `record_type` | yes | `real` or `synthetic` | Synthetic records must also say so in `title` (e.g. "[SYNTHETIC] ..."). |
| `title` | yes | text | As published by the provider. |
| `provider` | yes | text | Organisation offering it. |
| `category` | yes | `scholarship`, `internship`, `cadetship`, `graduate_program`, `traineeship`, `course`, `certification`, `mentoring`, `other` | |
| `location` | yes | text | e.g. `National`, `Adelaide SA`, `Remote`, or `unknown`. |
| `study_level` | yes | `undergraduate`, `postgraduate`, `vocational`, `school_leaver`, `graduate`, `any`, `unknown` | |
| `summary` | yes | 1-2 plain sentences | Written in our own words. |
| `skills` | no | list of text | Skills or knowledge areas the opportunity relates to. |
| `source_url` | yes | official URL | Prefer the provider's own page. |
| `eligibility_conditions` | yes | list (see below) | At least one, or one `unknown` entry if none are published. |
| `deadline` | yes | object (see below) | |
| `verification` | yes | object (see below) | |
| `data_notes` | no | text | Conflicts, gaps, anything a reviewer should know. |

### eligibility_conditions (one object per condition)

| Field | Required | Notes |
|---|---|---|
| `id` | yes | `<record id>-E1`, `-E2`, ... |
| `type` | yes | `education`, `enrolment`, `field_of_study`, `citizenship_residency`, `identity_requirement`, `skill`, `experience`, `age`, `location`, `other`, `unknown` |
| `text` | yes | Plain-language condition shown to the user. |
| `evidence_summary` | yes | Paraphrase of what the official page says. Short; do not copy long text. |
| `source_url` | yes | Page where the condition is published. |
| `checkable_from_profile` | yes | `true` if a profile field can answer it, `false` if a person must judge it. |

### deadline

| `status` | `date` | Meaning |
|---|---|---|
| `date` | `YYYY-MM-DD` | A published closing date. |
| `rolling` | `null` | Open all year / no fixed date. |
| `closed` | optional date | Round is closed; next round not announced. |
| `unknown` | `null` | The page does not state a date. **Never guess.** |

The `deadline` object may also hold an optional `note` (text), for example "applications close 11:59pm AEDT" or what the page says about the next round.

### verification

| Field | Notes |
|---|---|
| `verified_on` | `YYYY-MM-DD` date the record was last checked. For records imported from a team CSV this is the CSV's date, and `method` must say it was imported and not checked against the official page. |
| `status` | `verified`, `needs_recheck`, `conflicting`, `synthetic` |
| `method` | Short text, e.g. "Read official page". |

## Rules for the data (agreed principles from the project guide)

1. Missing information is recorded as `unknown`, never guessed and never treated as ineligible.
2. `identity_requirement` conditions (for programs that publish an Aboriginal and/or Torres Strait Islander requirement) are never inferred by the system. They are marked `checkable_from_profile: false` and handled as user-confirmed or uncertain.
3. No suitability scoring from identity. Conditions only describe what the provider publishes.
4. Real records need an official `source_url` and a `verified_on` date. Anything else is `synthetic` and labelled.
5. No personal data about real people anywhere in `data/`.

## Open questions for Stefano / Hakm

- Stefano: is nested JSON OK for the importer, or do you want flat CSV (one row per condition)?
- Hakm: do the cards need any extra fields (e.g. logo, short tag list)?
- All: should `deadline.date` for closed rounds be kept for display?
