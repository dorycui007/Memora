"""Import strategy documents as graph entities.

Parses strategy text and creates GOAL, COMMITMENT, and INSIGHT nodes.
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


STRATEGIC_GOALS = [
    {
        "title": "Enter Vector Institute lab by 3rd year",
        "content": "Secure a position in a Vector Institute affiliated lab by 3rd year of undergrad. Requires strong GPA, ML coursework, and research experience.",
        "properties": {
            "target_date": "2027-09-01",
            "status": "active",
            "priority": "critical",
            "success_criteria": "Accepted into a Vector-affiliated lab with research position",
            "progress": 0.15,
        },
        "networks": [NetworkType.ACADEMIC],
    },
    {
        "title": "Launch Pyko MVP",
        "content": "Launch minimum viable product of Pyko platform with core features. Target 50 beta users within first month.",
        "properties": {
            "target_date": "2026-06-01",
            "status": "active",
            "priority": "high",
            "progress": 0.35,
        },
        "networks": [NetworkType.VENTURES],
    },
    {
        "title": "Win MCSS VP Technology re-election",
        "content": "Campaign for and win re-election as VP Technology for MCSS. Build on achievements from current term.",
        "properties": {
            "target_date": "2026-04-01",
            "status": "active",
            "priority": "high",
            "progress": 0.5,
        },
        "networks": [NetworkType.CLUBS, NetworkType.GOVERNANCE],
    },
    {
        "title": "Maintain 3.7+ GPA",
        "content": "Maintain cumulative GPA of 3.7 or above to remain competitive for graduate school and Vector Institute.",
        "properties": {
            "status": "active",
            "priority": "high",
            "progress": 0.4,
        },
        "networks": [NetworkType.ACADEMIC],
    },
]


def import_strategy() -> None:
    """Import strategic goals."""
    settings = load_settings()
    repo = GraphRepository(settings.db_path)

    for goal_data in STRATEGIC_GOALS:
        node = BaseNode(
            node_type=NodeType.GOAL,
            title=goal_data["title"],
            content=goal_data["content"],
            properties=goal_data["properties"],
            networks=goal_data["networks"],
            confidence=1.0,
        )
        node.compute_content_hash()
        goal_id = repo.create_node(node)
        print(f"  Created GOAL: {goal_data['title']}")

        # RESPONSIBLE_FOR edge from You
        repo.create_edge(Edge(
            source_id=YOU_NODE_ID,
            target_id=goal_id,
            edge_type=EdgeType.RESPONSIBLE_FOR,
            edge_category=EdgeCategory.PERSONAL,
            confidence=1.0,
        ))

    repo.close()
    print(f"\nImported {len(STRATEGIC_GOALS)} strategic goals.")


if __name__ == "__main__":
    import_strategy()
