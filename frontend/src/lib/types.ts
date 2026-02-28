// ── Enums ────────────────────────────────────────────────────────────────────

export enum NodeType {
  EVENT = "event",
  PERSON = "person",
  COMMITMENT = "commitment",
  DECISION = "decision",
  GOAL = "goal",
  FINANCIAL_ITEM = "financial_item",
  NOTE = "note",
  IDEA = "idea",
  PROJECT = "project",
  CONCEPT = "concept",
  REFERENCE = "reference",
  INSIGHT = "insight",
}

export enum EdgeCategory {
  STRUCTURAL = "structural",
  ASSOCIATIVE = "associative",
  PROVENANCE = "provenance",
  TEMPORAL = "temporal",
  PERSONAL = "personal",
  SOCIAL = "social",
  NETWORK = "network",
}

export enum EdgeType {
  PART_OF = "part_of",
  CONTAINS = "contains",
  SUBTASK_OF = "subtask_of",
  RELATED_TO = "related_to",
  INSPIRED_BY = "inspired_by",
  CONTRADICTS = "contradicts",
  SIMILAR_TO = "similar_to",
  COMPLEMENTS = "complements",
  DERIVED_FROM = "derived_from",
  VERIFIED_BY = "verified_by",
  SOURCE_OF = "source_of",
  EXTRACTED_FROM = "extracted_from",
  PRECEDED_BY = "preceded_by",
  EVOLVED_INTO = "evolved_into",
  TRIGGERED = "triggered",
  CONCURRENT_WITH = "concurrent_with",
  COMMITTED_TO = "committed_to",
  DECIDED = "decided",
  FELT_ABOUT = "felt_about",
  RESPONSIBLE_FOR = "responsible_for",
  KNOWS = "knows",
  INTRODUCED_BY = "introduced_by",
  OWES_FAVOR = "owes_favor",
  COLLABORATES_WITH = "collaborates_with",
  REPORTS_TO = "reports_to",
  BRIDGES = "bridges",
  MEMBER_OF = "member_of",
  IMPACTS = "impacts",
  CORRELATES_WITH = "correlates_with",
}

export enum NetworkType {
  ACADEMIC = "academic",
  PROFESSIONAL = "professional",
  FINANCIAL = "financial",
  HEALTH = "health",
  PERSONAL_GROWTH = "personal_growth",
  SOCIAL = "social",
  VENTURES = "ventures",
}

export enum CommitmentStatus {
  OPEN = "open",
  COMPLETED = "completed",
  OVERDUE = "overdue",
  CANCELLED = "cancelled",
}

export enum GoalStatus {
  ACTIVE = "active",
  PAUSED = "paused",
  ACHIEVED = "achieved",
  ABANDONED = "abandoned",
}

export enum ProjectStatus {
  ACTIVE = "active",
  PAUSED = "paused",
  COMPLETED = "completed",
  ABANDONED = "abandoned",
}

export enum IdeaMaturity {
  SEED = "seed",
  DEVELOPING = "developing",
  MATURE = "mature",
  ARCHIVED = "archived",
}

export enum NoteType {
  OBSERVATION = "observation",
  REFLECTION = "reflection",
  SUMMARY = "summary",
  QUOTE = "quote",
}

export enum ComplexityLevel {
  BASIC = "basic",
  INTERMEDIATE = "intermediate",
  ADVANCED = "advanced",
}

export enum Priority {
  LOW = "low",
  MEDIUM = "medium",
  HIGH = "high",
  CRITICAL = "critical",
}

export enum FinancialDirection {
  INFLOW = "inflow",
  OUTFLOW = "outflow",
}

export enum HealthStatus {
  ON_TRACK = "on_track",
  NEEDS_ATTENTION = "needs_attention",
  FALLING_BEHIND = "falling_behind",
}

export enum Momentum {
  UP = "up",
  STABLE = "stable",
  DOWN = "down",
}

export enum ProposalStatus {
  PENDING = "pending",
  APPROVED = "approved",
  REJECTED = "rejected",
}

export enum ProposalRoute {
  AUTO = "auto",
  DIGEST = "digest",
  EXPLICIT = "explicit",
}

export enum QueryType {
  CAPTURE = "capture",
  ANALYSIS = "analysis",
  RESEARCH = "research",
  COUNCIL = "council",
}

export enum AgentRole {
  ARCHIVIST = "archivist",
  STRATEGIST = "strategist",
  RESEARCHER = "researcher",
  ORCHESTRATOR = "orchestrator",
}

// ── Graph Models ─────────────────────────────────────────────────────────────

