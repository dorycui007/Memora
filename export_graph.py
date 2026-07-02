#!/usr/bin/env python3
"""
Memora Knowledge Graph → Interactive vis.js Viewer
Extracts nodes + edges from DuckDB and generates a self-contained HTML file.

Usage:
    python3 export_graph.py              # uses default ~/.memora/graph/memora.duckdb
    python3 export_graph.py /path/to.db  # custom database path
"""

import sys
import json
import html as html_mod
from pathlib import Path
from datetime import datetime, date

DB_PATH = Path.home() / ".memora" / "graph" / "memora.duckdb"
if len(sys.argv) > 1:
    DB_PATH = Path(sys.argv[1])

OUTPUT_PATH = Path(__file__).parent / "graph_viewer.html"
YOU_NODE_ID = "00000000-0000-0000-0000-000000000001"

# ── Colors by node type ──
NODE_COLORS = {
    "PERSON":         "#f97316",
    "EVENT":          "#3b82f6",
    "COMMITMENT":     "#ef4444",
    "DECISION":       "#eab308",
    "GOAL":           "#10b981",
    "FINANCIAL_ITEM": "#14b8a6",
    "PROJECT":        "#a855f7",
    "NOTE":           "#64748b",
    "IDEA":           "#ec4899",
    "CONCEPT":        "#8b5cf6",
    "REFERENCE":      "#06b6d4",
    "INSIGHT":        "#f59e0b",
}

# ── Colors by edge category ──
EDGE_COLORS = {
    "SOCIAL":      "#f97316",
    "PERSONAL":    "#ef4444",
    "ASSOCIATIVE": "#64748b",
    "STRUCTURAL":  "#10b981",
    "TEMPORAL":    "#3b82f6",
    "PROVENANCE":  "#8b5cf6",
    "NETWORK":     "#06b6d4",
}


def json_serial(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)


def extract_data():
    import duckdb
    conn = duckdb.connect(str(DB_PATH), read_only=True)

    # ── Nodes ──
    raw_nodes = conn.execute("""
        SELECT id, node_type, title, content, properties, confidence,
               networks, decay_score, access_count, tags, created_at
        FROM nodes WHERE deleted = FALSE
    """).fetchall()

    cols_n = ["id", "node_type", "title", "content", "properties",
              "confidence", "networks", "decay_score", "access_count",
              "tags", "created_at"]

    nodes = []
    for row in raw_nodes:
        d = dict(zip(cols_n, row))
        # Parse properties JSON string
        props = {}
        if d["properties"]:
            try:
                props = json.loads(d["properties"]) if isinstance(d["properties"], str) else d["properties"]
            except (json.JSONDecodeError, TypeError):
                pass

        # Fix the "You" node title
        title = d["title"] or props.get("name", "")
        if d["id"] == YOU_NODE_ID:
            title = "You"

        nodes.append({
            "id": d["id"],
            "type": d["node_type"],
            "title": title,
            "content": d["content"] or "",
            "properties": props,
            "confidence": d["confidence"] or 0.5,
            "networks": d["networks"] or [],
            "decay_score": d["decay_score"] or 0.5,
            "access_count": d["access_count"] or 0,
            "tags": d["tags"] or [],
            "created_at": d["created_at"],
        })

    # ── Edges ──
    raw_edges = conn.execute("""
        SELECT e.id, e.source_id, e.target_id, e.edge_type, e.edge_category,
               e.properties, e.confidence, e.weight, e.bidirectional
        FROM edges e
        JOIN nodes s ON e.source_id = s.id AND s.deleted = FALSE
        JOIN nodes t ON e.target_id = t.id AND t.deleted = FALSE
    """).fetchall()

    cols_e = ["id", "source_id", "target_id", "edge_type", "edge_category",
              "properties", "confidence", "weight", "bidirectional"]

    # Build title lookup
    title_map = {n["id"]: n["title"] for n in nodes}

    edges = []
    for row in raw_edges:
        d = dict(zip(cols_e, row))
        props = {}
        if d["properties"]:
            try:
                props = json.loads(d["properties"]) if isinstance(d["properties"], str) else d["properties"]
            except (json.JSONDecodeError, TypeError):
                pass

        edges.append({
            "id": d["id"],
            "source": d["source_id"],
            "target": d["target_id"],
            "type": d["edge_type"] or "RELATED_TO",
            "category": d["edge_category"] or "ASSOCIATIVE",
            "properties": props,
            "confidence": d["confidence"] or 0.5,
            "weight": d["weight"] or 1.0,
            "bidirectional": bool(d["bidirectional"]),
            "source_title": title_map.get(d["source_id"], "?"),
            "target_title": title_map.get(d["target_id"], "?"),
        })

    conn.close()
    return nodes, edges


