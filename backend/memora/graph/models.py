"""Memora graph domain models.

All Pydantic models for the knowledge graph: enums, node types, edge types,
pipeline models (proposals/updates), and capture model.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    """Timezone-aware UTC now, for use as Pydantic default_factory."""
    return datetime.now(timezone.utc)


# ============================================================
# Enums
# ============================================================


class NodeType(str, Enum):
    # Life Context Nodes
    EVENT = "EVENT"
    PERSON = "PERSON"
    COMMITMENT = "COMMITMENT"
    DECISION = "DECISION"
    GOAL = "GOAL"
    FINANCIAL_ITEM = "FINANCIAL_ITEM"
    # Knowledge Nodes
    NOTE = "NOTE"
    IDEA = "IDEA"
    PROJECT = "PROJECT"
    CONCEPT = "CONCEPT"
    REFERENCE = "REFERENCE"
    INSIGHT = "INSIGHT"


class EdgeCategory(str, Enum):
    STRUCTURAL = "STRUCTURAL"
    ASSOCIATIVE = "ASSOCIATIVE"
    PROVENANCE = "PROVENANCE"
    TEMPORAL = "TEMPORAL"
    PERSONAL = "PERSONAL"
    SOCIAL = "SOCIAL"
    NETWORK = "NETWORK"


class EdgeType(str, Enum):
    # Structural
    PART_OF = "PART_OF"
    CONTAINS = "CONTAINS"
    SUBTASK_OF = "SUBTASK_OF"
    # Associative
    RELATED_TO = "RELATED_TO"
    INSPIRED_BY = "INSPIRED_BY"
    CONTRADICTS = "CONTRADICTS"
    SIMILAR_TO = "SIMILAR_TO"
    COMPLEMENTS = "COMPLEMENTS"
    # Provenance
    DERIVED_FROM = "DERIVED_FROM"
    VERIFIED_BY = "VERIFIED_BY"
    SOURCE_OF = "SOURCE_OF"
    EXTRACTED_FROM = "EXTRACTED_FROM"
    # Temporal
    PRECEDED_BY = "PRECEDED_BY"
    EVOLVED_INTO = "EVOLVED_INTO"
    TRIGGERED = "TRIGGERED"
    CONCURRENT_WITH = "CONCURRENT_WITH"
    # Personal
    COMMITTED_TO = "COMMITTED_TO"
    DECIDED = "DECIDED"
    FELT_ABOUT = "FELT_ABOUT"
    RESPONSIBLE_FOR = "RESPONSIBLE_FOR"
    # Social
    KNOWS = "KNOWS"
    INTRODUCED_BY = "INTRODUCED_BY"
    OWES_FAVOR = "OWES_FAVOR"
    COLLABORATES_WITH = "COLLABORATES_WITH"
    REPORTS_TO = "REPORTS_TO"
    # Network
    BRIDGES = "BRIDGES"
    MEMBER_OF = "MEMBER_OF"
    IMPACTS = "IMPACTS"
    CORRELATES_WITH = "CORRELATES_WITH"


class NetworkType(str, Enum):
    ACADEMIC = "ACADEMIC"
    PROFESSIONAL = "PROFESSIONAL"
    FINANCIAL = "FINANCIAL"
    HEALTH = "HEALTH"
    PERSONAL_GROWTH = "PERSONAL_GROWTH"
    SOCIAL = "SOCIAL"
    VENTURES = "VENTURES"


class CommitmentStatus(str, Enum):
    OPEN = "open"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class GoalStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ACHIEVED = "achieved"
    ABANDONED = "abandoned"


class ProjectStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class IdeaMaturity(str, Enum):
    SEED = "seed"
    DEVELOPING = "developing"
    MATURE = "mature"
    ARCHIVED = "archived"


class NoteType(str, Enum):
    OBSERVATION = "observation"
    REFLECTION = "reflection"
    SUMMARY = "summary"
    QUOTE = "quote"


class ComplexityLevel(str, Enum):
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FinancialDirection(str, Enum):
    INFLOW = "inflow"
    OUTFLOW = "outflow"


class HealthStatus(str, Enum):
    ON_TRACK = "on_track"
    NEEDS_ATTENTION = "needs_attention"
    FALLING_BEHIND = "falling_behind"


class Momentum(str, Enum):
    UP = "up"
    STABLE = "stable"
    DOWN = "down"


class ProposalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ProposalRoute(str, Enum):
    AUTO = "auto"
    DIGEST = "digest"
    EXPLICIT = "explicit"


# ============================================================
# Node Models
# ============================================================


class BaseNode(BaseModel):
    """Shared properties for all graph nodes."""

    id: UUID = Field(default_factory=uuid4)
    node_type: NodeType
    title: str
    content: str = ""
    content_hash: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    networks: list[NetworkType] = Field(default_factory=list)
    human_approved: bool = False
    proposed_by: str = ""
    source_capture_id: UUID | None = None
    access_count: int = 0
    last_accessed: datetime | None = None
    decay_score: float = 1.0
    review_date: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    def compute_content_hash(self) -> str:
        """Compute SHA-256 hash of title + content for dedup."""
        raw = f"{self.title}|{self.content}"
        self.content_hash = hashlib.sha256(raw.encode()).hexdigest()
        return self.content_hash


class EventNode(BaseNode):
    """An event that occurred or is planned."""

    node_type: NodeType = NodeType.EVENT
    event_date: datetime | None = None
    location: str = ""
    participants: list[str] = Field(default_factory=list)
    event_type: str = ""
    duration: str = ""
    sentiment: str = ""
    recurring: bool = False


class PersonNode(BaseNode):
    """A person in the user's life."""

    node_type: NodeType = NodeType.PERSON
    name: str = ""
    aliases: list[str] = Field(default_factory=list)
    role: str = ""
    relationship_to_user: str = ""
    contact_info: dict[str, str] = Field(default_factory=dict)
    organization: str = ""
    last_interaction: datetime | None = None


