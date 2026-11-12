
# HAK-04 — Eligibility API Integration

## Implementation Status

The React eligibility interface is connected to Stefano's
FastAPI eligibility service.

The frontend implementation is maintained on `hakm/frontend`.
The completed backend is maintained on `main`.

Live integration was successfully tested on 12 November 2026
using two separate local repository copies.

## Backend API

Endpoint:

POST http://127.0.0.1:8000/api/eligibility/evaluate

The frontend sends one request for the opportunity selected
by the student.

Example request:

{
  "opportunity_id": "OPP-003",
  "profile": {
    "citizenship_status": "australian_citizen",
    "weighted_average": 65
  }
}

The submitted profile uses the agreed fields documented in
PROFILE_MAPPING.md.

The voluntary `identity_answer` field is excluded from
eligibility API requests.

## Response Handling

FastAPI returns:

- opportunity_id
- results
- notice

Each condition result includes:

- condition_id
- status
- explanation
- requirement
- evidence_summary
- source_url

The frontend's `eligibilityResults.js` converts the backend
response into the existing internal format:

- opportunityId
- conditionId
- status
- explanation

Only three backend evaluation statuses are accepted:

- satisfied
- unmet
- uncertain

If an accepted result is unavailable, the interface displays
"Not yet evaluated".

The frontend does not independently calculate eligibility.

## Validation and Safeguards

The implementation:

1. Verifies that the response matches the selected opportunity.
2. Checks condition IDs and rejects duplicate results.
3. Rejects invalid statuses and malformed responses.
4. Verifies returned evidence against the published record.
5. Preserves published requirements and official source links.
6. Never automatically scores Indigenous identity.
7. Excludes identity_answer from the API request.
8. Clears previous results when the profile changes.
9. Prevents cancelled or outdated requests from updating results.
10. Displays neutral states when the backend is unavailable.
11. Rejects weighted averages outside 0–100.

Eligibility comparisons are informational only and do not
represent official admission or eligibility decisions.

## Verified Live Integration Tests

Testing used the React frontend from `hakm/frontend` and the
completed FastAPI backend from `main`, running locally.

Opportunity: OPP-003

Scenario 1:
Australian citizen, weighted average 65
Expected and observed:
2 satisfied, 4 uncertain.

Scenario 2:
No optional profile information supplied
Expected and observed:
6 uncertain.

Scenario 3:
New Zealand citizen, weighted average 65
Expected and observed:
1 satisfied, 1 unmet, 4 uncertain.

Additional verified behaviour:

- GET /api/opportunities returned HTTP 200.
- React retrieved opportunity records from FastAPI.
- POST /api/eligibility/evaluate returned HTTP 200.
- Unknown opportunity OPP-999 returned HTTP 404 in Swagger.
- Changing the voluntary Indigenous identity answer did not
  alter eligibility results.
- Browser Network inspection confirmed that identity_answer
  was absent from the request payload.
- Editing the student profile cleared previous eligibility
  results.
- Backend unavailability displayed a safe error message
  while preserving published opportunity information.

These results demonstrate local technical integration.
They do not establish production readiness, real-user
usability or community validation.

## Automated Frontend Verification

From the frontend directory, run:

npm test
npm run build

Final results on 12 November 2026:

- 71 automated frontend tests passed.
- 0 tests failed.
- Vite production build succeeded.

## Local Development Requirements

The frontend requires the FastAPI backend to be running
at http://127.0.0.1:8000.

The backend requires its SQLite opportunity database.
The database may need to be initialised separately after
cloning the repository.

The frontend can display the bundled local JSON dataset
if the opportunity API is unavailable. This fallback does
not provide automatic eligibility decisions.

The completed backend and frontend were tested together
using separate local clones before branch integration.

## Remaining Work

- Review the frontend changes through GitHub.
- Preserve the completed backend when merging branches.
- Merge the reviewed frontend integration into main.
- Rerun tests after merging.
- Verify the combined repository can run both services.

Production authentication, deployment and real-user testing
remain outside the verified HAK-04 implementation.