def make_node_description(n):
    """Build a short visible description for the node label (shown on the graph)."""
    ntype = n["type"]
    props = n["properties"]
    content = (n["content"] or "").replace("\n", " ").strip()

    if n["id"] == YOU_NODE_ID:
        return "First-year CS @ UTM\nCTO of Pyko EdTech"

    if ntype == "PERSON":
        role = props.get("role", "")
        org = props.get("organization", "")
        rel = props.get("relationship_to_user", "")
        parts = [p for p in [role, org] if p]
        if not parts and content:
            parts = [content[:60]]
        if rel and rel != "unknown" and rel != "self":
            parts.append(f"({rel})")
        return "; ".join(parts)[:80] if parts else ""

    if ntype == "COMMITMENT":
        status = props.get("status", "open")
        committed_to = props.get("committed_to", "")
        desc = props.get("description", content[:80])
        line = desc[:70] if desc else ""
        return f"{line}\nStatus: {status}" if line else f"Status: {status}"

    if ntype == "EVENT":
        date_str = props.get("event_date", "")
        location = props.get("location", "")
        parts = [p for p in [date_str, location] if p]
        summary = content[:60] if content else ""
        return f"{summary}\n{', '.join(parts)}" if parts else summary

    if ntype == "PROJECT":
        status = props.get("status", "")
        team = props.get("team", [])
        team_str = ", ".join(team[:3]) if team else ""
        parts = [p for p in [status, team_str] if p]
        summary = content[:60] if content else ""
        return f"{summary}\n{'; '.join(parts)}" if parts else summary

    if ntype == "NOTE":
        note_type = props.get("note_type", "")
        prefix = f"[{note_type}] " if note_type else ""
        return f"{prefix}{content[:80]}"

    if ntype == "GOAL":
        progress = props.get("progress", 0)
        status = props.get("status", "active")
        return f"{content[:60]}\nProgress: {progress:.0%} | {status}"

    if ntype == "DECISION":
        chosen = props.get("chosen_option", "")
        rationale = props.get("rationale", "")
        return f"Chose: {chosen}\n{rationale[:60]}" if chosen else content[:80]

    if ntype == "IDEA":
        maturity = props.get("maturity", "seed")
        return f"[{maturity}] {content[:70]}"

    if ntype == "FINANCIAL_ITEM":
        amount = props.get("amount", "")
        direction = props.get("direction", "")
        return f"{'$' + str(amount) if amount else ''} {direction}\n{content[:60]}"

    # Fallback: CONCEPT, REFERENCE, INSIGHT, etc.
    return content[:80] if content else ""


def build_vis_nodes(nodes):
    vis_nodes = []
    for n in nodes:
        is_you = n["id"] == YOU_NODE_ID
        decay = n["decay_score"] if n["decay_score"] else 0.5
        size = 45 if is_you else max(14, int(decay * 30 + 10))

        title = n["title"][:30] if n["title"] else n["type"]
        desc = make_node_description(n)

        # Label = short title only. Description goes into hover tooltip.
        label = title

        # Build detail text for modal
        net_str = ", ".join(n["networks"]) if n["networks"] else "None"
        tag_str = ", ".join(n["tags"]) if n["tags"] else "None"
        props_lines = "\n".join(f"  {k}: {v}" for k, v in n["properties"].items()) if n["properties"] else "  (none)"
        created = n["created_at"].isoformat() if isinstance(n["created_at"], (datetime, date)) else str(n["created_at"] or "")

        detail_body = (
            f"{n['content']}\n\n"
            f"Confidence: {n['confidence']:.0%}\n"
            f"Decay Score: {n['decay_score']:.0%}\n"
            f"Access Count: {n['access_count']}\n"
            f"Networks: {net_str}\n"
            f"Tags: {tag_str}\n"
            f"Created: {created[:16]}\n\n"
            f"Properties:\n{props_lines}"
        )

        color = NODE_COLORS.get(n["type"], "#64748b")

        vis_nodes.append({
            "id": n["id"],
            "label": label,
            "group": n["type"],
            "size": size,
            "hoverDesc": desc,
            "details": {
                "cat": n["type"],
                "catColor": color,
                "title": n["title"] or n["type"],
                "body": detail_body,
                "networks": n["networks"],
            }
        })

    return vis_nodes


