"""Academic route — course roadmap and GPA tracking."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from memora.api.deps import get_repo
from memora.graph.repository import GraphRepository

router = APIRouter()


@router.get("/academic/roadmap")
async def get_academic_roadmap(repo: GraphRepository = Depends(get_repo)):
    """Get course dependency DAG with status information."""
    from memora.graph.models import NodeFilter, NodeType, EdgeType, parse_properties

    # Get all course nodes
    filters = NodeFilter(node_types=[NodeType.COURSE], limit=200)
    courses = repo.query_nodes(filters)

    # Build course map
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
            "credits": props.get("credits"),
            "status": props.get("status", "planned"),
            "instructor": props.get("instructor", ""),
        })

    # Get prerequisite edges
    prerequisites = []
    for c in courses:
        edges = repo.get_edges(str(c.id), "outgoing")
        for e in edges:
            if hasattr(e.edge_type, 'value'):
                et = e.edge_type.value
            else:
                et = str(e.edge_type)
            if et == "PREREQUISITE_OF":
                prerequisites.append({
                    "from": str(e.source_id),
                    "to": str(e.target_id),
                })

    return {
        "courses": course_list,
        "prerequisites": prerequisites,
        "count": len(course_list),
    }


@router.get("/academic/gpa")
async def get_gpa(repo: GraphRepository = Depends(get_repo)):
    """Calculate GPA from completed courses."""
    from memora.graph.models import NodeFilter, NodeType, parse_properties

    filters = NodeFilter(node_types=[NodeType.COURSE], limit=200)
    courses = repo.query_nodes(filters)

    grade_points = {
        "A+": 4.0, "A": 4.0, "A-": 3.7,
        "B+": 3.3, "B": 3.0, "B-": 2.7,
        "C+": 2.3, "C": 2.0, "C-": 1.7,
        "D+": 1.3, "D": 1.0, "D-": 0.7,
        "F": 0.0,
    }

    total_points = 0.0
    total_credits = 0.0
    for c in courses:
        props = parse_properties(c.properties)
        grade = props.get("grade", "")
        credits = props.get("credits", 0.5)
        status = props.get("status", "")
        if status == "completed" and grade in grade_points:
            total_points += grade_points[grade] * credits
            total_credits += credits

    gpa = total_points / total_credits if total_credits > 0 else 0.0
    return {"gpa": round(gpa, 2), "total_credits": total_credits}