class CommitmentNode(BaseNode):
    """A promise or obligation."""

    node_type: NodeType = NodeType.COMMITMENT
    due_date: datetime | None = None
    status: CommitmentStatus = CommitmentStatus.OPEN
    committed_by: str = ""
    committed_to: str = ""
    priority: Priority = Priority.MEDIUM
    description: str = ""


class DecisionNode(BaseNode):
    """A decision made or pending."""

    node_type: NodeType = NodeType.DECISION
    decision_date: datetime | None = None
    options_considered: list[str] = Field(default_factory=list)
    chosen_option: str = ""
    rationale: str = ""
    outcome: str = ""
    reversible: bool = True


class GoalNode(BaseNode):
    """A goal being pursued."""

    node_type: NodeType = NodeType.GOAL
    target_date: datetime | None = None
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    milestones: list[dict[str, Any]] = Field(default_factory=list)
    status: GoalStatus = GoalStatus.ACTIVE
    priority: Priority = Priority.MEDIUM
    success_criteria: str = ""


class FinancialItemNode(BaseNode):
    """A financial transaction or item."""

    node_type: NodeType = NodeType.FINANCIAL_ITEM
    amount: float = 0.0
    currency: str = "USD"
    direction: FinancialDirection = FinancialDirection.OUTFLOW
    category: str = ""
    recurring: bool = False
    frequency: str = ""
    counterparty: str = ""


class NoteNode(BaseNode):
    """A note or observation."""

    node_type: NodeType = NodeType.NOTE
    source_context: str = ""
    note_type: NoteType = NoteType.OBSERVATION


class IdeaNode(BaseNode):
    """An idea at some stage of development."""

    node_type: NodeType = NodeType.IDEA
    maturity: IdeaMaturity = IdeaMaturity.SEED
    domain: str = ""
    potential_impact: str = ""


class ProjectNode(BaseNode):
    """A project being tracked."""

    node_type: NodeType = NodeType.PROJECT
    status: ProjectStatus = ProjectStatus.ACTIVE
    start_date: datetime | None = None
    target_date: datetime | None = None
    team: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    repository_url: str = ""


class ConceptNode(BaseNode):
    """A concept or knowledge item."""

    node_type: NodeType = NodeType.CONCEPT
    definition: str = ""
    domain: str = ""
    related_concepts: list[str] = Field(default_factory=list)
    complexity_level: ComplexityLevel = ComplexityLevel.BASIC


class ReferenceNode(BaseNode):
    """An external reference (paper, article, link)."""

    node_type: NodeType = NodeType.REFERENCE
    url: str = ""
    author: str = ""
    publication_date: datetime | None = None
    source_type: str = ""
    citation: str = ""
    archived: bool = False


