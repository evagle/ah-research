# External Research Handoff

Use this contract only after `read-filing` has finished annual filing selection,
official event source discovery, manifest construction, source preflight, and
Mode B evidence binding for the current parent run.

peer/listing-applicant/industry evidence routes belong to `source-discovery`.
official filing and event source discovery remain in `read-filing`.

## Gap States

- `not_present_in_selected_filing`: the requested fact is not present in the
  selected annual filing or the already-bound official event/counterpart
  manifests. This is a filing-scope statement only. It must not be mapped to
  public absence, and it is valid to continue with external research.
- `public_availability_unresolved`: after running the allowed external routes,
  public evidence is still blocked, exhausted, conflicted, or unresolved as of
  `AS_OF`. This is not proof that the fact is absent from the public record.

## Request Construction

The outward request body must validate against
`source-discovery/references/research-request.schema.json`
(`research-request.schema.json` in discussion). Each unresolved external fact
becomes its own `claim_id`; do not bundle multiple unresolved facts into one
claim.

Every external request/handoff must preserve the parent evidence binding:

- annual manifest path and SHA-256
- event manifest path and SHA-256
- counterpart manifest paths and SHA-256s

Recommended wrapper shape:

```json
{
  "request": {
    "schema_version": "1.0",
    "claim_id": "cn-pop-toy-market-2020-2025",
    "claim_type": "market-size",
    "subject": "China pop-toy market",
    "metric": "annual retail market size",
    "geographies": ["China"],
    "industries": ["pop-toys"],
    "population": "retail consumers",
    "product_scope": "pop toys only",
    "measurement_basis": "retail value",
    "period_start": "2020",
    "period_end": "2025",
    "frequency": "annual",
    "continuity_required": true,
    "required_latest_period": "2025",
    "accepted_units": ["CNY billion"],
    "definition_constraints": ["pop toys only", "retail value"],
    "value_status_allowed": ["observed", "historical-estimate", "forecast"],
    "minimum_source_authority": "High",
    "minimum_conclusion_evidence": "High",
    "minimum_originality": "High",
    "minimum_independence": "Medium",
    "independent_cross_check_required": true,
    "absence_claim": false,
    "as_of": "2026-08-02"
  },
  "gap_state": "not_present_in_selected_filing",
  "parent_manifests": {
    "annual": {"path": "<absolute>", "sha256": "<sha256>"},
    "event": {"path": "<absolute>", "sha256": "<sha256>"},
    "counterpart": {"HK": {"path": "<absolute>", "sha256": "<sha256>"}}
  }
}
```

## Manifest Boundary

External research must read the preserved parent bindings as inputs only and
must not mutate those manifests. It cannot replace, rewrite, downgrade, or
re-select annual, event, or counterpart manifests, and it cannot weaken the
parent live-revalidation contract.

## return consumption

`read-filing` remains the consumer of the external handoff result.
`source-discovery` may return accepted candidates, unresolved claims, and the
terminal ledger, but it does not bind Mode B evidence or write profile text.
`read-filing` maps accepted external evidence back to the parent section,
retains the original parent manifest paths and hashes, binds citations itself,
and leaves unresolved external gaps explicit instead of converting them into
filing facts or public-absence conclusions.
