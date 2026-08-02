# Source Discovery Baseline

Date: 2026-08-02
Status: RED baseline captured before any `source-discovery` Skill edit

## Inputs reviewed

- `.superpowers/sdd/2026-08-02-evidence-gated-source-discovery/baseline-official-source.md`
- `.superpowers/sdd/2026-08-02-evidence-gated-source-discovery/baseline-pop-mart-expansion.md`
- `.superpowers/sdd/2026-08-02-evidence-gated-source-discovery/baseline-negative-claim.md`
- `docs/superpowers/specs/2026-08-02-evidence-gated-source-discovery-design.md`

## Pressure scenarios recorded

- `official-source-early-stop`
- `pop-mart-listing-applicant-expansion`
- `negative-enforcement-exhaustion`

## Baseline observations

### `official-source-early-stop`

The no-Skill control complied. The recorded baseline stops immediately after a
single National Bureau of Statistics table satisfies the claim end to end, and
it does not broaden discovery once the official source is sufficient.

Evidence level: High, because the baseline file explicitly states that one NBS
table covers the requested 2021-2025 annual series with matching scope,
definition, unit, and vintage.

### `negative-enforcement-exhaustion`

The no-Skill control complied. The recorded baseline refuses to conclude
`No enforcement action` after one zero-result regulator search and one timeout,
and it keeps all remaining official routes and issuer-name variants open.

Evidence level: High, because the baseline file explicitly treats the timeout as
unresolved coverage rather than negative evidence and requires all applicable
official routes to reach a terminal state before any absence conclusion.

### `pop-mart-listing-applicant-expansion`

The no-Skill baseline writeup also points in the correct direction. It says the
next route should pivot away from stale Pop Mart filings and familiar consultant
sources toward peer or listing-applicant HKEX industry-overview documents, with
strict acceptance rules for a continuous China pop-toy series.

Evidence level: Medium, because the baseline writeup is a process judgment about
the next best route, not proof that a qualifying document has already been
resolved.

## Observed regression that justifies the contract edit

The real historical Pop Mart failure was not that the no-Skill control reasoned
incorrectly about the route family. The failure was that the prior Pop Mart run
stopped on stale target-company and familiar-source paths, never reached the
listing-applicant expansion route, and therefore missed TOP TOY HKEX active
application `108384` and its 2020-2025 industry series.

Evidence level: High for the regression statement, because this task brief names
that exact miss as the observed failure the RED test must justify.

## Task 1 baseline conclusion

The control scenarios behaved correctly without revised Skill behavior. The RED
contract is still justified because the current Skill text does not yet encode
the claim-level stopping and exhaustion rules needed to prevent the observed Pop
Mart early-stop regression.

## Task 7 Contract Implication

The control results remain part of the evidence: the revised Skill is not
credited with the controls' early stop or refusal of premature absence. The
contract edit targets the observed historical Pop Mart routing failure by
requiring the planner's current layer, a gate decision after each layer, and
terminal ledger handoff before a conclusion.

## Task 7 Post-Edit Pressure Deployment

Five fresh-context repetitions were completed after the Skill edit:
`task-7-pressure-rep-{1..5}.md`. Every repetition returned `PASS` for all
three combined scenarios.

| Scenario | Result | Observed post-edit behavior |
| --- | --- | --- |
| Fitting official series | 5/5 PASS | Accepted claim stops after the gate and writes an accepted terminal ledger. |
| Stale Pop Mart evidence | 5/5 PASS | Only the unresolved claim advances through peer/listing-applicant and document layers before broad discovery. |
| Enforcement absence | 5/5 PASS | Remaining official routes stay open; timeout or access failure is `blocked`, never factual absence. |

The reps explicitly retained the HKEX boundary: TOP TOY application `108384`
may provide historical chart evidence only after index/PDF identity handling;
it is not current application proof. No pressure report identified a new
rationalization or contract loophole.

Evidence level: High for the retained no-Skill control observations and the
named Pop Mart regression, and High for the post-edit routing and ledger-rule
conclusions reported consistently by all five reps. Evidence level: Medium for
whether a qualifying current listing-applicant document will be found in a
future retrieval.
