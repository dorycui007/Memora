"""Import academic courses into the knowledge graph.

Creates COURSE nodes and PREREQUISITE_OF edges for the academic pathway.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memora.config import load_settings
from memora.graph.models import (
    BaseNode, Edge, EdgeCategory, EdgeType, NetworkType, NodeType,
)
from memora.graph.repository import GraphRepository


# Course data: (code, name, semester, status, grade, credits, prerequisites)
COURSES = [
    # Year 1
    ("CSC108", "Introduction to Computer Programming", "Fall 2024", "completed", "A", 0.5, []),
    ("CSC148", "Introduction to Computer Science", "Winter 2025", "completed", "A", 0.5, ["CSC108"]),
    ("MAT102", "Introduction to Mathematical Proofs", "Fall 2024", "completed", "A-", 0.5, []),
    ("MAT135", "Calculus I", "Fall 2024", "completed", "A", 0.5, []),
    ("MAT136", "Calculus II", "Winter 2025", "completed", "A", 0.5, ["MAT135"]),
    ("STA107", "Introduction to Probability and Modelling", "Winter 2025", "completed", "A-", 0.5, []),

    # Year 2
    ("CSC207", "Software Design", "Fall 2025", "enrolled", "", 0.5, ["CSC148"]),
    ("CSC236", "Introduction to Theory of Computation", "Fall 2025", "enrolled", "", 0.5, ["CSC148", "MAT102"]),
    ("CSC258", "Computer Organization", "Winter 2026", "planned", "", 0.5, ["CSC148"]),
    ("MAT223", "Linear Algebra I", "Fall 2025", "enrolled", "", 0.5, []),
    ("MAT232", "Multivariable Calculus", "Winter 2026", "planned", "", 0.5, ["MAT136"]),
    ("STA256", "Probability and Statistics I", "Winter 2026", "planned", "", 0.5, ["MAT136", "STA107"]),

    # Year 3 (planned)
    ("CSC311", "Introduction to Machine Learning", "Fall 2026", "planned", "", 0.5, ["CSC207", "MAT223", "STA256"]),
    ("CSC343", "Introduction to Databases", "Fall 2026", "planned", "", 0.5, ["CSC207"]),
    ("CSC369", "Operating Systems", "Winter 2027", "planned", "", 0.5, ["CSC258", "CSC207"]),
    ("MAT224", "Linear Algebra II", "Fall 2026", "planned", "", 0.5, ["MAT223"]),
    ("STA302", "Methods of Data Analysis I", "Winter 2027", "planned", "", 0.5, ["STA256"]),

    # Year 4 (planned)
    ("CSC412", "Probabilistic Learning and Reasoning", "Fall 2027", "planned", "", 0.5, ["CSC311", "STA256"]),
    ("CSC413", "Neural Networks and Deep Learning", "Fall 2027", "planned", "", 0.5, ["CSC311", "MAT224"]),
    ("CSC401", "Natural Language Computing", "Winter 2028", "planned", "", 0.5, ["CSC311"]),
]


def import_courses() -> None:
    """Import courses and prerequisite edges."""
    settings = load_settings()
    repo = GraphRepository(settings.db_path)

    course_ids: dict[str, str] = {}

    # Create course nodes
    for code, name, semester, status, grade, credits, _ in COURSES:
        node = BaseNode(
            node_type=NodeType.COURSE,
            title=f"{code} — {name}",
            properties={
                "code": code,
                "name": name,
                "semester": semester,
                "status": status,
                "grade": grade,
                "credits": credits,
            },
            networks=[NetworkType.ACADEMIC],
            confidence=1.0,
        )
        node.compute_content_hash()
        node_id = repo.create_node(node)
        course_ids[code] = str(node_id)
        print(f"  Created COURSE: {code} — {name} [{status}]")

    # Create prerequisite edges
    prereq_count = 0
    for code, _, _, _, _, _, prereqs in COURSES:
        for prereq_code in prereqs:
            if prereq_code in course_ids and code in course_ids:
                repo.create_edge(Edge(
                    source_id=course_ids[prereq_code],
                    target_id=course_ids[code],
                    edge_type=EdgeType.PREREQUISITE_OF,
                    edge_category=EdgeCategory.STRUCTURAL,
                    confidence=1.0,
                ))
                prereq_count += 1

    repo.close()
    print(f"\nImported {len(COURSES)} courses with {prereq_count} prerequisite edges.")


if __name__ == "__main__":
    import_courses()
