# Graph Ontology

Memora's ontology is defined in `ontology_default.yaml` and loaded at runtime by
`OntologyRegistry` (`memora/graph/ontology_registry.py`). It is **enforced**, not just
descriptive: `GraphRepository` validates every node and edge write (both direct
`create_node`/`create_edge` calls and the LLM-proposal commit path) against it before
persisting, raising `OntologyViolationError` on a violation.

## Node Types (17)

| Category | Types |
|----------|-------|
| core | `PERSON`, `EVENT`, `COMMITMENT`, `DECISION`, `GOAL`, `FINANCIAL_ITEM`, `NOTE`, `IDEA`, `PROJECT`, `CONCEPT`, `REFERENCE`, `INSIGHT` |
| strategic | `ORGANIZATION`, `POSITION`, `ELECTION` |
| academic | `COURSE` |
| intelligence | `METRIC` |

Each type declares a `properties` schema (name → `type`, optional `default`,
optional `required`, optional `value_type`) used for LLM extraction prompts,
dashboard rendering, and write-time validation.

## Edge Types (33)

Organized into 8 categories: `STRUCTURAL`, `ASSOCIATIVE`, `PROVENANCE`, `TEMPORAL`,
`PERSONAL`, `SOCIAL`, `NETWORK`, `STRATEGIC`. Each edge declares an optional
`source`/`target` type constraint (`null` = any type) and an optional `cardinality`.

### Cardinality

Most edge types are unconstrained many-to-many. A few declare real cardinality,
enforced at write time via an edge-count check:

| Edge | Cardinality | Meaning |
|------|-------------|---------|
| `SUBTASK_OF` | `MANY_TO_ONE` | a subtask has exactly one parent |
| `PART_OF` | `MANY_TO_ONE` | a part has exactly one whole |
| `HOLDS_POSITION` | `ONE_TO_MANY` | a position has one current holder; a person may hold several positions |

`MANY_TO_ONE` limits the **source** to ≤1 outgoing edge of that type;
`ONE_TO_MANY` limits the **target** to ≤1 incoming edge of that type;
`ONE_TO_ONE` (unused today, available for future edges) enforces both.

## Value Types

Shared semantic property types, referenced from an entity's `properties` schema
via `value_type: NAME`, validated at write time:

| Value type | Rule |
|------------|------|
| `URL` | must match `^https?://\S+$` |
| `CURRENCY_CODE` | must match `^[A-Z]{3}$` |
| `PERCENTAGE` | numeric, `0.0`–`1.0` |

Applied today to `REFERENCE.url`, `ORGANIZATION.website`, `PROJECT.repository_url`
(`URL`), `FINANCIAL_ITEM.currency` (`CURRENCY_CODE`), and `GOAL.progress` /
`INSIGHT.strength` (`PERCENTAGE`).

## Interfaces

Cross-type contracts enabling type-agnostic queries, independent of the
source/target constraints on any single edge:

| Interface | Implemented by |
|-----------|----------------|
| `SCHEDULABLE` | `EVENT`, `COMMITMENT`, `GOAL` |
| `TRACKABLE` | `COMMITMENT`, `GOAL`, `PROJECT`, `POSITION`, `COURSE` |

Query across an interface with `GraphRepository.get_nodes_by_interface(name, ...)`,
which resolves the interface to its implementing node types and delegates to
`query_nodes`.

## Action Types

`memora/core/actions.py`'s `ActionEngine` executes typed, kinetic graph operations
(state changes with preconditions and side effects). The `action_types:` section of
the ontology declares each action's label and applicable node types; the handler
implementation stays in Python since behavior isn't YAML-expressible.

| Action | Applies to | Precondition |
|--------|-----------|---------------|
| `COMPLETE_COMMITMENT` | `COMMITMENT` | status must be open |
| `PROMOTE_IDEA` | `IDEA` | must not already be archived |
| `ARCHIVE_GOAL` | `GOAL` | must be active |
| `ADVANCE_GOAL` | `GOAL` | must be active |
| `RECORD_OUTCOME` | `DECISION`, `GOAL`, `COMMITMENT` | none |
| `LINK_ENTITIES` | any | none |

## Context Networks (9)

Every node belongs to zero or more context networks, used for decay scoring and
health tracking:

| Network | Decay Lambda |
|---------|-------------|
| `ACADEMIC` | 0.05 |
| `PROFESSIONAL` | 0.03 |
| `FINANCIAL` | 0.02 |
| `HEALTH` | 0.05 |
| `PERSONAL_GROWTH` | 0.04 |
| `SOCIAL` | 0.07 |
| `VENTURES` | 0.03 |
| `GOVERNANCE` | 0.04 |
| `CLUBS` | 0.04 |

`OntologyRegistry.suggest_networks(text)` scores candidate networks for a piece of
text by keyword match, used during extraction.

## Central Node

A fixed `PERSON` node (UUID: `00000000-0000-0000-0000-000000000001`) represents "You"
— the ego node. All other nodes orbit this central node via direct or transitive edges.
