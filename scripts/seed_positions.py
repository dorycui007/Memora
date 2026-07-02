"""Seed strategic positions and organizations into the knowledge graph.

Creates POSITION and ORGANIZATION nodes with connecting edges
for Ericsson Cui's strategic roles.
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memora.config import load_settings
from memora.graph.models import (
    BaseNode, Edge, EdgeCategory, EdgeType, NetworkType, NodeType,
)
from memora.graph.repository import GraphRepository, YOU_NODE_ID


def seed_positions() -> None:
    """Create position and organization nodes."""
    settings = load_settings()
    repo = GraphRepository(settings.db_path)

    # ── Organizations ──
    orgs = [
        {
            "title": "MCSS — Mathematical and Computational Sciences Society",
            "properties": {
                "name": "MCSS",
                "org_type": "student society",
                "website": "https://mcss.club",
            },
            "networks": [NetworkType.CLUBS],
        },
        {
            "title": "UTMIST — UTM Information Security Team",
            "properties": {
                "name": "UTMIST",
                "org_type": "student society",
                "website": "https://utmist.ca",
            },
            "networks": [NetworkType.CLUBS],
        },
        {
            "title": "UTM Campus Council",
            "properties": {
                "name": "UTM Campus Council",
                "org_type": "governance body",
                "parent_org": "University of Toronto",
            },
            "networks": [NetworkType.GOVERNANCE],
        },
        {
            "title": "Pyko",
            "properties": {
                "name": "Pyko",
                "org_type": "startup",
            },
            "networks": [NetworkType.VENTURES],
        },
        {
            "title": "Vector Institute",
            "properties": {
                "name": "Vector Institute",
                "org_type": "research institute",
                "website": "https://vectorinstitute.ai",
            },
            "networks": [NetworkType.ACADEMIC],
        },
        {
            "title": "University of Toronto Mississauga",
            "properties": {
                "name": "UTM",
                "org_type": "university",
                "website": "https://utm.utoronto.ca",
            },
            "networks": [NetworkType.ACADEMIC],
        },
    ]

    org_ids = {}
    for org_data in orgs:
        node = BaseNode(
            node_type=NodeType.ORGANIZATION,
            title=org_data["title"],
            properties=org_data["properties"],
            networks=org_data["networks"],
            confidence=1.0,
        )
        node.compute_content_hash()
        node_id = repo.create_node(node)
        org_ids[org_data["properties"]["name"]] = str(node_id)
        print(f"  Created ORGANIZATION: {org_data['title']}")

    # ── Positions ──
    positions = [
        {
            "title": "VP Technology — MCSS",
            "properties": {
                "title": "VP Technology",
                "organization": "MCSS",
                "status": "active",
                "time_hrs_week": 8.0,
            },
            "networks": [NetworkType.CLUBS],
            "org_key": "MCSS",
        },
        {
            "title": "Associate Director — UTMIST",
            "properties": {
                "title": "Associate Director",
                "organization": "UTMIST",
                "status": "active",
                "time_hrs_week": 5.0,
            },
            "networks": [NetworkType.CLUBS],
            "org_key": "UTMIST",
        },
        {
            "title": "Co-founder & CTO — Pyko",
            "properties": {
                "title": "Co-founder & CTO",
                "organization": "Pyko",
                "status": "active",
                "time_hrs_week": 15.0,
            },
            "networks": [NetworkType.VENTURES],
            "org_key": "Pyko",
        },
        {
            "title": "Coopted Member — UTM Campus Council",
            "properties": {
                "title": "Coopted Member",
                "organization": "UTM Campus Council",
                "status": "target",
            },
            "networks": [NetworkType.GOVERNANCE],
            "org_key": "UTM Campus Council",
        },
        {
            "title": "Vector Institute Lab Researcher",
            "properties": {
                "title": "Lab Researcher",
                "organization": "Vector Institute",
                "status": "target",
            },
            "networks": [NetworkType.ACADEMIC],
            "org_key": "Vector Institute",
        },
    ]

    for pos_data in positions:
        node = BaseNode(
            node_type=NodeType.POSITION,
            title=pos_data["title"],
            properties=pos_data["properties"],
            networks=pos_data["networks"],
            confidence=1.0,
        )
        node.compute_content_hash()
        pos_id = repo.create_node(node)
        print(f"  Created POSITION: {pos_data['title']}")

        # HOLDS_POSITION edge from You
        repo.create_edge(Edge(
            source_id=YOU_NODE_ID,
            target_id=pos_id,
            edge_type=EdgeType.HOLDS_POSITION,
            edge_category=EdgeCategory.STRATEGIC,
            confidence=1.0,
        ))

        # MEMBER_OF edge to organization
        org_key = pos_data.get("org_key", "")
        if org_key and org_key in org_ids:
            repo.create_edge(Edge(
                source_id=pos_id,
                target_id=org_ids[org_key],
                edge_type=EdgeType.MEMBER_OF,
                edge_category=EdgeCategory.NETWORK,
                confidence=1.0,
            ))

    repo.close()
    print(f"\nSeeded {len(orgs)} organizations and {len(positions)} positions.")


if __name__ == "__main__":
    seed_positions()
