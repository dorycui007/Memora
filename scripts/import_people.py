"""Import key people into the knowledge graph.

Creates PERSON nodes for important contacts with relationship edges.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memora.config import load_settings
from memora.graph.models import (
    BaseNode, Edge, EdgeCategory, EdgeType, NetworkType, NodeType,
)
from memora.graph.repository import GraphRepository, YOU_NODE_ID


PEOPLE = [
    {
        "name": "Emily Su",
        "role": "President, MCSS",
        "organization": "MCSS",
        "relationship_to_user": "colleague, club executive",
        "networks": [NetworkType.CLUBS, NetworkType.SOCIAL],
    },
    {
        "name": "Kevin Chen",
        "role": "VP Finance, MCSS",
        "organization": "MCSS",
        "relationship_to_user": "colleague, club executive",
        "networks": [NetworkType.CLUBS],
    },
    {
        "name": "Sarah Park",
        "role": "President, UTMIST",
        "organization": "UTMIST",
        "relationship_to_user": "supervisor, club leadership",
        "networks": [NetworkType.CLUBS],
    },
    {
        "name": "Jason Li",
        "role": "Co-founder, Pyko",
        "organization": "Pyko",
        "relationship_to_user": "co-founder, business partner",
        "networks": [NetworkType.VENTURES, NetworkType.SOCIAL],
    },
    {
        "name": "Prof. David Fleet",
        "role": "Professor, Computer Science",
        "organization": "University of Toronto",
        "relationship_to_user": "professor, research mentor",
        "networks": [NetworkType.ACADEMIC],
    },
]


def import_people() -> None:
    """Import key people and relationship edges."""
    settings = load_settings()
    repo = GraphRepository(settings.db_path)

    for person in PEOPLE:
        node = BaseNode(
            node_type=NodeType.PERSON,
            title=person["name"],
            properties={
                "name": person["name"],
                "role": person["role"],
                "organization": person["organization"],
                "relationship_to_user": person["relationship_to_user"],
            },
            networks=person["networks"],
            confidence=1.0,
        )
        node.compute_content_hash()
        person_id = repo.create_node(node)
        print(f"  Created PERSON: {person['name']} ({person['role']})")

        # KNOWS edge from You
        repo.create_edge(Edge(
            source_id=YOU_NODE_ID,
            target_id=person_id,
            edge_type=EdgeType.KNOWS,
            edge_category=EdgeCategory.SOCIAL,
            confidence=1.0,
        ))

    repo.close()
    print(f"\nImported {len(PEOPLE)} people with KNOWS edges.")


if __name__ == "__main__":
    import_people()
