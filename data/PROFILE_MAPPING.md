# How conditions are matched to profile fields (draft)

I wrote this for Stefano (eligibility rules) and Hakm (profile form).
It is a proposal. You own the profile fields, so please change any name that does not match what you are building.

## The three results

Each condition ends up as one of these:

- **satisfied**: the profile has a value and it meets the condition.
- **unmet**: the profile has a value and it clearly does not meet the condition.
- **uncertain**: everything else. This is the default.

If information is missing, the result is **uncertain**. It is never unmet.

## The mapping

| Condition type | Profile field | How it is checked |
|---|---|---|
| `citizenship_residency` | `citizenship_status` (`australian_citizen`, `permanent_resident`, `nz_citizen`, `other`, `not_stated`) | Compare it with what the page allows. `not_stated` gives uncertain. |
| `enrolment` | `enrolment_status` (`enrolled_full_time`, `enrolled_part_time`, `commencing`, `not_enrolled`, `not_stated`) and `institution` | Compare it with what the page asks for. If the page names one university and the profile has another, that is unmet. If the institution is blank, it is uncertain. |
| `education` | `education_level`, and `weighted_average` only if the student chooses to enter it | Compare it with the minimum on the page. No value gives uncertain. |
| `field_of_study` | `field_of_study` | Compare it with the list on the page. If the course is not on the list, it is uncertain, because lists are often incomplete. |
| `skill` | `skills` (tags from the list below) | The skill gap is the skills the opportunity lists that the profile does not mention. Show it as "not mentioned in your profile". Never say the student lacks the skill. |
| `experience` | `experience_notes` (free text) | Always uncertain. A person reads it. |
| `location` | `state` | Compare it with the state on the page. No value gives uncertain. |
| `age` | none | Always uncertain. I suggest we do not collect age. |
| `identity_requirement` | none | **Never worked out and never scored.** The app shows the wording from the page and lets the student answer (yes, no, or prefer not to say). Until they answer, it stays uncertain. |
| `other`, `unknown` | none | Always uncertain. Show the text and the source link. |

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