def describe_edge(edge_type, category, src_title, tgt_title, src_type, tgt_type, src_content, tgt_content, src_props, tgt_props):
    """Generate a content-aware explanation using actual node data, not generic templates."""
    s = src_title or "Unknown"
    t = tgt_title or "Unknown"
    sc = (src_content or "").replace("\n", " ").strip()
    tc = (tgt_content or "").replace("\n", " ").strip()

    # ── KNOWS ──
    if edge_type == "KNOWS":
        # Pull actual context from content
        rel = tgt_props.get("relationship_to_user", "") or src_props.get("relationship_to_user", "")
        org = tgt_props.get("organization", "") or src_props.get("organization", "")
        role = tgt_props.get("role", "") or src_props.get("role", "")
        context_parts = [p for p in [role, org, rel] if p and p != "unknown" and p != "self"]
        context = f" ({', '.join(context_parts)})" if context_parts else ""
        # Use target's content for how they know each other
        how = tc[:120] if tc else ""
        return f"{s} knows {t}{context}.\n\n{how}" if how else f"{s} knows {t}{context}."

    # ── COMMITTED_TO ──
    if edge_type == "COMMITTED_TO":
        desc_text = tgt_props.get("description", "") or tc[:120]
        status = tgt_props.get("status", "open")
        due = tgt_props.get("due_date", "")
        due_str = f"\nDue: {due}" if due else ""
        return f"{s} committed to: {t}\n\n{desc_text}\n\nStatus: {status}{due_str}"

    # ── RESPONSIBLE_FOR ──
    if edge_type == "RESPONSIBLE_FOR":
        if tgt_type == "PROJECT":
            team = tgt_props.get("team", [])
            status = tgt_props.get("status", "")
            team_str = f"\nTeam: {', '.join(team)}" if team else ""
            return f"{s} owns and is accountable for {t}.\n\n{tc[:120]}{team_str}\nStatus: {status}"
        elif tgt_type == "EVENT":
            date = tgt_props.get("event_date", "")
            loc = tgt_props.get("location", "")
            parts = [p for p in [date, loc] if p]
            return f"{s} is responsible for {t}.\n\n{tc[:120]}\n{', '.join(parts)}" if parts else f"{s} is responsible for {t}.\n\n{tc[:120]}"
        return f"{s} is responsible for {t}.\n\n{tc[:120]}"

    # ── FELT_ABOUT ──
    if edge_type == "FELT_ABOUT":
        # The source's content or target's content should capture the sentiment
        sentiment_ctx = sc if "felt" in sc.lower() or "mad" in sc.lower() or "happy" in sc.lower() else tc
        if not sentiment_ctx:
            sentiment_ctx = sc or tc
        return f"{s} has feelings about {t}.\n\n\"{sentiment_ctx[:150]}\""

    # ── RELATED_TO (the most common — needs the most context) ──
    if edge_type == "RELATED_TO":
        # Person ↔ Person: explain the shared context
        if src_type == "PERSON" and tgt_type == "PERSON":
            src_ctx = sc[:80]
            tgt_ctx = tc[:80]
            return f"{s} and {t} are linked.\n\n{s}: {src_ctx}\n{t}: {tgt_ctx}"

        # Person ↔ Event: explain involvement
        if src_type == "PERSON" and tgt_type == "EVENT":
            date = tgt_props.get("event_date", "")
            return f"{s} was involved in {t}.\n\n{tc[:120]}" + (f"\nDate: {date}" if date else "")
        if src_type == "EVENT" and tgt_type == "PERSON":
            date = src_props.get("event_date", "")
            return f"{t} was involved in {s}.\n\n{sc[:120]}" + (f"\nDate: {date}" if date else "")

        # Person ↔ Project
        if src_type == "PERSON" and tgt_type == "PROJECT":
            role = src_props.get("role", "")
            return f"{s} works on {t}" + (f" as {role}" if role else "") + f".\n\n{tc[:120]}"
        if src_type == "PROJECT" and tgt_type == "PERSON":
            return f"{t} is part of project {s}.\n\n{sc[:120]}"

        # Commitment ↔ Commitment: same effort
        if src_type == "COMMITMENT" and tgt_type == "COMMITMENT":
            src_desc = src_props.get("description", sc[:80])
            tgt_desc = tgt_props.get("description", tc[:80])
            return f"Part of the same campaign:\n\n1. {s}: {src_desc[:80]}\n2. {t}: {tgt_desc[:80]}"

        # Note ↔ Event
        if src_type == "NOTE" and tgt_type == "EVENT":
            return f"Note about {t}:\n\n\"{sc[:150]}\""
        if src_type == "EVENT" and tgt_type == "NOTE":
            return f"Note about {s}:\n\n\"{tc[:150]}\""

        # Note ↔ Person
        if src_type == "NOTE" and tgt_type == "PERSON":
            return f"Note mentioning {t}:\n\n\"{sc[:150]}\""

        # Person ↔ Event (reverse)
        if src_type == "PERSON" and tgt_type == "NOTE":
            return f"{s} is mentioned in this note:\n\n\"{tc[:150]}\""

        # Event ↔ Event
        if src_type == "EVENT" and tgt_type == "EVENT":
            return f"Related events:\n\n{s}: {sc[:80]}\n{t}: {tc[:80]}"

        # Fallback: show both sides' content
        src_snip = sc[:100] if sc else "(no content)"
        tgt_snip = tc[:100] if tc else "(no content)"
        return f"{s} is connected to {t}.\n\n{s}: {src_snip}\n\n{t}: {tgt_snip}"

    # ── All other edge types: template + content ──
    templates = {
        "INSPIRED_BY":       f"{s} was inspired by {t}.",
        "CONTRADICTS":       f"{s} contradicts {t} — these are in tension.",
        "SIMILAR_TO":        f"{s} is similar to {t}.",
        "COMPLEMENTS":       f"{s} complements {t}.",
        "DERIVED_FROM":      f"{s} was derived from {t}.",
        "VERIFIED_BY":       f"{s} was verified by {t}.",
        "SOURCE_OF":         f"{s} is the source of {t}.",
        "EXTRACTED_FROM":    f"{s} was extracted from {t}.",
        "PRECEDED_BY":       f"{t} happened before {s}.",
        "EVOLVED_INTO":      f"{s} evolved into {t} over time.",
        "TRIGGERED":         f"{s} caused or triggered {t}.",
        "CONCURRENT_WITH":   f"{s} and {t} happened at the same time.",
        "DECIDED":           f"{s} made a decision regarding {t}.",
        "PART_OF":           f"{s} is part of {t}.",
        "CONTAINS":          f"{s} contains {t}.",
        "SUBTASK_OF":        f"{s} is a subtask of {t}.",
        "INTRODUCED_BY":     f"{t} introduced {s}.",
        "OWES_FAVOR":        f"{s} owes a favor to {t}.",
        "COLLABORATES_WITH": f"{s} and {t} collaborate together.",
        "REPORTS_TO":        f"{s} reports to {t}.",
        "BRIDGES":           f"Cross-network bridge: {s} connects to {t} across different life domains.",
        "MEMBER_OF":         f"{s} is a member of {t}.",
        "IMPACTS":           f"{s} impacts {t}.",
        "CORRELATES_WITH":   f"{s} and {t} tend to change together.",
    }

    base = templates.get(edge_type, f"{s} → {t} ({edge_type})")
    # Append content context for specificity
    context = tc[:120] if tc else sc[:120] if sc else ""
    return f"{base}\n\n{context}" if context else base