class InsightNode(BaseNode):
    """A derived insight from graph analysis."""

    node_type: NodeType = NodeType.INSIGHT
    derived_from: list[str] = Field(default_factory=list)
    actionable: bool = False
    cross_network: bool = False
    strength: float = Field(default=0.5, ge=0.0, le=1.0)


# Map NodeType enum to the corresponding model class
NODE_TYPE_MODEL_MAP: dict[NodeType, type[BaseNode]] = {
    NodeType.EVENT: EventNode,
    NodeType.PERSON: PersonNode,
    NodeType.COMMITMENT: CommitmentNode,
    NodeType.DECISION: DecisionNode,
    NodeType.GOAL: GoalNode,
    NodeType.FINANCIAL_ITEM: FinancialItemNode,
    NodeType.NOTE: NoteNode,
    NodeType.IDEA: IdeaNode,
    NodeType.PROJECT: ProjectNode,
    NodeType.CONCEPT: ConceptNode,
    NodeType.REFERENCE: ReferenceNode,
    NodeType.INSIGHT: InsightNode,
}


# ============================================================
# Edge Model
# ============================================================


class Edge(BaseModel):
    """A typed relationship between two nodes."""

    id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    target_id: UUID
    edge_type: EdgeType
    edge_category: EdgeCategory
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    weight: float = 1.0
    bidirectional: bool = False
    properties: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


# ============================================================
# Pipeline Models (Proposals & Updates)
# ============================================================


class TemporalAnchor(BaseModel):
    """Temporal metadata for a node."""

    occurred_at: datetime | None = None
    due_at: datetime | None = None
    temporal_type: str = "present"  # past, present, future, recurring


class NodeProposal(BaseModel):
    """A proposed new node in the knowledge graph."""

    temp_id: str
    node_type: NodeType
    title: str
    content: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    networks: list[NetworkType] = Field(default_factory=list)
    temporal: TemporalAnchor | None = None


class NodeUpdate(BaseModel):
    """An update to an existing node."""

    node_id: str
    updates: dict[str, Any]
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    reason: str = ""


class EdgeProposal(BaseModel):
    """A proposed relationship between two nodes."""

    source_id: str  # temp_id or existing graph UUID
    target_id: str
    edge_type: EdgeType
    edge_category: EdgeCategory
    properties: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    bidirectional: bool = False


class EdgeUpdate(BaseModel):
    """An update to an existing edge."""

    edge_id: str
    updates: dict[str, Any]
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class NetworkAssignment(BaseModel):
    """Assign a node to a context network."""

    node_id: str  # temp_id or existing UUID
    network: NetworkType
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class GraphProposal(BaseModel):
    """Atomic set of graph changes proposed by the Archivist."""

    source_capture_id: str
    timestamp: datetime = Field(default_factory=_utcnow)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    nodes_to_create: list[NodeProposal] = Field(default_factory=list)
    nodes_to_update: list[NodeUpdate] = Field(default_factory=list)
    edges_to_create: list[EdgeProposal] = Field(default_factory=list)
    edges_to_update: list[EdgeUpdate] = Field(default_factory=list)
    network_assignments: list[NetworkAssignment] = Field(default_factory=list)
    human_summary: str = ""


# ============================================================
# Capture Model
# ============================================================


class Capture(BaseModel):
    """A raw user input capture."""

    id: UUID = Field(default_factory=uuid4)
    modality: Literal["text"] = "text"
    raw_content: str
    processed_content: str = ""
    content_hash: str = ""
    language: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)

    def compute_content_hash(self) -> str:
        """Compute SHA-256 hash of raw_content for dedup."""
        self.content_hash = hashlib.sha256(self.raw_content.encode()).hexdigest()
        return self.content_hash


# ============================================================
# Query / Filter helpers
# ============================================================


class NodeFilter(BaseModel):
    """Filters for querying nodes."""

    node_types: list[NodeType] | None = None
    networks: list[NetworkType] | None = None
    tags: list[str] | None = None
    min_confidence: float | None = None
    min_decay_score: float | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = 50
    offset: int = 0


class Subgraph(BaseModel):
    """A subgraph result (neighborhood query)."""

    nodes: list[BaseNode] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
