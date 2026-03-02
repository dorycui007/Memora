"""Profile command — view and update the central You node."""

from __future__ import annotations

import asyncio
import hashlib
import textwrap

from uuid import UUID

from cli.rendering import (
    C, NETWORK_ICONS, divider, health_bar, menu_option, prompt,
    render_profile_card, spinner, term_width, subcommand_header,
)
from cli.tracker import PipelineTracker

from memora.graph.repository import YOU_NODE_ID


def cmd_profile(app):
    """View and update the central You node."""
    you_id = UUID(YOU_NODE_ID)
    you_node = app.repo.get_node(you_id)

    if not you_node:
        print(f"  {C.DANGER}You node not found.{C.RESET}")
        return

    props = you_node.properties or {}
    content = you_node.content or ""

    name = props.get("name", "You")
    if name == "You":
        name = you_node.title or "You"

    # Build fields
    fields: list[tuple[str, str]] = []
    if props.get("role"):
        fields.append(("Role", props["role"]))
    if props.get("organization"):
        fields.append(("Org", props["organization"]))
    if props.get("location"):
        fields.append(("Location", props["location"]))

    # Network badges
    if you_node.networks:
        nets = "".join(
            NETWORK_ICONS.get(n.value, f"[{n.value[0]}]")
            for n in you_node.networks
        )
        fields.append(("Networks", nets))

    if props.get("interests"):
        interests = props["interests"]
        if isinstance(interests, list):
            interests = ", ".join(interests)
        fields.append(("Interests", interests))
    if props.get("skills"):
        skills = props["skills"]
        if isinstance(skills, list):
            skills = ", ".join(skills)
        fields.append(("Skills", skills))

    # Extra properties
    shown = {"name", "role", "location", "organization", "interests",
             "skills", "bio", "relationship_to_user"}
    for k, v in props.items():
        if k not in shown and v:
            fields.append((k.replace("_", " ").title(), str(v)))

    # Bio
    bio = props.get("bio", "")
    if not bio and content and content != "Central node representing the user":
        bio = content

    # Confidence / decay
    conf = you_node.confidence if hasattr(you_node, "confidence") else None
    decay = you_node.decay_score if hasattr(you_node, "decay_score") else None

    # Summary strip
    summary_lines: list[str] = []
    try:
        edges = app.repo.get_edges(you_id)
        edge_count = len(edges)
        summary_lines.append(
            f"{C.BOLD}CONNECTIONS{C.RESET}  {C.BASE}{edge_count}{C.RESET}"
            f"       {C.DIM}nodes in your galaxy{C.RESET}"
        )
    except Exception:
        pass

    print()
    render_profile_card(
        name=name,
        fields=fields,
        confidence=conf,
        decay=decay,
        bio=bio,
        summary_lines=summary_lines,
        symbol="◆",
    )

    print(f"\n{divider()}")
    print(menu_option("1", "Update profile",  "Tell Memora about yourself"))
    print(menu_option("2", "View galaxy",     "See your galaxy graph"))
    print(menu_option("b", "Back",            "Return to main menu"))

    choice = prompt("profile> ")
    if choice == "1":
        _profile_update(app)
    elif choice == "2":
        from cli.commands.browse import browse_galaxy
        browse_galaxy(app)


def _profile_update(app):
    """Let user write self-descriptions to enrich the You node."""
    print(f"\n  {C.BOLD}Tell Memora about yourself.{C.RESET}")
    print(f"  {C.DIM}Examples: \"I'm a software engineer at Acme Corp\"{C.RESET}")
    print(f"  {C.DIM}          \"I live in San Francisco and love hiking\"{C.RESET}")
    print(f"  {C.DIM}          \"My goal is to launch a startup by Q3\"{C.RESET}")
    print(f"  {C.DIM}Press Enter twice to submit, 'cancel' to abort.{C.RESET}")
    print(f"  {C.DIM}{'─' * 60}{C.RESET}")

    lines = []
    while True:
        line = prompt(f"  {C.CYAN}| {C.RESET}")
        if line.lower() == "cancel":
            print(f"  {C.DIM}Cancelled.{C.RESET}")
            return
        if line == "" and lines and lines[-1] == "":
            lines.pop()
            break
        lines.append(line)

    text = "\n".join(lines).strip()
    if not text:
        print(f"  {C.DIM}Nothing to update.{C.RESET}")
        return

    pipeline = app._get_pipeline()
    if pipeline:
        from memora.graph.models import Capture
        content_hash = hashlib.sha256(text.encode()).hexdigest()
        capture = Capture(modality="text", raw_content=text, content_hash=content_hash)
        cid = app.repo.create_capture(capture)

        tracker = PipelineTracker()
        print()
        try:
            state = asyncio.run(pipeline.run(str(cid), text, on_stage=tracker.on_stage))
            from cli.commands.capture import _render_pipeline_result
            _render_pipeline_result(state, text)
            if state.proposal_id and state.status == "awaiting_review":
                action = prompt(f"\n  Approve this proposal? [{C.GREEN}Y{C.RESET}/n/skip] ")
                if action.lower() not in ("n", "no", "skip"):
                    from cli.commands.proposals import approve_proposal
                    approve_proposal(app, state.proposal_id[:8])
        except Exception as e:
            print(f"\n  {C.RED}Pipeline error: {e}{C.RESET}")
            _profile_direct_update(app, text)
    else:
        _profile_direct_update(app, text)


def _profile_direct_update(app, text: str):
    """Directly update the You node content without AI processing."""
    you_id = UUID(YOU_NODE_ID)
    you_node = app.repo.get_node(you_id)
    if not you_node:
        return

    current = you_node.content or ""
    if current == "Central node representing the user":
        new_content = text
    else:
        new_content = f"{current}\n{text}"

    app.repo.update_node(you_id, {"content": new_content})

    print(f"\n  {C.GREEN}Profile updated!{C.RESET}")
    print(f"  {C.DIM}Added: {text[:60]}{'...' if len(text) > 60 else ''}{C.RESET}")