def build_vis_edges(edges, nodes_list):
    # Build lookup maps
    node_content = {n["id"]: n["content"] for n in nodes_list}
    node_type = {n["id"]: n["type"] for n in nodes_list}
    node_props = {n["id"]: n["properties"] for n in nodes_list}

    vis_edges = []
    for e in edges:
        cat_color = EDGE_COLORS.get(e["category"], "#64748b")
        arrows = "" if e["bidirectional"] else "to"
        width = max(1, min(3, e["weight"] * 2))

        explanation = describe_edge(
            e["type"], e["category"],
            e["source_title"], e["target_title"],
            node_type.get(e["source"], ""), node_type.get(e["target"], ""),
            node_content.get(e["source"], ""), node_content.get(e["target"], ""),
            node_props.get(e["source"], {}), node_props.get(e["target"], {}),
        )

        sticky = (
            f"{explanation}\n\n"
            f"Confidence: {e['confidence']:.0%}  |  "
            f"Weight: {e['weight']:.1f}  |  "
            f"{'Bidirectional' if e['bidirectional'] else 'Directed'}"
        )

        vis_edges.append({
            "from": e["source"],
            "to": e["target"],
            "arrows": arrows,
            "width": width,
            "color": {"color": cat_color + "66", "hover": cat_color, "highlight": cat_color},
            "stickyFrom": e["source_title"],
            "stickyTo": e["target_title"],
            "sticky": sticky,
            "edgeCat": e["category"],
            "edgeType": e["type"],
        })

    return vis_edges


