# Graph Ontology

## Node Types (12)

| Type | Description | Key Properties |
|------|-------------|----------------|
| `EVENT` | Something that happened | date, location, participants |
| `PERSON` | A person in your life | role, relationship_type |
| `COMMITMENT` | A promise or obligation | status, deadline, assignee |
| `DECISION` | A choice made or pending | outcome, alternatives |
| `GOAL` | A desired future state | status, target_date, milestones |
| `FINANCIAL_ITEM` | Money-related entry | amount, currency, category |
| `NOTE` | A general note or observation | category, source |
| `IDEA` | A concept not yet acted on | maturity, feasibility |
| `PROJECT` | An active initiative | status, deadline, team |
| `CONCEPT` | An abstract topic or theme | domain, complexity |
| `REFERENCE` | A book, paper, or resource | url, author, type |
| `INSIGHT` | A derived conclusion | evidence_nodes, pattern_type |

## Edge Types (29)

Organized into 6 categories:

### Structural
`PART_OF`, `CONTAINS`, `DEPENDS_ON`, `BLOCKS`

### Associative
`RELATED_TO`, `SIMILAR_TO`, `CONTRASTS_WITH`, `SUPPORTS`, `CONTRADICTS`

### Provenance
`DERIVED_FROM`, `REFERENCES`, `CITES`, `INFORMED_BY`

### Temporal
`PRECEDED_BY`, `FOLLOWED_BY`, `CONCURRENT_WITH`, `TRIGGERED`

### Personal
`ASSIGNED_TO`, `CREATED_BY`, `DECIDED_BY`, `COMMITTED_TO`, `PROGRESS`

### Social
`KNOWS`, `COLLABORATES_WITH`, `REPORTS_TO`, `MENTORS`, `INTRODUCED_BY`

## Context Networks (7)

Every node belongs to one or more context networks:

| Network | Decay Lambda | Description |
|---------|-------------|-------------|
| `ACADEMIC` | 0.05 | Education, research, learning |
| `PROFESSIONAL` | 0.03 | Work, career, business |
| `FINANCIAL` | 0.02 | Money, investments, expenses |
| `HEALTH` | 0.05 | Physical and mental health |
| `PERSONAL_GROWTH` | 0.04 | Self-improvement, habits |
| `SOCIAL` | 0.07 | Relationships, social events |
| `VENTURES` | 0.03 | Side projects, startups |

## Central Node

A fixed `PERSON` node (UUID: `00000000-0000-0000-0000-000000000001`) represents "You" — the ego node. All other nodes orbit this central node via direct or transitive edges.
