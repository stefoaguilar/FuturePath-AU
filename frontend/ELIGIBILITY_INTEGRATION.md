# HAK-04 eligibility integration boundary

There is no agreed eligibility endpoint or response contract in this checkout.
`backend/main.py` exposes only `/` and `/health`. The existing opportunity fetch
does not supply eligibility data to the adapter. Profile submission remains local
input validation and sends no student data.

`main.jsx` mounts `<App />` with no evaluation input. It shows all conditions as
`not_yet_evaluated` and explains that evaluation is unavailable. No test fixtures
are imported into the running application.

After Stefano supplies the endpoint, request/response contract and profile/result
binding, implement the agreed transport separately. Supply the internal App prop
`eligibilityInput` with:

- `payload`: the response from that agreed transport, treated as untrusted data.
- `decodeResponse`: a synchronous, format-specific decoder returning the internal
  records below. There is deliberately no default decoder or guessed wire format.
- `profileSnapshot`: a copy of the exact 11-field local profile used for that
  request. This is local freshness metadata, not an assumed backend response field.
- `unavailable: true` when that evaluation request fails, to clear prior results.

The decoder returns an array of **frontend-internal** records:

```javascript
{ opportunityId, conditionId, status, explanation? }
```

This is not a proposed backend contract. Map the actual agreed format here rather
than changing the opportunity dataset. Preserve condition IDs and all outcome and
scoring fields during decoding: do not silently discard unsupported scoring data.
Normalize absent optional explanations by omitting them; supplied explanations
must be text. The internal record deliberately allows no score fields.

`eligibilityResults.js` validates the entire decoded batch before exposing any
results. IDs must match the same published opportunity/condition pair, each
condition may appear once, and outcomes must be `satisfied`, `unmet` or `uncertain`.
Unknown outcomes, malformed records, decoder failures and extra fields reject the
whole batch. Missing results remain neutral `not_yet_evaluated`. Explanations are
rendered as plain React text alongside the original published evidence and source.

Identity requirements may only retain an explicit backend `uncertain` result.
An automatic `satisfied`/`unmet` identity result or extra identity scoring fields
rejects the batch with a safeguard warning. The UI always calls for voluntary
student confirmation or human review and never uses `identity_answer` to decide.

Results for a different profile snapshot are hidden. An opportunity API failure
also hides evaluations while retaining the 30-record local development fallback.
The snapshot check is equality for freshness only; no profile field is compared
with an eligibility criterion. Counts include accepted condition results only,
never an overall eligibility decision or suitability score.

Run `npm.cmd test` and `npm.cmd run build` from `frontend/` on Windows (or `npm test`
and `npm run build` where npm's shell entrypoint is available).