def generate_html(vis_nodes, vis_edges, node_count, edge_count):
    nodes_json = json.dumps(vis_nodes, default=json_serial, indent=2)
    edges_json = json.dumps(vis_edges, default=json_serial, indent=2)

    # Build legend items from actual node types present
    present_types = sorted(set(n["group"] for n in vis_nodes))
    legend_items = ""
    for t in present_types:
        c = NODE_COLORS.get(t, "#64748b")
        legend_items += f'  <div class="legend-item"><div class="legend-dot" style="background:{c}; --glow:{c}80;"></div>{t}</div>\n'

    # Build group config
    group_entries = []
    for t, c in NODE_COLORS.items():
        r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
        group_entries.append(f"""
    '{t}': {{
      shape: 'box',
      color: {{
        background: 'rgba({r},{g},{b},0.12)',
        border: '{c}',
        highlight: {{ background: 'rgba({r},{g},{b},0.25)', border: '{c}' }},
        hover: {{ background: 'rgba({r},{g},{b},0.2)', border: '{c}' }}
      }},
      font: {{ color: '#e2e8f0', face: 'Inter, sans-serif', size: 13 }},
      borderWidth: 2,
      shadow: {{ enabled: true, color: 'rgba({r},{g},{b},0.35)', size: 18, x: 0, y: 0 }},
      shapeProperties: {{ borderRadius: 8 }},
      margin: {{ top: 10, bottom: 10, left: 14, right: 14 }}
    }}""")
    groups_js = ",".join(group_entries)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Memora — Knowledge Graph</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: radial-gradient(ellipse at 50% 30%, #16213e 0%, #1a1a2e 60%, #0f0f23 100%);
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    color: #e2e8f0; overflow: hidden;
  }}
  #network {{ width: 100vw; height: 100vh; }}
  #legend {{
    position: fixed; top: 20px; left: 20px;
    background: rgba(30,41,59,0.65);
    backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px; padding: 18px 20px;
    z-index: 100; min-width: 180px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.3);
  }}
  #legend h3 {{
    font-size: 11px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 1.5px; color: #94a3b8; margin-bottom: 12px;
  }}
  .legend-item {{
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 6px; font-size: 11px; font-weight: 500;
  }}
  .legend-dot {{
    width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0;
    box-shadow: 0 0 8px var(--glow);
  }}
  #title-badge {{
    position: fixed; bottom: 20px; left: 20px;
    background: rgba(30,41,59,0.55);
    backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 10px; padding: 12px 18px; z-index: 100;
  }}
  #title-badge h2 {{ font-size: 13px; font-weight: 700; }}
  #title-badge p {{ font-size: 10px; color: #64748b; margin-top: 2px; }}
  #modal-backdrop {{
    position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
    background: rgba(0,0,0,0.45);
    backdrop-filter: blur(6px); -webkit-backdrop-filter: blur(6px);
    display: none; justify-content: center; align-items: center;
    z-index: 1000; opacity: 0; transition: opacity 0.25s ease;
  }}
  #modal-backdrop.visible {{ display: flex; opacity: 1; }}
  #modal-card {{
    background: rgba(22,33,62,0.88);
    backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 20px; padding: 36px 32px 28px;
    max-width: 520px; width: 90%; max-height: 80vh; overflow-y: auto;
    box-shadow: 0 25px 60px rgba(0,0,0,0.5), 0 0 40px var(--modal-glow, rgba(100,100,200,0.1));
    position: relative; animation: modalIn 0.3s ease;
  }}
  @keyframes modalIn {{
    from {{ transform: translateY(20px) scale(0.97); opacity: 0; }}
    to   {{ transform: translateY(0) scale(1); opacity: 1; }}
  }}
  #modal-close {{
    position: absolute; top: 14px; right: 18px;
    background: none; border: none; color: #64748b;
    font-size: 22px; cursor: pointer; transition: color 0.2s;
  }}
  #modal-close:hover {{ color: #e2e8f0; }}
  #modal-category {{
    font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 1.5px; margin-bottom: 6px;
  }}
  #modal-title {{ font-size: 20px; font-weight: 700; margin-bottom: 14px; line-height: 1.3; }}
  .net-badge {{
    display: inline-block; font-size: 9px; font-weight: 600;
    padding: 2px 8px; border-radius: 6px; margin-right: 4px; margin-bottom: 4px;
    background: rgba(255,255,255,0.08); color: #94a3b8; text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  #modal-body {{
    font-size: 12px; line-height: 1.7; color: #cbd5e1;
    white-space: pre-line; margin-top: 12px;
  }}
  #modal-connections {{
    margin-top: 16px; padding-top: 12px;
    border-top: 1px solid rgba(255,255,255,0.07);
  }}
  #modal-connections h4 {{
    font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 1.2px; color: #64748b; margin-bottom: 8px;
  }}
  .conn-item {{
    font-size: 11px; color: #94a3b8; margin-bottom: 3px;
    padding-left: 12px; position: relative;
  }}
  .conn-item::before {{
    content: ''; position: absolute; left: 0; top: 5px;
    width: 5px; height: 5px; border-radius: 50%;
    background: var(--dot-color, #64748b);
  }}
  #edge-tooltip {{
    position: fixed;
    background: rgba(22,33,62,0.92);
    backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 12px; padding: 14px 18px;
    max-width: 320px;
    font-size: 12px; line-height: 1.6; color: #cbd5e1;
    box-shadow: 0 12px 40px rgba(0,0,0,0.4);
    z-index: 500; pointer-events: none;
    display: none; opacity: 0; transition: opacity 0.2s ease;
  }}
  #edge-tooltip.visible {{ display: block; opacity: 1; }}
  #edge-tooltip .tt-label {{
    font-size: 11px; font-weight: 700; color: #e2e8f0;
    margin-bottom: 6px;
  }}
  .tt-type {{
    display: inline-block; font-size: 10px; font-weight: 600;
    padding: 1px 6px; border-radius: 4px; margin-bottom: 6px;
    background: rgba(255,255,255,0.08); color: #94a3b8;
  }}
  #help-hint {{
    position: fixed; bottom: 20px; right: 20px;
    background: rgba(30,41,59,0.5);
    backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 8px; padding: 8px 14px;
    font-size: 10px; color: #64748b; z-index: 100;
  }}
