# Task 6 Report: Direct Source Usage Guides

## Status

Completed the Task 6 runtime instructions and direct-use site guides.

- **Evidence: High.** Five guides cover SSE, CNINFO, HKEXnews, Hong Kong
  regulatory and ownership routes, and official statistics. Each has direct
  URLs, query fields and examples, result identity, citation fields, access
  limitations, same-function fallbacks, and provenance boundaries.
- **Evidence: High.** `SKILL.md` defines the required reachability precedence:
  `valid local cache observation -> reviewed snapshot -> profile access record`.
  Cache is limited to reachability and uses the existing
  `source_profiles.ttl_for_status` statuses and TTLs.
- **Evidence: High.** The search playbook now specifies trust-first discovery
  and deterministic tie-breaking for uncataloged Hong Kong official sources.
  A finance portal remains discovery-only unless the verified-mirror exception
  applies.

## Baseline Failures Addressed

- **Evidence: High.** The SSE baseline’s missing local-cache, reviewed
  snapshot, profile precedence, TTL, and exact SSE/CNINFO field guidance are
  addressed in the runtime section and the SSE/CNINFO guides. The Moutai
  `600519` / `贵州茅台` examples separate SSE inquiry letters from issuer replies.
- **Evidence: High.** The HK baseline’s missing HKEXnews, DI, CCASS, and
  monthly-return boundaries are addressed. Pop Mart `09992` examples retain DI
  as the statutory ownership route, prohibit treating CCASS, annual reports,
  or monthly returns as DI substitutes, and preserve DI’s lack of a
  function-equivalent fallback.
- **Evidence: High.** The uncataloged-HK baseline’s missing tie-break is
  addressed: direct official producer, exact geography/period/definition, and
  result identity order tied official sources before adjacent evidence or a
  finance portal.

## RED

Command:

```bash
uv run pytest tests/unit/skills/test_source_discovery_skill.py -q
```

Observed output:

```text
collected 23 items
4 failed, 19 passed in 1.53s
```

The failures were intentional and specific to the new requirements: runtime
cache/snapshot/TTL instructions, noninteractive retrieval guidance, absent site
guides, and uncataloged Hong Kong trust-first routing.

## GREEN

Command:

```bash
uv run pytest tests/unit/skills/test_source_discovery_skill.py tests/unit/skills/test_source_capability_profiles.py -q
```

Observed output:

```text
collected 54 items
54 passed in 4.74s
```

## Validation

```bash
uv run python .claude/skills/source-discovery/scripts/build_source_catalog.py \
  --profiles .claude/skills/source-discovery/references/sources \
  --snapshot .claude/skills/source-discovery/references/reachability-snapshot.json \
  --output .claude/skills/source-discovery/references/source-catalog.md --check
git diff --check
```

Both commands exited 0 with no output. The catalog was regenerated because its
existing generator automatically links the new `sse`, `cninfo`, and
`hkexnews` guide filenames.

## Self-Review

- **Evidence: High.** `SKILL.md` is below the 500-line limit and delegates
  detailed fields and route behavior to the five guides.
- **Evidence: High.** The runtime rules keep cache observations out of
  authority, citation scope, publisher identity, workflow evidence, and
  field/API evidence.
- **Evidence: High.** Same-function boundaries remain explicit: DI is not
  widened to CCASS, annual reports, or monthly returns; an SSE inquiry letter
  is not replaced by a CNINFO issuer response.
- **Evidence: High.** The committed catalog remains deterministic against the
  maintained profiles and reviewed snapshot.

## Concerns

- **Evidence: High.** This task added instructions from reviewed profiles and
  baseline evidence; it did not run live browser or network retrieval.
  Direct URLs and rendered workflows remain point-in-time and must be
  revalidated at use time.
- **Evidence: High.** DI was recorded as temporarily unavailable in the
  reviewed snapshot. Its guide intentionally does not invent HTML parameter
  names and requires a stale route to be rechecked.
