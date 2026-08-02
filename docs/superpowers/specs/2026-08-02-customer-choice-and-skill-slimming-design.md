# Customer Choice And Skill Slimming Design

## Purpose

Make product analysis answer why customers repeatedly choose the target
company, why competitors have not arbitraged away its advantage, and whether
the advantage survives funded entry, while removing duplicated instructions
from the `value-profile` orchestrator.

## Customer Choice Contract

Every `product-analysis` run must answer three adaptive questions:

1. Why does the customer buy and continue to repurchase, renew, or expand
   usage here instead of choosing a named alternative? The answer must
   distinguish concrete attraction, preference, habit, and true switching
   cost.
2. Why has other capital not offered a better-value product or service and
   taken the company's market share? The answer must identify capability,
   cost, channel, resource, or replication-time constraints rather than use
   circular claims such as "the brand is strong."
3. If a well-funded incumbent or entrant commits substantial capital, can the
   company defend or expand its share? This answer must also test whether the
   next product, version, or hit comes from a repeatable process or past luck.

The questions adapt by business type. Consumer products emphasize attraction,
design, identity, experience, collection, and social behavior. B2B products
emphasize procurement criteria, return on investment, quality, integration,
delivery, and switching risk. Commodity products may conclude that the product
itself has little attraction and that advantage comes from cost, resource
quality, reliability, or logistics.

Each answer separates observed facts, supported inference, and unknowns.
Low-switching-cost businesses must not claim to prevent customers from leaving;
the analysis instead asks whether the company can earn the customer's choice
again on each purchase.

`product-analysis` owns the detailed method. `value-profile` requires the three
answers in the combined §1.1/§1.3 handoff and rejects generic brand language.
§1.8 and §3 synthesize the accepted product evidence but do not rerun product
research.

## Pop Mart Update

Update §1.3 to present one coherent chain under the three core questions:

```text
customer attraction
-> repeat purchase
-> choice versus alternatives
-> defense against funded competitors
-> repeatable IP and product creation
```

Use existing accepted evidence for design preference, collecting, gifting,
social display, unboxing surprise, companionship, member contribution,
repurchase, price bands, direct channels, multiple IPs, product development,
and named competitors.

Do not overclaim:

- Blind-box randomness is an amplifier, not a durable advantage by itself.
- Collector-community strength and hidden-edition effects remain unverified
  where independent behavioral data is absent.
- Affordable-luxury positioning is an inference from price bands, not a proven
  customer motive.
- Pop Mart has low customer switching costs; its defense is repeated
  preference, design and IP execution, direct feedback, multi-IP breadth, and
  operating scale.
- The IP pipeline is supported by several multi-year IPs, but hit rate,
  development funnel, and lifecycle economics remain undisclosed.

The final moat conclusion remains narrow unless new evidence justifies a
different label.

## Skill Ownership And Migration

`value-profile/SKILL.md` remains an orchestrator. It keeps:

- invocation and mode routing;
- parent ownership and subskill calls;
- input and output contracts;
- acceptance gates;
- state transitions, blocking behavior, and atomic save requirements; and
- short required-read links to owned references.

Delete duplicated copies after confirming the owned reference contains the
rule:

- reader-facing prose and terminology belong to
  `references/profile-writing-style.md`;
- final projection and HTML behavior belong to
  `references/reader-rendering.md`;
- detailed section-worker prompts and operational examples belong to
  `references/operations.md`.

In this change, migrate and remove the duplicated `§4.6 Profile输出风格` and
`§4.7子agent prompt模板` bodies from the main skill. Replace them with concise
ownership and acceptance pointers. Do not migrate Step 1-6 wholesale because
the existing operations reference is not yet fully synchronized with current
manifest, subskill, and state-transition contracts.

Tests must verify ownership and routing instead of requiring the same wording
in both the orchestrator and its references.

## Validation

Keep validation focused:

- extend the existing product-analysis contract test with the three questions;
- update the existing value-profile ownership and prompt tests to read the
  owned references;
- update the existing Pop Mart product-section test with the new synthesis;
- run only those targeted contract tests plus the two reader-rendering tests;
- rerender the Pop Mart HTML and scan for machine-only leakage.

The resulting main skill must be comfortably below the existing 700-line
orchestrator ceiling.