</style>
</head>
<body>
<div id="network"></div>

<div id="legend">
  <h3>Knowledge Graph</h3>
{legend_items}</div>

<div id="title-badge">
  <h2>Memora &mdash; Knowledge Graph</h2>
  <p>{node_count} nodes &middot; {edge_count} edges &middot; Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
</div>

<div id="help-hint">Click node for details &middot; Hover edge for info &middot; Scroll to zoom &middot; Drag to move</div>

<div id="edge-tooltip">
  <div class="tt-label" id="tt-label"></div>
  <div id="tt-body"></div>
</div>

<div id="modal-backdrop">
  <div id="modal-card">
    <button id="modal-close">&times;</button>
    <div id="modal-category"></div>
    <h2 id="modal-title"></h2>
    <div id="modal-networks"></div>
    <div id="modal-body"></div>
    <div id="modal-connections"><h4>Connected To</h4><div id="modal-conn-list"></div></div>
  </div>
</div>

<script>
// ═══ EMBEDDED GRAPH DATA ═══
const RAW_NODES = {nodes_json};
const RAW_EDGES = {edges_json};

// ═══ BUILD VIS.JS DATASETS ═══
const nodes = new vis.DataSet(RAW_NODES);
const edges = new vis.DataSet(RAW_EDGES);

