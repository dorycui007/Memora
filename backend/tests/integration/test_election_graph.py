"""Integration tests: University Student Union Election graph network.

Establishes a rich election scenario with candidates, voters, campaign events,
decisions, commitments, and cross-network interactions. Tests proposal creation,
commit, temp-ID resolution, edge ontology, filtering, and neighborhood queries.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from memora.agents.archivist import ArchivistAgent
from memora.core.pipeline import ExtractionPipeline
from memora.graph.models import (
    Capture,
    EdgeCategory,
    EdgeType,
    NetworkType,
    NodeFilter,
    NodeType,
    ProposalRoute,
)
from memora.graph.repository import GraphRepository


# ── Mock helpers ───────────────────────────────────────────────


def _make_openai_response(proposal_json: dict) -> MagicMock:
    resp = MagicMock()
    resp.output_text = json.dumps(proposal_json)
    resp.usage = MagicMock(input_tokens=500, output_tokens=300)
    return resp


def _make_pipeline(repo, mock_openai_response) -> ExtractionPipeline:
    mock_client = AsyncMock()
    mock_client.responses.create.return_value = mock_openai_response

    archivist = ArchivistAgent.__new__(ArchivistAgent)
    archivist._client = mock_client
    archivist._model = "gpt-5-nano"
    archivist._vector_store = None
    archivist._embedding_engine = None
    archivist._you_node_id = repo.get_you_node_id()
    archivist._system_prompt = "test"

    return ExtractionPipeline(
        repo=repo,
        archivist=archivist,
    )


def _create_capture(repo, content: str) -> str:
    import hashlib
    capture = Capture(
        raw_content=content,
        modality="text",
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
    )
    return str(repo.create_capture(capture))


# ── Proposal factories ────────────────────────────────────────


def _candidates_announcement() -> dict:
    """5 candidates announcing their campaigns for student union president."""
    return {
        "confidence": 0.92,
        "nodes_to_create": [
            {
                "temp_id": "person_aisha",
                "node_type": "PERSON",
                "title": "Aisha Nakamura",
                "content": "Presidential candidate, current VP of Academic Affairs. Running on platform of expanded tutoring and mental health resources.",
                "properties": {"name": "Aisha Nakamura", "role": "Presidential Candidate", "organization": "Student Union"},
                "confidence": 0.95,
                "networks": ["ACADEMIC", "SOCIAL"],
            },
            {
                "temp_id": "person_carlos",
                "node_type": "PERSON",
                "title": "Carlos Rivera",
                "content": "Presidential candidate, founder of Startup Society. Running on innovation and entrepreneurship platform.",
                "properties": {"name": "Carlos Rivera", "role": "Presidential Candidate", "organization": "Startup Society"},
                "confidence": 0.93,
                "networks": ["VENTURES", "SOCIAL"],
            },
            {
                "temp_id": "person_mei",
                "node_type": "PERSON",
                "title": "Mei-Lin Park",
                "content": "Presidential candidate, treasurer of Student Government. Running on fiscal transparency and budget reform.",
                "properties": {"name": "Mei-Lin Park", "role": "Presidential Candidate", "organization": "Student Government"},
                "confidence": 0.94,
                "networks": ["FINANCIAL", "SOCIAL"],
            },
            {
                "temp_id": "person_kwame",
                "node_type": "PERSON",
                "title": "Kwame Asante",
                "content": "Presidential candidate, captain of debate team. Running on diversity and inclusion platform.",
                "properties": {"name": "Kwame Asante", "role": "Presidential Candidate", "organization": "Debate Society"},
                "confidence": 0.91,
                "networks": ["SOCIAL", "PERSONAL_GROWTH"],
            },
            {
                "temp_id": "person_elena",
                "node_type": "PERSON",
                "title": "Elena Volkov",
                "content": "Presidential candidate, editor of campus newspaper. Running on transparency and free press platform.",
                "properties": {"name": "Elena Volkov", "role": "Presidential Candidate", "organization": "Campus Chronicle"},
                "confidence": 0.90,
                "networks": ["SOCIAL", "ACADEMIC"],
            },
            {
                "temp_id": "event_announcement",
                "node_type": "EVENT",
                "title": "Election Candidacy Announcements",
                "content": "Official announcement of all five presidential candidates at Student Union Hall.",
                "properties": {"event_type": "announcement", "location": "Student Union Hall", "participants": ["Aisha Nakamura", "Carlos Rivera", "Mei-Lin Park", "Kwame Asante", "Elena Volkov"]},
                "confidence": 0.95,
                "networks": ["SOCIAL", "ACADEMIC"],
            },
            {
                "temp_id": "project_election",
                "node_type": "PROJECT",
                "title": "Student Union Presidential Election 2026",
                "content": "Annual election for student union president with 5 candidates.",
                "properties": {"status": "active", "target_date": "2026-03-15"},
                "confidence": 0.96,
                "networks": ["SOCIAL", "ACADEMIC"],
            },
        ],
        "edges_to_create": [
            {"source_id": "person_aisha", "target_id": "event_announcement", "edge_type": "MEMBER_OF", "edge_category": "NETWORK", "confidence": 0.95},
            {"source_id": "person_carlos", "target_id": "event_announcement", "edge_type": "MEMBER_OF", "edge_category": "NETWORK", "confidence": 0.95},
            {"source_id": "person_mei", "target_id": "event_announcement", "edge_type": "MEMBER_OF", "edge_category": "NETWORK", "confidence": 0.95},
            {"source_id": "person_kwame", "target_id": "event_announcement", "edge_type": "MEMBER_OF", "edge_category": "NETWORK", "confidence": 0.95},
            {"source_id": "person_elena", "target_id": "event_announcement", "edge_type": "MEMBER_OF", "edge_category": "NETWORK", "confidence": 0.95},
            {"source_id": "event_announcement", "target_id": "project_election", "edge_type": "PART_OF", "edge_category": "STRUCTURAL", "confidence": 0.93},
        ],
        "nodes_to_update": [],
        "human_summary": "Five candidates announced for Student Union presidential election 2026.",
    }


def _campaign_events() -> dict:
    """Campaign debate, rally, and town hall events with voter interactions."""
    return {
        "confidence": 0.91,
        "nodes_to_create": [
            {
                "temp_id": "event_debate",
                "node_type": "EVENT",
                "title": "First Presidential Debate",
                "content": "All five candidates debated tuition policy, campus safety, and sustainability. Aisha and Carlos clashed on budget priorities.",
                "properties": {"event_type": "debate", "location": "Lecture Hall A", "participants": ["Aisha Nakamura", "Carlos Rivera", "Mei-Lin Park", "Kwame Asante", "Elena Volkov"]},
                "confidence": 0.93,
                "networks": ["SOCIAL", "ACADEMIC"],
            },
            {
                "temp_id": "event_rally_carlos",
                "node_type": "EVENT",
                "title": "Carlos Rivera Campaign Rally",
                "content": "Startup Society rally on the quad. 200+ students attended. Carlos pitched his innovation fund proposal.",
                "properties": {"event_type": "rally", "location": "Main Quad", "participants": ["Carlos Rivera"]},
                "confidence": 0.88,
                "networks": ["VENTURES", "SOCIAL"],
            },
            {
                "temp_id": "event_townhall_aisha",
                "node_type": "EVENT",
                "title": "Aisha Nakamura Town Hall",
                "content": "Q&A session in the library. Students raised concerns about tutoring waitlists and counseling access.",
                "properties": {"event_type": "town_hall", "location": "University Library", "participants": ["Aisha Nakamura"]},
                "confidence": 0.90,
                "networks": ["ACADEMIC", "SOCIAL", "HEALTH"],
            },
            # Voters
            {
                "temp_id": "person_jordan",
                "node_type": "PERSON",
                "title": "Jordan Williams",
                "content": "Junior, CS major. Attended debate and rally. Leaning toward Carlos for innovation fund.",
                "properties": {"name": "Jordan Williams", "role": "Voter", "organization": "CS Department"},
                "confidence": 0.85,
                "networks": ["ACADEMIC", "SOCIAL"],
            },
            {
                "temp_id": "person_priya",
                "node_type": "PERSON",
                "title": "Priya Sharma",
                "content": "Senior, pre-med. Supports Aisha's mental health platform. Volunteering for her campaign.",
                "properties": {"name": "Priya Sharma", "role": "Campaign Volunteer", "organization": "Pre-Med Society"},
                "confidence": 0.87,
                "networks": ["HEALTH", "SOCIAL", "ACADEMIC"],
            },
            {
                "temp_id": "person_tyler",
                "node_type": "PERSON",
                "title": "Tyler Okonkwo",
                "content": "Sophomore, political science. Writing election coverage for the campus paper. Neutral observer.",
                "properties": {"name": "Tyler Okonkwo", "role": "Reporter", "organization": "Campus Chronicle"},
                "confidence": 0.86,
                "networks": ["SOCIAL", "ACADEMIC"],
            },
            {
                "temp_id": "person_sophie",
                "node_type": "PERSON",
                "title": "Sophie Chen",
                "content": "Freshman, undeclared. Attended town hall, asking about first-year tutoring programs.",
                "properties": {"name": "Sophie Chen", "role": "Voter"},
                "confidence": 0.82,
                "networks": ["ACADEMIC", "SOCIAL"],
            },
            # Decision and note
            {
                "temp_id": "decision_endorsement",
                "node_type": "DECISION",
                "title": "Campus Chronicle Endorsement Decision",
                "content": "Editorial board decided to endorse Aisha Nakamura based on policy depth and feasibility.",
                "properties": {"chosen_option": "Aisha Nakamura", "options_considered": ["Aisha Nakamura", "Carlos Rivera", "Mei-Lin Park"], "rationale": "Strongest policy proposals with measurable outcomes"},
                "confidence": 0.89,
                "networks": ["SOCIAL", "ACADEMIC"],
            },
            {
                "temp_id": "note_debate_recap",
                "node_type": "NOTE",
                "title": "Debate Recap: Key Takeaways",
                "content": "Aisha strong on academics, Carlos strong on innovation, Mei-Lin focused on budget transparency. Kwame gave powerful diversity speech. Elena pushed for student media funding.",
                "properties": {"note_type": "summary"},
                "confidence": 0.90,
                "networks": ["SOCIAL", "ACADEMIC"],
            },
        ],
        "edges_to_create": [
            # Voter-event interactions
            {"source_id": "person_jordan", "target_id": "event_debate", "edge_type": "MEMBER_OF", "edge_category": "NETWORK", "confidence": 0.85},
            {"source_id": "person_jordan", "target_id": "event_rally_carlos", "edge_type": "MEMBER_OF", "edge_category": "NETWORK", "confidence": 0.84},
            {"source_id": "person_priya", "target_id": "event_townhall_aisha", "edge_type": "MEMBER_OF", "edge_category": "NETWORK", "confidence": 0.88},
            {"source_id": "person_sophie", "target_id": "event_townhall_aisha", "edge_type": "MEMBER_OF", "edge_category": "NETWORK", "confidence": 0.80},
            {"source_id": "person_tyler", "target_id": "event_debate", "edge_type": "MEMBER_OF", "edge_category": "NETWORK", "confidence": 0.86},
            # Social connections
            {"source_id": "person_priya", "target_id": "person_sophie", "edge_type": "KNOWS", "edge_category": "SOCIAL", "confidence": 0.75},
            {"source_id": "person_tyler", "target_id": "person_jordan", "edge_type": "KNOWS", "edge_category": "SOCIAL", "confidence": 0.72},
            # Endorsement decision
            {"source_id": "person_tyler", "target_id": "decision_endorsement", "edge_type": "RELATED_TO", "edge_category": "ASSOCIATIVE", "confidence": 0.85},
            # Note derived from debate
            {"source_id": "note_debate_recap", "target_id": "event_debate", "edge_type": "DERIVED_FROM", "edge_category": "PROVENANCE", "confidence": 0.92},
        ],
        "nodes_to_update": [],
        "human_summary": "Campaign events: debate, rally, town hall with voter interactions and endorsement decision.",
    }


def _campaign_promises() -> dict:
    """Candidate commitments, goals, and policy ideas."""
    return {
        "confidence": 0.90,
        "nodes_to_create": [
            # Aisha's commitments
            {
                "temp_id": "commit_tutoring",
                "node_type": "COMMITMENT",
                "title": "Expand Peer Tutoring Program",
                "content": "Aisha commits to doubling peer tutoring capacity and eliminating waitlists within one semester.",
                "properties": {"committed_by": "Aisha Nakamura", "status": "open", "priority": "high"},
                "confidence": 0.92,
                "networks": ["ACADEMIC"],
            },
            {
                "temp_id": "commit_counseling",
                "node_type": "COMMITMENT",
                "title": "24/7 Mental Health Hotline",
                "content": "Aisha pledges to establish a 24/7 student mental health support hotline by fall semester.",
                "properties": {"committed_by": "Aisha Nakamura", "status": "open", "priority": "critical"},
                "confidence": 0.91,
                "networks": ["HEALTH", "ACADEMIC"],
            },
            # Carlos's commitments
            {
                "temp_id": "commit_innovation_fund",
                "node_type": "COMMITMENT",
                "title": "Student Innovation Fund",
                "content": "Carlos pledges $50,000 annual fund for student startup grants, sourced from alumni donations.",
                "properties": {"committed_by": "Carlos Rivera", "status": "open", "priority": "high"},
                "confidence": 0.89,
                "networks": ["VENTURES", "FINANCIAL"],
            },
            {
                "temp_id": "idea_makerspace",
                "node_type": "IDEA",
                "title": "Campus Makerspace",
                "content": "Convert unused basement in engineering building into a 24/7 makerspace with 3D printers and prototyping tools.",
                "properties": {"domain": "education-tech", "maturity": "developing", "potential_impact": "high"},
                "confidence": 0.87,
                "networks": ["VENTURES", "ACADEMIC"],
            },
            # Mei-Lin's commitments
            {
                "temp_id": "commit_budget_audit",
                "node_type": "COMMITMENT",
                "title": "Full Budget Transparency Audit",
                "content": "Mei-Lin commits to publishing a full student union budget audit within 30 days of taking office.",
                "properties": {"committed_by": "Mei-Lin Park", "status": "open", "priority": "high"},
                "confidence": 0.93,
                "networks": ["FINANCIAL"],
            },
            {
                "temp_id": "fin_budget_realloc",
                "node_type": "FINANCIAL_ITEM",
                "title": "Proposed Budget Reallocation",
                "content": "Mei-Lin proposes shifting $25,000 from administrative overhead to student programming.",
                "properties": {"amount": 25000.00, "currency": "USD", "direction": "outflow", "category": "budget_reallocation"},
                "confidence": 0.88,
                "networks": ["FINANCIAL"],
            },
            # Kwame's goals
            {
                "temp_id": "goal_diversity",
                "node_type": "GOAL",
                "title": "Diversity & Inclusion Council",
                "content": "Establish a permanent D&I council with representatives from every student organization.",
                "properties": {"status": "active", "priority": "high", "success_criteria": "Council formed with 20+ org representatives"},
                "confidence": 0.90,
                "networks": ["SOCIAL", "PERSONAL_GROWTH"],
            },
            # Elena's goals
            {
                "temp_id": "goal_media_fund",
                "node_type": "GOAL",
                "title": "Independent Student Media Fund",
                "content": "Secure dedicated funding for student-run media to ensure editorial independence.",
                "properties": {"status": "active", "priority": "high", "success_criteria": "Approved annual budget of $15,000 for student media"},
                "confidence": 0.88,
                "networks": ["SOCIAL", "FINANCIAL"],
            },
            # Cross-candidate concept
            {
                "temp_id": "concept_student_gov",
                "node_type": "CONCEPT",
                "title": "Student Governance Reform",
                "content": "Recurring theme across all candidates: the current student government structure needs modernization.",
                "properties": {"definition": "Restructuring student government for better representation and efficiency", "domain": "governance", "complexity_level": "advanced"},
                "confidence": 0.86,
                "networks": ["SOCIAL", "ACADEMIC"],
            },
        ],
        "edges_to_create": [
            # Commitment ownership
            {"source_id": "commit_tutoring", "target_id": "commit_counseling", "edge_type": "RELATED_TO", "edge_category": "ASSOCIATIVE", "confidence": 0.85},
            {"source_id": "commit_innovation_fund", "target_id": "idea_makerspace", "edge_type": "INSPIRED_BY", "edge_category": "ASSOCIATIVE", "confidence": 0.80},
            {"source_id": "commit_budget_audit", "target_id": "fin_budget_realloc", "edge_type": "TRIGGERED", "edge_category": "TEMPORAL", "confidence": 0.88},
            {"source_id": "goal_diversity", "target_id": "concept_student_gov", "edge_type": "PART_OF", "edge_category": "STRUCTURAL", "confidence": 0.82},
            {"source_id": "goal_media_fund", "target_id": "concept_student_gov", "edge_type": "PART_OF", "edge_category": "STRUCTURAL", "confidence": 0.80},
            # Cross-candidate tensions
            {"source_id": "commit_innovation_fund", "target_id": "commit_budget_audit", "edge_type": "CONTRADICTS", "edge_category": "ASSOCIATIVE", "confidence": 0.70},
        ],
        "nodes_to_update": [],
        "human_summary": "Campaign promises: tutoring, mental health, innovation fund, budget reform, diversity council, media fund.",
    }


def _voting_day() -> dict:
    """Voting day events, results, and aftermath."""
    return {
        "confidence": 0.94,
        "nodes_to_create": [
            {
                "temp_id": "event_voting",
                "node_type": "EVENT",
                "title": "Election Day Voting",
                "content": "Record turnout of 3,200 students. Polls open 8am-8pm across 4 campus locations.",
                "properties": {"event_type": "election", "location": "Multiple Campus Locations", "participants": ["All registered students"]},
                "confidence": 0.96,
                "networks": ["SOCIAL", "ACADEMIC"],
            },
            {
                "temp_id": "event_results",
                "node_type": "EVENT",
                "title": "Election Results Announcement",
                "content": "Aisha Nakamura wins with 38% of votes. Carlos Rivera second with 27%. Mei-Lin Park third with 20%.",
                "properties": {"event_type": "announcement", "location": "Student Union Hall"},
                "confidence": 0.97,
                "networks": ["SOCIAL", "ACADEMIC"],
            },
            {
                "temp_id": "decision_winner",
                "node_type": "DECISION",
                "title": "Election Winner: Aisha Nakamura",
                "content": "Aisha Nakamura elected as Student Union President with 38% plurality.",
                "properties": {
                    "chosen_option": "Aisha Nakamura",
                    "options_considered": ["Aisha Nakamura", "Carlos Rivera", "Mei-Lin Park", "Kwame Asante", "Elena Volkov"],
                    "rationale": "Plurality vote winner",
                },
                "confidence": 0.98,
                "networks": ["SOCIAL", "ACADEMIC"],
            },
            {
                "temp_id": "insight_turnout",
                "node_type": "INSIGHT",
                "title": "Record Voter Turnout Driven by Candidate Diversity",
                "content": "The diverse range of platforms and backgrounds attracted previously disengaged students. First-year participation up 60%.",
                "properties": {"actionable": True, "cross_network": True, "strength": 0.85},
                "confidence": 0.87,
                "networks": ["SOCIAL", "ACADEMIC", "PERSONAL_GROWTH"],
            },
            # Post-election commitments
            {
                "temp_id": "commit_transition",
                "node_type": "COMMITMENT",
                "title": "Form Transition Team",
                "content": "Aisha commits to forming a transition team including members from rival campaigns.",
                "properties": {"committed_by": "Aisha Nakamura", "status": "open", "priority": "critical"},
                "confidence": 0.93,
                "networks": ["SOCIAL", "ACADEMIC"],
            },
            {
                "temp_id": "commit_coalition",
                "node_type": "COMMITMENT",
                "title": "Carlos-Aisha Innovation Coalition",
                "content": "Carlos agrees to chair an innovation committee under Aisha's administration.",
                "properties": {"committed_by": "Carlos Rivera", "committed_to": "Aisha Nakamura", "status": "open", "priority": "high"},
                "confidence": 0.88,
                "networks": ["VENTURES", "SOCIAL"],
            },
        ],
        "edges_to_create": [
            {"source_id": "event_voting", "target_id": "event_results", "edge_type": "PRECEDED_BY", "edge_category": "TEMPORAL", "confidence": 0.98},
            {"source_id": "event_results", "target_id": "decision_winner", "edge_type": "TRIGGERED", "edge_category": "TEMPORAL", "confidence": 0.97},
            {"source_id": "insight_turnout", "target_id": "event_voting", "edge_type": "DERIVED_FROM", "edge_category": "PROVENANCE", "confidence": 0.88},
            {"source_id": "commit_transition", "target_id": "decision_winner", "edge_type": "TRIGGERED", "edge_category": "TEMPORAL", "confidence": 0.90},
            {"source_id": "commit_coalition", "target_id": "commit_transition", "edge_type": "RELATED_TO", "edge_category": "ASSOCIATIVE", "confidence": 0.85},
        ],
        "nodes_to_update": [],
        "human_summary": "Election day: Aisha wins, coalition formed with Carlos, record turnout.",
    }


# ── Fixtures ───────────────────────────────────────────────────


@pytest.fixture
def repo():
    r = GraphRepository(db_path=None)
    yield r
    r.close()


# ── Tests ──────────────────────────────────────────────────────


class TestElectionCandidateAnnouncements:
    """Phase 1: Candidate announcements create person, event, and project nodes."""

    @pytest.mark.asyncio
    async def test_five_candidates_created(self, repo):
        cid = _create_capture(repo, "Five candidates announced for student union president.")
        proposal = _candidates_announcement()
        resp = _make_openai_response(proposal)
        pipeline = _make_pipeline(repo, resp)

        state = await pipeline.run(cid, "Five candidates announced for student union president.")

        assert state.status == "completed"
        nodes = repo.query_nodes(NodeFilter(node_types=[NodeType.PERSON], limit=50))
        assert len(nodes) == 6  # 5 candidates + You node

        names = {n.title for n in nodes}
        assert "Aisha Nakamura" in names
        assert "Carlos Rivera" in names
        assert "Mei-Lin Park" in names
        assert "Kwame Asante" in names
        assert "Elena Volkov" in names

    @pytest.mark.asyncio
    async def test_announcement_event_and_project_created(self, repo):
        cid = _create_capture(repo, "Election candidacy announcements at Student Union Hall.")
        resp = _make_openai_response(_candidates_announcement())
        pipeline = _make_pipeline(repo, resp)

        await pipeline.run(cid, "Election candidacy announcements at Student Union Hall.")

        events = repo.query_nodes(NodeFilter(node_types=[NodeType.EVENT], limit=50))
        assert len(events) == 1
        assert events[0].title == "Election Candidacy Announcements"

        projects = repo.query_nodes(NodeFilter(node_types=[NodeType.PROJECT], limit=50))
        assert len(projects) == 1
        assert "Election 2026" in projects[0].title

    @pytest.mark.asyncio
    async def test_candidates_linked_to_announcement(self, repo):
        cid = _create_capture(repo, "Candidates announced.")
        resp = _make_openai_response(_candidates_announcement())
        pipeline = _make_pipeline(repo, resp)

        await pipeline.run(cid, "Candidates announced.")

        events = repo.query_nodes(NodeFilter(node_types=[NodeType.EVENT], limit=50))
        event = events[0]
        edges = repo.get_edges(event.id, direction="incoming")
        # 5 candidates MEMBER_OF announcement
        member_edges = [e for e in edges if e.edge_type == EdgeType.MEMBER_OF]
        assert len(member_edges) == 5

    @pytest.mark.asyncio
    async def test_no_temp_ids_in_committed_edges(self, repo):
        cid = _create_capture(repo, "Candidates announced for election.")
        resp = _make_openai_response(_candidates_announcement())
        pipeline = _make_pipeline(repo, resp)

        await pipeline.run(cid, "Candidates announced for election.")

        rows = repo._conn.execute("SELECT source_id, target_id FROM edges").fetchall()
        for src, tgt in rows:
            assert len(src) == 36, f"source_id looks like temp_id: {src}"
            assert len(tgt) == 36, f"target_id looks like temp_id: {tgt}"

    @pytest.mark.asyncio
    async def test_multi_network_assignment(self, repo):
        cid = _create_capture(repo, "Candidates with multiple networks.")
        resp = _make_openai_response(_candidates_announcement())
        pipeline = _make_pipeline(repo, resp)

        await pipeline.run(cid, "Candidates with multiple networks.")

        nodes = repo.query_nodes(NodeFilter(node_types=[NodeType.PERSON], limit=50))
        carlos = next(n for n in nodes if n.title == "Carlos Rivera")
        assert NetworkType.VENTURES in carlos.networks
        assert NetworkType.SOCIAL in carlos.networks


class TestCampaignEvents:
    """Phase 2: Debates, rallies, town halls with voter interactions."""

    @pytest.mark.asyncio
    async def test_campaign_events_and_voters(self, repo):
        cid = _create_capture(repo, "Campaign events with voters.")
        resp = _make_openai_response(_campaign_events())
        pipeline = _make_pipeline(repo, resp)

        state = await pipeline.run(cid, "Campaign events with voters.")

        assert state.status == "completed"
        events = repo.query_nodes(NodeFilter(node_types=[NodeType.EVENT], limit=50))
        assert len(events) == 3  # debate, rally, town hall

        persons = repo.query_nodes(NodeFilter(node_types=[NodeType.PERSON], limit=50))
        assert len(persons) == 5  # Jordan, Priya, Tyler, Sophie + You

    @pytest.mark.asyncio
    async def test_voter_event_attendance(self, repo):
        cid = _create_capture(repo, "Voter attendance at events.")
        resp = _make_openai_response(_campaign_events())
        pipeline = _make_pipeline(repo, resp)

        await pipeline.run(cid, "Voter attendance at events.")

        events = repo.query_nodes(NodeFilter(node_types=[NodeType.EVENT], limit=50))
        debate = next(e for e in events if "Debate" in e.title)

        edges = repo.get_edges(debate.id, direction="incoming")
        attendees = [e for e in edges if e.edge_type == EdgeType.MEMBER_OF]
        # Jordan and Tyler attended the debate
        assert len(attendees) == 2

    @pytest.mark.asyncio
    async def test_social_connections_between_voters(self, repo):
        cid = _create_capture(repo, "Voter social connections.")
        resp = _make_openai_response(_campaign_events())
        pipeline = _make_pipeline(repo, resp)

        await pipeline.run(cid, "Voter social connections.")

        rows = repo._conn.execute(
            "SELECT edge_type FROM edges WHERE edge_type = 'KNOWS'"
        ).fetchall()
        assert len(rows) == 2  # Priya-Sophie, Tyler-Jordan

    @pytest.mark.asyncio
    async def test_endorsement_decision_created(self, repo):
        cid = _create_capture(repo, "Endorsement decision.")
        resp = _make_openai_response(_campaign_events())
        pipeline = _make_pipeline(repo, resp)

        await pipeline.run(cid, "Endorsement decision.")

        decisions = repo.query_nodes(NodeFilter(node_types=[NodeType.DECISION], limit=50))
        assert len(decisions) == 1
        assert "Endorsement" in decisions[0].title

    @pytest.mark.asyncio
    async def test_debate_recap_note_derived_from_event(self, repo):
        cid = _create_capture(repo, "Debate recap.")
        resp = _make_openai_response(_campaign_events())
        pipeline = _make_pipeline(repo, resp)

        await pipeline.run(cid, "Debate recap.")

        notes = repo.query_nodes(NodeFilter(node_types=[NodeType.NOTE], limit=50))
        assert len(notes) == 1
        assert "Debate Recap" in notes[0].title

        edges = repo.get_edges(notes[0].id, direction="outgoing")
        derived = [e for e in edges if e.edge_type == EdgeType.DERIVED_FROM]
        assert len(derived) == 1


class TestCampaignPromises:
    """Phase 3: Commitments, goals, ideas, financial items across candidates."""

    @pytest.mark.asyncio
    async def test_commitment_nodes_created(self, repo):
        cid = _create_capture(repo, "Campaign promises.")
        resp = _make_openai_response(_campaign_promises())
        pipeline = _make_pipeline(repo, resp)

        await pipeline.run(cid, "Campaign promises.")

        commits = repo.query_nodes(NodeFilter(node_types=[NodeType.COMMITMENT], limit=50))
        assert len(commits) == 4  # tutoring, counseling, innovation fund, budget audit

        titles = {c.title for c in commits}
        assert "Expand Peer Tutoring Program" in titles
        assert "24/7 Mental Health Hotline" in titles
        assert "Student Innovation Fund" in titles
        assert "Full Budget Transparency Audit" in titles

    @pytest.mark.asyncio
    async def test_diverse_node_types(self, repo):
        cid = _create_capture(repo, "Diverse campaign proposals.")
        resp = _make_openai_response(_campaign_promises())
        pipeline = _make_pipeline(repo, resp)

        await pipeline.run(cid, "Diverse campaign proposals.")

        stats = repo.get_graph_stats()
        type_breakdown = stats.get("type_breakdown", {})
        assert type_breakdown.get("COMMITMENT", 0) == 4
        assert type_breakdown.get("IDEA", 0) == 1
        assert type_breakdown.get("FINANCIAL_ITEM", 0) == 1
        assert type_breakdown.get("GOAL", 0) == 2
        assert type_breakdown.get("CONCEPT", 0) == 1

    @pytest.mark.asyncio
    async def test_cross_candidate_contradiction_edge(self, repo):
        cid = _create_capture(repo, "Cross-candidate tensions.")
        resp = _make_openai_response(_campaign_promises())
        pipeline = _make_pipeline(repo, resp)

        await pipeline.run(cid, "Cross-candidate tensions.")

        rows = repo._conn.execute(
            "SELECT edge_type FROM edges WHERE edge_type = 'CONTRADICTS'"
        ).fetchall()
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_financial_network_nodes(self, repo):
        cid = _create_capture(repo, "Financial proposals.")
        resp = _make_openai_response(_campaign_promises())
        pipeline = _make_pipeline(repo, resp)

        await pipeline.run(cid, "Financial proposals.")

        nodes = repo.query_nodes(NodeFilter(networks=[NetworkType.FINANCIAL], limit=50))
        assert len(nodes) >= 3  # innovation fund, budget audit, budget reallocation, media fund


class TestVotingDay:
    """Phase 4: Election day, results, coalition formation."""

    @pytest.mark.asyncio
    async def test_voting_and_results_created(self, repo):
        cid = _create_capture(repo, "Election day and results.")
        resp = _make_openai_response(_voting_day())
        pipeline = _make_pipeline(repo, resp)

        state = await pipeline.run(cid, "Election day and results.")

        assert state.status == "completed"
        events = repo.query_nodes(NodeFilter(node_types=[NodeType.EVENT], limit=50))
        assert len(events) == 2  # voting + results

    @pytest.mark.asyncio
    async def test_winner_decision_node(self, repo):
        cid = _create_capture(repo, "Election winner announced.")
        resp = _make_openai_response(_voting_day())
        pipeline = _make_pipeline(repo, resp)

        await pipeline.run(cid, "Election winner announced.")

        decisions = repo.query_nodes(NodeFilter(node_types=[NodeType.DECISION], limit=50))
        assert len(decisions) == 1
        assert "Aisha Nakamura" in decisions[0].title

    @pytest.mark.asyncio
    async def test_temporal_chain(self, repo):
        cid = _create_capture(repo, "Temporal chain of election events.")
        resp = _make_openai_response(_voting_day())
        pipeline = _make_pipeline(repo, resp)

        await pipeline.run(cid, "Temporal chain of election events.")

        rows = repo._conn.execute(
            "SELECT edge_type FROM edges WHERE edge_type IN ('PRECEDED_BY', 'TRIGGERED')"
        ).fetchall()
        temporal_types = [r[0] for r in rows]
        assert "PRECEDED_BY" in temporal_types
        assert "TRIGGERED" in temporal_types

    @pytest.mark.asyncio
    async def test_insight_node_created(self, repo):
        cid = _create_capture(repo, "Voter turnout insight.")
        resp = _make_openai_response(_voting_day())
        pipeline = _make_pipeline(repo, resp)

        await pipeline.run(cid, "Voter turnout insight.")

        insights = repo.query_nodes(NodeFilter(node_types=[NodeType.INSIGHT], limit=50))
        assert len(insights) == 1
        assert "Turnout" in insights[0].title

    @pytest.mark.asyncio
    async def test_post_election_coalition(self, repo):
        cid = _create_capture(repo, "Post-election coalition.")
        resp = _make_openai_response(_voting_day())
        pipeline = _make_pipeline(repo, resp)

        await pipeline.run(cid, "Post-election coalition.")

        commits = repo.query_nodes(NodeFilter(node_types=[NodeType.COMMITMENT], limit=50))
        assert len(commits) == 2  # transition team + coalition
        titles = {c.title for c in commits}
        assert "Form Transition Team" in titles
        assert "Carlos-Aisha Innovation Coalition" in titles


class TestFullElectionGraph:
    """Phase 5: All proposals combined — full graph integrity tests."""

    @pytest.mark.asyncio
    async def test_cumulative_graph_stats(self, repo):
        """All 4 captures produce a rich interconnected graph."""
        proposals = [
            ("Candidate announcements.", _candidates_announcement()),
            ("Campaign events and voter interactions.", _campaign_events()),
            ("Campaign promises and policies.", _campaign_promises()),
            ("Voting day and results.", _voting_day()),
        ]

        for content, proposal_data in proposals:
            cid = _create_capture(repo, content)
            resp = _make_openai_response(proposal_data)
            pipeline = _make_pipeline(repo, resp)
            state = await pipeline.run(cid, content)
            assert state.status == "completed", f"Pipeline failed for: {content}"

        stats = repo.get_graph_stats()
        assert stats["node_count"] >= 30
        assert stats["edge_count"] >= 20

    @pytest.mark.asyncio
    async def test_all_node_types_represented(self, repo):
        """Election scenario exercises most node types."""
        proposals = [
            ("Candidates.", _candidates_announcement()),
            ("Events.", _campaign_events()),
            ("Promises.", _campaign_promises()),
            ("Voting.", _voting_day()),
        ]

        for content, proposal_data in proposals:
            cid = _create_capture(repo, content)
            resp = _make_openai_response(proposal_data)
            pipeline = _make_pipeline(repo, resp)
            await pipeline.run(cid, content)

        stats = repo.get_graph_stats()
        types_present = set(stats.get("type_breakdown", {}).keys())
        expected = {"PERSON", "EVENT", "PROJECT", "COMMITMENT", "DECISION",
                    "NOTE", "IDEA", "FINANCIAL_ITEM", "GOAL", "CONCEPT", "INSIGHT"}
        assert expected.issubset(types_present), f"Missing types: {expected - types_present}"

    @pytest.mark.asyncio
    async def test_all_edge_categories_used(self, repo):
        """Election graph uses structural, associative, temporal, provenance, social, network edges."""
        proposals = [
            ("Candidates.", _candidates_announcement()),
            ("Events.", _campaign_events()),
            ("Promises.", _campaign_promises()),
            ("Voting.", _voting_day()),
        ]

        for content, proposal_data in proposals:
            cid = _create_capture(repo, content)
            resp = _make_openai_response(proposal_data)
            pipeline = _make_pipeline(repo, resp)
            await pipeline.run(cid, content)

        rows = repo._conn.execute("SELECT DISTINCT edge_category FROM edges").fetchall()
        categories = {r[0] for r in rows}
        expected = {"STRUCTURAL", "ASSOCIATIVE", "TEMPORAL", "PROVENANCE", "SOCIAL", "NETWORK"}
        assert expected.issubset(categories), f"Missing categories: {expected - categories}"

    @pytest.mark.asyncio
    async def test_multiple_networks_populated(self, repo):
        """Election touches ACADEMIC, SOCIAL, VENTURES, FINANCIAL, HEALTH, PERSONAL_GROWTH."""
        proposals = [
            ("Candidates.", _candidates_announcement()),
            ("Events.", _campaign_events()),
            ("Promises.", _campaign_promises()),
            ("Voting.", _voting_day()),
        ]

        for content, proposal_data in proposals:
            cid = _create_capture(repo, content)
            resp = _make_openai_response(proposal_data)
            pipeline = _make_pipeline(repo, resp)
            await pipeline.run(cid, content)

        stats = repo.get_graph_stats()
        networks_present = set(stats.get("network_breakdown", {}).keys())
        expected = {"ACADEMIC", "SOCIAL", "VENTURES", "FINANCIAL", "HEALTH", "PERSONAL_GROWTH"}
        assert expected.issubset(networks_present), f"Missing networks: {expected - networks_present}"

    @pytest.mark.asyncio
    async def test_neighborhood_query(self, repo):
        """Neighborhood query from a candidate returns connected nodes."""
        cid = _create_capture(repo, "Candidate announcements for neighborhood test.")
        resp = _make_openai_response(_candidates_announcement())
        pipeline = _make_pipeline(repo, resp)
        await pipeline.run(cid, "Candidate announcements for neighborhood test.")

        persons = repo.query_nodes(NodeFilter(node_types=[NodeType.PERSON], limit=50))
        assert len(persons) > 0

        subgraph = repo.get_neighborhood(persons[0].id, hops=1)
        assert len(subgraph.nodes) >= 2  # person + at least announcement event
        assert len(subgraph.edges) >= 1

    @pytest.mark.asyncio
    async def test_filter_by_network(self, repo):
        """Filter nodes by specific network returns correct subset."""
        proposals = [
            ("Candidates.", _candidates_announcement()),
            ("Promises.", _campaign_promises()),
        ]

        for content, proposal_data in proposals:
            cid = _create_capture(repo, content)
            resp = _make_openai_response(proposal_data)
            pipeline = _make_pipeline(repo, resp)
            await pipeline.run(cid, content)

        ventures_nodes = repo.query_nodes(NodeFilter(networks=[NetworkType.VENTURES], limit=50))
        assert len(ventures_nodes) >= 3  # Carlos + innovation fund + makerspace

        for node in ventures_nodes:
            assert NetworkType.VENTURES in node.networks

    @pytest.mark.asyncio
    async def test_source_capture_linkage(self, repo):
        """All committed nodes have source_capture_id set."""
        cid = _create_capture(repo, "Candidate announcements for linkage test.")
        resp = _make_openai_response(_candidates_announcement())
        pipeline = _make_pipeline(repo, resp)
        await pipeline.run(cid, "Candidate announcements for linkage test.")

        from memora.graph.repository import YOU_NODE_ID
        nodes = repo.query_nodes(NodeFilter(limit=50))
        for node in nodes:
            if str(node.id) == YOU_NODE_ID:
                continue  # You node is system-created, no capture
            assert node.source_capture_id is not None
            assert str(node.source_capture_id) == cid

    @pytest.mark.asyncio
    async def test_edge_integrity_no_dangling(self, repo):
        """Every edge references existing nodes (no dangling references)."""
        proposals = [
            ("Candidates.", _candidates_announcement()),
            ("Events.", _campaign_events()),
            ("Promises.", _campaign_promises()),
            ("Voting.", _voting_day()),
        ]

        for content, proposal_data in proposals:
            cid = _create_capture(repo, content)
            resp = _make_openai_response(proposal_data)
            pipeline = _make_pipeline(repo, resp)
            await pipeline.run(cid, content)

        edges = repo._conn.execute("SELECT source_id, target_id FROM edges").fetchall()
        node_ids = {r[0] for r in repo._conn.execute("SELECT id FROM nodes WHERE deleted = FALSE").fetchall()}

        for src, tgt in edges:
            assert src in node_ids, f"Dangling source: {src}"
            assert tgt in node_ids, f"Dangling target: {tgt}"