export interface GraphNode {
  id: string;
  node_type: NodeType;
  title: string;
  content: string;
  content_hash: string;
  properties: Record<string, unknown>;
  confidence: number;
  networks: NetworkType[];
  human_approved: boolean;
  proposed_by: string;
  source_capture_id: string | null;
  access_count: number;
  last_accessed: string | null;
  decay_score: number;
  review_date: string | null;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface GraphEdge {
  id: string;
  source_id: string;
  target_id: string;
  edge_type: EdgeType;
  edge_category: EdgeCategory;
  confidence: number;
  weight: number;
  bidirectional: boolean;
  properties: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Subgraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// ── Capture ──────────────────────────────────────────────────────────────────

export interface Capture {
  id: string;
  modality: "text";
  raw_content: string;
  processed_content: string;
  content_hash: string;
  language: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface CaptureCreate {
  modality?: "text";
  content: string;
  metadata?: Record<string, unknown>;
}

export interface CaptureResponse {
  id: string;
  status: string;
  pipeline_stage: number;
  created_at: string;
}

// ── Proposals ────────────────────────────────────────────────────────────────

export interface ProposalAction {
  action: "create_node" | "update_node" | "create_edge" | "update_edge";
  summary: string;
  node_type: string | null;
  edge_type: string | null;
  confidence: number;
  impact: "low" | "medium" | "high";
}

export interface ProposalResponse {
  id: string;
  capture_id: string;
  status: ProposalStatus;
  route: ProposalRoute;
  confidence: number;
  human_summary: string;
  action_count: number;
  created_at: string;
  reviewed_at: string | null;
}

export interface ProposalDetail extends ProposalResponse {
  actions: ProposalAction[];
  proposal_data: Record<string, unknown>;
  reviewer: string | null;
}

// ── Council ──────────────────────────────────────────────────────────────────

export interface CouncilQueryRequest {
  query: string;
  query_type?: QueryType;
  context?: Record<string, unknown>;
  max_deliberation_rounds?: number;
}

export interface CritiqueRequest {
  statement: string;
  context?: Record<string, unknown>;
}

export interface AgentOutput {
  agent: AgentRole;
  content: string;
  confidence: number;
  citations: string[];
  sources: Record<string, unknown>[];
}

export interface CouncilQueryResponse {
  query_id: string;
  query_type: QueryType;
  synthesis: string;
  agent_outputs: AgentOutput[];
  confidence: number;
  citations: string[];
  deliberation_rounds: number;
  high_disagreement: boolean;
  created_at: string;
}

export interface CritiqueResponse {
  original_statement: string;
  critique: string;
  counter_evidence: string[];
  confidence: number;
  citations: string[];
}

// ── Briefing ─────────────────────────────────────────────────────────────────

export interface BriefingSection {
  title: string;
  items: Record<string, unknown>[];
  priority: "low" | "medium" | "high";
}

export interface DailyBriefing {
  sections: BriefingSection[];
  summary: string;
  generated_at: string;
  cached: boolean;
}

// ── Networks ─────────────────────────────────────────────────────────────────

export interface NetworkHealth {
  name: NetworkType;
  node_count: number;
  health: {
    status: HealthStatus;
    momentum: Momentum;
    commitment_completion_rate: number;
    alert_count: number;
    staleness_flags: number;
  };
}

export interface NetworkDetail {
  name: string;
  node_count: number;
  health: {
    status: HealthStatus;
    momentum: Momentum;
    commitment_completion_rate: number;
    alert_count: number;
    staleness_flags: number;
  };
  health_history: Array<{
    timestamp: string;
    status: HealthStatus;
    momentum: Momentum;
  }>;
  recent_nodes: GraphNode[];
  commitment_stats: {
    open: number;
    completed: number;
    overdue: number;
    cancelled: number;
  };
  alerts: Notification[];
}

export interface Bridge {
  id: string;
  source_node_id: string;
  target_node_id: string;
  source_network: NetworkType;
  target_network: NetworkType;
  similarity_score: number;
  description: string;
  validated: boolean;
  created_at: string;
}

// ── Notifications ────────────────────────────────────────────────────────────

export interface Notification {
  id: string;
  type: string;
  trigger_condition: string;
  message: string;
  related_node_ids: string[];
  priority: Priority;
  created_at: string;
  read: boolean;
}

// ── Facts (Truth Layer) ──────────────────────────────────────────────────────

export interface VerifiedFact {
  id: string;
  claim: string;
  source_type: "PRIMARY" | "SECONDARY" | "SELF_REPORTED";
  source_url: string;
  source_title: string;
  source_author: string;
  verified_at: string;
  expiry_type: "STATIC" | "DYNAMIC";
  next_check_date: string | null;
  confidence: number;
  related_node_ids: string[];
  created_by: string;
}

// ── Streaming ────────────────────────────────────────────────────────────────

export interface StreamToken {
  token: string;
  agent: AgentRole;
  confidence: number;
  citing_nodes: string[];
}

export interface AgentStateUpdate {
  agent: AgentRole;
  state: "thinking" | "generating" | "done" | "error";
  message: string;
}

export interface SSEEvent {
  event_type: string;
  data: Record<string, unknown>;
  timestamp: string;
}

// ── Search ───────────────────────────────────────────────────────────────────

export interface SearchResult {
  score: number;
  node: GraphNode;
}

// ── Graph Stats ──────────────────────────────────────────────────────────────

export interface GraphStats {
  total_nodes: number;
  total_edges: number;
  nodes_by_type: Record<string, number>;
  edges_by_category: Record<string, number>;
}

// ── Pipeline Status ──────────────────────────────────────────────────────────

export interface PipelineStatus {
  capture_id: string;
  stage: number;
  stage_name: string;
  status: "processing" | "awaiting_review" | "completed" | "failed";
  proposal_id: string | null;
  error: string | null;
}