// ═══ NETWORK INIT ═══
const container = document.getElementById('network');
const data = {{ nodes, edges }};
const options = {{
  groups: {{ {groups_js}
  }},
  edges: {{
    width: 1.5,
    hoverWidth: 3,
    selectionWidth: 2.5,
    smooth: {{ type: 'continuous', roundness: 0.25 }},
    font: {{ size: 0 }}
  }},
  physics: {{
    solver: 'forceAtlas2Based',
    forceAtlas2Based: {{
      gravitationalConstant: -45,
      centralGravity: 0.01,
      springLength: 160,
      springConstant: 0.04,
      damping: 0.5,
      avoidOverlap: 0.5
    }},
    stabilization: {{ iterations: 500, fit: true }},
    maxVelocity: 30,
    minVelocity: 0.75
  }},
  interaction: {{
    hover: true,
    tooltipDelay: 0,
    hideEdgesOnDrag: true,
    zoomView: true,
    dragView: true
  }},
  layout: {{ randomSeed: 42 }}
}};

const network = new vis.Network(container, data, options);

// ═══ UNIFIED HOVER TOOLTIP (nodes + edges) ═══
const tooltip = document.getElementById('edge-tooltip');
const ttLabel = document.getElementById('tt-label');
const ttBody = document.getElementById('tt-body');
let tooltipActive = false;

function showTooltip(labelHtml, bodyHtml) {{
  ttLabel.innerHTML = labelHtml;
  ttBody.innerHTML = bodyHtml;
  tooltip.classList.add('visible');
  tooltipActive = true;
}}
function hideTooltip() {{
  tooltip.classList.remove('visible');
  tooltipActive = false;
}}

// Edge hover
network.on('hoverEdge', function(params) {{
  const edge = edges.get(params.edge);
  if (!edge || !edge.sticky) return;
  const label = '<span style="color:#e2e8f0">' + (edge.stickyFrom || '?') + '</span>  \\u2192  <span style="color:#e2e8f0">' + (edge.stickyTo || '?') + '</span>';
  const body = '<span class="tt-type">' + (edge.edgeType || '') + '</span> <span class="tt-type" style="background:rgba(255,255,255,0.04)">' + (edge.edgeCat || '') + '</span><br><br>' + edge.sticky.replace(/\\n/g, '<br>');
  showTooltip(label, body);
}});
network.on('blurEdge', function() {{ hideTooltip(); }});

// Node hover
network.on('hoverNode', function(params) {{
  const node = nodes.get(params.node);
  if (!node) return;
  const d = node.details || {{}};
  const color = d.catColor || '#64748b';
  const cat = d.cat || '';
  const title = d.title || node.label || '';
  const desc = node.hoverDesc || '';
  const nets = (d.networks && d.networks.length) ? d.networks.join(', ') : '';

  const label = '<span style="color:' + color + '">' + cat + '</span>';
  let body = '<div style="font-size:14px;font-weight:600;color:#f1f5f9;margin-bottom:8px">' + title.replace(/</g,'&lt;') + '</div>';
  if (desc) {{
    body += '<div style="color:#cbd5e1;line-height:1.6">' + desc.replace(/</g,'&lt;').replace(/\\n/g, '<br>') + '</div>';
  }}
  if (nets) {{
    body += '<div style="margin-top:8px;color:#64748b;font-size:10px">Networks: ' + nets + '</div>';
  }}
  showTooltip(label, body);
}});
network.on('blurNode', function() {{ hideTooltip(); }});

