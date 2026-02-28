"""Graph ontology: valid edge type → node type mappings and validation.

Defines which edge types can connect which node types, and provides
validation functions for the graph schema.
"""

from __future__ import annotations

from .models import EdgeCategory, EdgeType, NodeType

# ============================================================
# Edge Type → Category mapping
# ============================================================

EDGE_TYPE_CATEGORY: dict[EdgeType, EdgeCategory] = {
    # Structural
    EdgeType.PART_OF: EdgeCategory.STRUCTURAL,
    EdgeType.CONTAINS: EdgeCategory.STRUCTURAL,
    EdgeType.SUBTASK_OF: EdgeCategory.STRUCTURAL,
    # Associative
    EdgeType.RELATED_TO: EdgeCategory.ASSOCIATIVE,
    EdgeType.INSPIRED_BY: EdgeCategory.ASSOCIATIVE,
    EdgeType.CONTRADICTS: EdgeCategory.ASSOCIATIVE,
    EdgeType.SIMILAR_TO: EdgeCategory.ASSOCIATIVE,
    EdgeType.COMPLEMENTS: EdgeCategory.ASSOCIATIVE,
    # Provenance
    EdgeType.DERIVED_FROM: EdgeCategory.PROVENANCE,
    EdgeType.VERIFIED_BY: EdgeCategory.PROVENANCE,
    EdgeType.SOURCE_OF: EdgeCategory.PROVENANCE,
    EdgeType.EXTRACTED_FROM: EdgeCategory.PROVENANCE,
    # Temporal
    EdgeType.PRECEDED_BY: EdgeCategory.TEMPORAL,
    EdgeType.EVOLVED_INTO: EdgeCategory.TEMPORAL,
    EdgeType.TRIGGERED: EdgeCategory.TEMPORAL,
    EdgeType.CONCURRENT_WITH: EdgeCategory.TEMPORAL,
    # Personal
    EdgeType.COMMITTED_TO: EdgeCategory.PERSONAL,
    EdgeType.DECIDED: EdgeCategory.PERSONAL,
    EdgeType.FELT_ABOUT: EdgeCategory.PERSONAL,
    EdgeType.RESPONSIBLE_FOR: EdgeCategory.PERSONAL,
    # Social
    EdgeType.KNOWS: EdgeCategory.SOCIAL,
    EdgeType.INTRODUCED_BY: EdgeCategory.SOCIAL,
    EdgeType.OWES_FAVOR: EdgeCategory.SOCIAL,
    EdgeType.COLLABORATES_WITH: EdgeCategory.SOCIAL,
    EdgeType.REPORTS_TO: EdgeCategory.SOCIAL,
    # Network
    EdgeType.BRIDGES: EdgeCategory.NETWORK,
    EdgeType.MEMBER_OF: EdgeCategory.NETWORK,
    EdgeType.IMPACTS: EdgeCategory.NETWORK,
    EdgeType.CORRELATES_WITH: EdgeCategory.NETWORK,
}


# ============================================================
# Valid source → target node type constraints per edge type
# None means "any node type is valid" for that position
# ============================================================

_ANY = None  # sentinel for "any node type"

# Each entry: (allowed_source_types, allowed_target_types)
# None = any type allowed
EDGE_CONSTRAINTS: dict[EdgeType, tuple[set[NodeType] | None, set[NodeType] | None]] = {
    # Structural — hierarchy edges
    EdgeType.PART_OF: (_ANY, _ANY),
    EdgeType.CONTAINS: (_ANY, _ANY),
    EdgeType.SUBTASK_OF: (
        {NodeType.COMMITMENT, NodeType.GOAL, NodeType.PROJECT},
        {NodeType.COMMITMENT, NodeType.GOAL, NodeType.PROJECT},
    ),
    # Associative — semantic relationships (any ↔ any)
    EdgeType.RELATED_TO: (_ANY, _ANY),
    EdgeType.INSPIRED_BY: (_ANY, _ANY),
    EdgeType.CONTRADICTS: (_ANY, _ANY),
    EdgeType.SIMILAR_TO: (_ANY, _ANY),
    EdgeType.COMPLEMENTS: (_ANY, _ANY),
    # Provenance
    EdgeType.DERIVED_FROM: (_ANY, _ANY),
    EdgeType.VERIFIED_BY: (_ANY, {NodeType.REFERENCE, NodeType.PERSON}),
    EdgeType.SOURCE_OF: ({NodeType.REFERENCE, NodeType.PERSON}, _ANY),
    EdgeType.EXTRACTED_FROM: (_ANY, _ANY),
    # Temporal
    EdgeType.PRECEDED_BY: (_ANY, _ANY),
    EdgeType.EVOLVED_INTO: (_ANY, _ANY),
    EdgeType.TRIGGERED: (_ANY, _ANY),
    EdgeType.CONCURRENT_WITH: (_ANY, _ANY),
    # Personal — user-centric edges
    EdgeType.COMMITTED_TO: ({NodeType.PERSON}, {NodeType.COMMITMENT}),
    EdgeType.DECIDED: ({NodeType.PERSON}, {NodeType.DECISION}),
    EdgeType.FELT_ABOUT: ({NodeType.PERSON}, _ANY),
    EdgeType.RESPONSIBLE_FOR: ({NodeType.PERSON}, _ANY),
    # Social — person ↔ person (mostly)
    EdgeType.KNOWS: ({NodeType.PERSON}, {NodeType.PERSON}),
    EdgeType.INTRODUCED_BY: ({NodeType.PERSON}, {NodeType.PERSON}),
    EdgeType.OWES_FAVOR: ({NodeType.PERSON}, {NodeType.PERSON}),
    EdgeType.COLLABORATES_WITH: ({NodeType.PERSON}, {NodeType.PERSON}),
    EdgeType.REPORTS_TO: ({NodeType.PERSON}, {NodeType.PERSON}),
    # Network — cross-network connections
    EdgeType.BRIDGES: (_ANY, _ANY),
    EdgeType.MEMBER_OF: (_ANY, {NodeType.PROJECT, NodeType.EVENT}),
    EdgeType.IMPACTS: (_ANY, _ANY),
    EdgeType.CORRELATES_WITH: (_ANY, _ANY),
}


