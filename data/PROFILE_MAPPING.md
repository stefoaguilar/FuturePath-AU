# How conditions are matched to profile fields (draft)

I wrote this for Stefano (eligibility rules) and Hakm (profile form).
It is a proposal. You own the profile fields, so please change any name that does not match what you are building. If you rename a field, tell me and I will change the scenarios and the validator to match.

## The three results

Each condition ends up as one of these:

- **satisfied**: the profile has a value and it meets the condition.
- **unmet**: the profile has a value and it clearly does not meet the condition.
- **uncertain**: everything else. This is the default.

If information is missing, the result is **uncertain**. It is never unmet.

## The profile fields (one list)

These are the only profile field names. The test scenarios use exactly these names, and the validator checks it.
A field that is missing, empty or `not_stated` counts as "no information", so the result is uncertain.

| Field | Type | Allowed values |
|---|---|---|
| `education_level` | text | `undergraduate`, `postgraduate`, `vocational`, `school_leaver`, `graduate`, `not_stated` |
| `enrolment_status` | text | `enrolled_full_time`, `enrolled_part_time`, `commencing`, `not_enrolled`, `not_stated` |
| `institution` | text | Any text, for example `Curtin University` |
| `citizenship_status` | text | `australian_citizen`, `permanent_resident`, `nz_citizen`, `other`, `not_stated` |
| `state` | text | `ACT`, `NSW`, `NT`, `QLD`, `SA`, `TAS`, `VIC`, `WA`, `not_stated` |
| `field_of_study` | text | Any text, for example `cyber security` |
| `weighted_average` | number | Optional. Only if the student chooses to enter it. |
| `skills` | list of text | Tags from the skill list at the end of this file, or the student's own words |
| `experience_notes` | text | Free text |
| `preferred_agencies` | list of text | Optional. For example `["Defence"]`. Used for conditions such as "list Defence as a preferred agency". |
| `identity_answer` | text | `yes`, `no`, `prefer_not_to_say`, `not_stated`. The student's own answer. Never worked out by the app. |

The student's goal (for example "entry-level cyber job") is a separate input. It is not part of the profile.

## The mapping

| Condition type | Profile field | How it is checked |
|---|---|---|
| `citizenship_residency` | `citizenship_status` | Compare it with what the page allows. `not_stated` gives uncertain. |
| `enrolment` | `enrolment_status` and `institution` | Compare it with what the page asks for. If the page names one university and the profile has another, that is unmet. If the institution is blank, it is uncertain. |
| `education` | `education_level`, and `weighted_average` only if the student chooses to enter it | Compare it with the minimum on the page. No value gives uncertain. |
| `field_of_study` | `field_of_study` | Compare it with the list on the page. If the course is not on the list, it is uncertain, because lists are often incomplete. |
| `skill` | `skills` (tags from the list below) | The skill gap is the skills the opportunity lists that the profile does not mention. Show it as "not mentioned in your profile". Never say the student lacks the skill. |
| `experience` | `experience_notes` (free text) | Always uncertain. A person reads it. |
| `location` | `state` | Compare it with the state on the page. No value gives uncertain. |
| `age` | none | Always uncertain. I suggest we do not collect age. |
| `identity_requirement` | `identity_answer` (only the student's own answer) | **Never worked out and never scored.** The app shows the wording from the page and lets the student answer (yes, no, or prefer not to say). Until they answer, it stays uncertain. |
| `other` | `preferred_agencies`, only when the condition is marked `checkable_from_profile: true` (for example OPP-001-E2) | Compare the list with the agency named on the page. Empty gives uncertain. Other `other` conditions are always uncertain. |
| `unknown` | none | Always uncertain. Show the text and the source link. |

## Rules

1. If `checkable_from_profile` is `false`, the result is **uncertain** until a person confirms it.
2. A condition is only **unmet** when the profile has a value that clearly goes against the condition.
3. No suitability score. No ranking by identity. The app only lists which conditions are satisfied, unmet or uncertain.
4. Every result shows the condition's `evidence_summary` and `source_url`, so the student can check the page.
5. An empty `skills` list means "no skills published". It does not mean "no skills needed".

## What the data looks like now

- There are 81 conditions across the 30 records.
- 27 of them are marked `checkable_from_profile: true`. The rest need a person.
- 12 are identity conditions. They can never be checked by the app.
- 28 of the 30 records were checked against the official page. So fewer results will be uncertain than before, but many will still be uncertain. That is correct, not a bug.

## Skill tags in use

`cyber security`, `technology`, `ICT`, `software engineering`, `digital`, `STEM`, `data`,
`digital delivery`, `computing`, `data science`, `networking`, `cybernetics`.

Tags are lower case except `ICT` and `STEM`. The importer should match them exactly.
If you would rather use a fixed list, tell me and I will change the data to match.
7 of the 30 records have no skills listed, because their pages do not say.