// Position tooltip at cursor
document.addEventListener('mousemove', function(e) {{
  if (!tooltipActive) return;
  const x = e.clientX + 18, y = e.clientY + 18;
  const tw = tooltip.offsetWidth, th = tooltip.offsetHeight;
  tooltip.style.left = (x + tw > window.innerWidth ? e.clientX - tw - 10 : x) + 'px';
  tooltip.style.top = (y + th > window.innerHeight ? e.clientY - th - 10 : y) + 'px';
}});

// ═══ NODE CLICK MODAL ═══
const backdrop = document.getElementById('modal-backdrop');
const modalCard = document.getElementById('modal-card');
const modalCat = document.getElementById('modal-category');
const modalTitle = document.getElementById('modal-title');
const modalNetworks = document.getElementById('modal-networks');
const modalBody = document.getElementById('modal-body');
const modalConnList = document.getElementById('modal-conn-list');

// Build adjacency map for connections list
const adjMap = {{}};
RAW_EDGES.forEach(function(e) {{
  if (!adjMap[e.from]) adjMap[e.from] = [];
  if (!adjMap[e.to]) adjMap[e.to] = [];
  adjMap[e.from].push({{ id: e.to, type: e.edgeType, dir: 'outgoing' }});
  adjMap[e.to].push({{ id: e.from, type: e.edgeType, dir: 'incoming' }});
}});

const nodeMap = {{}};
RAW_NODES.forEach(function(n) {{ nodeMap[n.id] = n; }});

network.on('click', function(params) {{
  if (params.nodes.length === 0) return;
  const nodeId = params.nodes[0];
  const node = nodes.get(nodeId);
  if (!node || !node.details) return;
  const d = node.details;

  modalCat.textContent = d.cat;
  modalCat.style.color = d.catColor;
  modalTitle.textContent = d.title;
  modalCard.style.setProperty('--modal-glow', d.catColor + '30');

  // Network badges
  modalNetworks.innerHTML = '';
  if (d.networks && d.networks.length) {{
    d.networks.forEach(function(net) {{
      const span = document.createElement('span');
      span.className = 'net-badge';
      span.textContent = net;
      modalNetworks.appendChild(span);
    }});
  }}

  modalBody.textContent = d.body;

  // Connections
  modalConnList.innerHTML = '';
  const conns = adjMap[nodeId] || [];
  conns.forEach(function(c) {{
    const target = nodeMap[c.id];
    if (!target) return;
    const div = document.createElement('div');
    div.className = 'conn-item';
    const targetColor = target.details ? target.details.catColor : '#64748b';
    div.style.setProperty('--dot-color', targetColor);
    const arrow = c.dir === 'outgoing' ? '\\u2192' : '\\u2190';
    div.innerHTML = '<strong>' + c.type + '</strong> ' + arrow + ' ' + (target.label || target.id.slice(0,8));
    modalConnList.appendChild(div);
  }});

  backdrop.style.display = 'flex';
  requestAnimationFrame(function() {{ backdrop.classList.add('visible'); }});
}});

document.getElementById('modal-close').addEventListener('click', closeModal);
backdrop.addEventListener('click', function(e) {{ if (e.target === backdrop) closeModal(); }});
document.addEventListener('keydown', function(e) {{ if (e.key === 'Escape') closeModal(); }});

function closeModal() {{
  backdrop.classList.remove('visible');
  setTimeout(function() {{ backdrop.style.display = 'none'; }}, 250);
}}
</script>
</body>
</html>"""


def main():
    print(f"Connecting to {DB_PATH}...")
    nodes, edges = extract_data()
    print(f"Extracted {len(nodes)} nodes, {len(edges)} edges")

    vis_nodes = build_vis_nodes(nodes)
    vis_edges = build_vis_edges(edges, nodes)

    html_content = generate_html(vis_nodes, vis_edges, len(nodes), len(edges))
    OUTPUT_PATH.write_text(html_content, encoding="utf-8")
    print(f"Written to {OUTPUT_PATH}")
    print(f"Open in browser: file://{OUTPUT_PATH}")


if __name__ == "__main__":
    main()