# ============================================================
# Network classification rules
# ============================================================

NETWORK_KEYWORDS: dict[str, list[str]] = {
    "ACADEMIC": [
        "course", "class", "professor", "grade", "exam", "study", "research",
        "paper", "thesis", "lecture", "assignment", "university", "college",
        "semester", "GPA", "curriculum", "syllabus", "academic",
    ],
    "PROFESSIONAL": [
        "work", "job", "client", "meeting", "project", "deadline", "colleague",
        "manager", "deliverable", "sprint", "standup", "promotion", "salary",
        "office", "career", "resume", "interview", "company",
    ],
    "FINANCIAL": [
        "money", "payment", "invoice", "budget", "expense", "income", "invest",
        "stock", "savings", "loan", "debt", "rent", "subscription", "tax",
        "bank", "transaction", "price", "cost", "fee",
    ],
    "HEALTH": [
        "exercise", "workout", "gym", "sleep", "stress", "doctor", "medication",
        "symptom", "diet", "nutrition", "mental health", "therapy", "habit",
        "weight", "blood pressure", "medical", "health",
    ],
    "PERSONAL_GROWTH": [
        "learn", "skill", "book", "course", "habit", "goal", "improvement",
        "meditation", "journal", "reflection", "growth", "mindset", "podcast",
        "tutorial", "practice", "mastery",
    ],
    "SOCIAL": [
        "friend", "family", "party", "dinner", "birthday", "relationship",
        "hangout", "call", "catch up", "wedding", "reunion", "favor",
        "gift", "social", "gathering",
    ],
    "VENTURES": [
        "startup", "idea", "MVP", "investor", "pitch", "business", "founder",
        "revenue", "customer", "product", "launch", "prototype", "market",
        "venture", "entrepreneurship", "side project",
    ],
}


# ============================================================
# Validation functions
# ============================================================


def validate_edge(
    source_type: NodeType,
    target_type: NodeType,
    edge_type: EdgeType,
) -> bool:
    """Check if an edge type is valid between the given node types.

    Returns True if the edge is valid according to the ontology constraints.
    """
    constraints = EDGE_CONSTRAINTS.get(edge_type)
    if constraints is None:
        return False

    allowed_sources, allowed_targets = constraints

    if allowed_sources is not None and source_type not in allowed_sources:
        return False
    if allowed_targets is not None and target_type not in allowed_targets:
        return False

    return True


def get_category_for_edge_type(edge_type: EdgeType) -> EdgeCategory:
    """Return the category for a given edge type."""
    category = EDGE_TYPE_CATEGORY.get(edge_type)
    if category is None:
        raise ValueError(f"Unknown edge type: {edge_type}")
    return category


def validate_edge_category(edge_type: EdgeType, edge_category: EdgeCategory) -> bool:
    """Check that an edge type belongs to the declared category."""
    expected = EDGE_TYPE_CATEGORY.get(edge_type)
    return expected == edge_category


def get_valid_edge_types(
    source_type: NodeType,
    target_type: NodeType,
) -> list[EdgeType]:
    """Return all valid edge types between two node types."""
    valid = []
    for edge_type in EdgeType:
        if validate_edge(source_type, target_type, edge_type):
            valid.append(edge_type)
    return valid


def suggest_networks(text: str) -> list[tuple[str, float]]:
    """Suggest networks based on keyword matching in text.

    Returns list of (network_name, confidence) tuples, sorted by confidence desc.
    """
    text_lower = text.lower()
    scores: list[tuple[str, float]] = []

    for network, keywords in NETWORK_KEYWORDS.items():
        matches = sum(1 for kw in keywords if kw.lower() in text_lower)
        if matches > 0:
            confidence = min(0.95, 0.3 + (matches * 0.15))
            scores.append((network, confidence))

    scores.sort(key=lambda x: x[1], reverse=True)
    return scores
