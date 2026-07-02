"""Academic tracking — course roadmap, prerequisite chains, and GPA computation.

Manages COURSE nodes and PREREQUISITE_OF edges for academic pathway planning.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AcademicTracker:
    """Tracks academic courses, prerequisites, and GPA trends."""

    GRADE_POINTS = {
        "A+": 4.0, "A": 4.0, "A-": 3.7,
        "B+": 3.3, "B": 3.0, "B-": 2.7,
        "C+": 2.3, "C": 2.0, "C-": 1.7,
        "D+": 1.3, "D": 1.0, "D-": 0.7,
        "F": 0.0,
    }

    def __init__(self, repo) -> None:
        self._repo = repo

    def get_roadmap(self) -> dict[str, Any]:
        """Get the complete academic roadmap with courses and prerequisites."""
        from memora.graph.models import NodeFilter, NodeType, parse_properties

        filters = NodeFilter(node_types=[NodeType.COURSE], limit=200)
        courses = self._repo.query_nodes(filters)

        course_list = []
        for c in courses:
            props = parse_properties(c.properties)
            course_list.append({
                "id": str(c.id),
                "title": c.title,
                "code": props.get("code", ""),
                "name": props.get("name", c.title),
                "semester": props.get("semester", ""),
                "grade": props.get("grade", ""),
                "credits": props.get("credits", 0.5),
                "status": props.get("status", "planned"),
                "instructor": props.get("instructor", ""),
                "networks": [n.value for n in c.networks],
            })

        # Get prerequisite edges
        prerequisites = []
        for c in courses:
            edges = self._repo.get_edges(str(c.id), "outgoing")
            for e in edges:
                et = e.edge_type.value if hasattr(e.edge_type, "value") else str(e.edge_type)
                if et == "PREREQUISITE_OF":
                    prerequisites.append({
                        "from_id": str(e.source_id),
                        "to_id": str(e.target_id),
                    })

        return {
            "courses": course_list,
            "prerequisites": prerequisites,
            "stats": self._compute_stats(course_list),
        }

    def compute_gpa(self) -> dict[str, Any]:
        """Compute cumulative and per-semester GPA."""
        roadmap = self.get_roadmap()
        courses = roadmap["courses"]

        # Cumulative GPA
        total_points = 0.0
        total_credits = 0.0
        semester_gpas = {}

        for c in courses:
            grade = c.get("grade", "")
            credits = c.get("credits", 0.5)
            status = c.get("status", "")
            semester = c.get("semester", "")

            if status == "completed" and grade in self.GRADE_POINTS:
                points = self.GRADE_POINTS[grade] * credits
                total_points += points
                total_credits += credits

                if semester:
                    if semester not in semester_gpas:
                        semester_gpas[semester] = {"points": 0.0, "credits": 0.0}
                    semester_gpas[semester]["points"] += points
                    semester_gpas[semester]["credits"] += credits

        cumulative_gpa = total_points / total_credits if total_credits > 0 else 0.0

        semester_results = {}
        for sem, data in semester_gpas.items():
            semester_results[sem] = round(data["points"] / data["credits"], 2) if data["credits"] > 0 else 0.0

        return {
            "cumulative_gpa": round(cumulative_gpa, 2),
            "total_credits": total_credits,
            "semester_gpas": semester_results,
        }

    def get_prerequisite_chain(self, course_id: str) -> list[dict[str, Any]]:
        """Get the full prerequisite chain for a course (recursive)."""
        visited = set()
        chain = []
        self._traverse_prerequisites(course_id, visited, chain)
        return chain

    def _traverse_prerequisites(
        self, course_id: str, visited: set[str], chain: list[dict[str, Any]]
    ) -> None:
        """Recursively traverse prerequisite edges."""
        if course_id in visited:
            return
        visited.add(course_id)

        edges = self._repo.get_edges(course_id, "incoming")
        for e in edges:
            et = e.edge_type.value if hasattr(e.edge_type, "value") else str(e.edge_type)
            if et == "PREREQUISITE_OF":
                prereq_id = str(e.source_id)
                prereq = self._repo.get_node(prereq_id)
                if prereq:
                    from memora.graph.models import parse_properties
                    props = parse_properties(prereq.properties)
                    chain.append({
                        "id": prereq_id,
                        "title": prereq.title,
                        "code": props.get("code", ""),
                        "status": props.get("status", "planned"),
                    })
                    self._traverse_prerequisites(prereq_id, visited, chain)

    def _compute_stats(self, courses: list[dict]) -> dict[str, int]:
        """Compute course statistics."""
        stats = {
            "total": len(courses),
            "completed": 0,
            "enrolled": 0,
            "planned": 0,
            "dropped": 0,
        }
        for c in courses:
            status = c.get("status", "planned")
            if status in stats:
                stats[status] += 1
        return stats
