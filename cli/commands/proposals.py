"""Proposals command — review and approve pending graph proposals."""

from __future__ import annotations

import json
from uuid import UUID

from cli.rendering import C, horizontal_bar, prompt, subcommand_header

from memora.core.entity_resolution import EntityResolver, ResolutionCandidate, ResolutionOutcome, ResolutionResult
from memora.graph.models import GraphProposal, ProposalStatus


def cmd_proposals(app):
    try:
        proposals = app.repo.get_pending_proposals()
    except Exception:
        proposals = []

    try:
        all_proposals = app.repo.query_proposals(limit=20)
    except Exception:
        all_proposals = []

    pending_count = len(proposals)

    count_str = f"  {C.SIGNAL}{C.BOLD}({pending_count} pending){C.RESET}" if pending_count > 0 else ""
    subcommand_header(
        title="PROPOSALS",
        symbol="◆",
        color=C.ACCENT,
        taglines=[
            f"Review and approve AI-extracted graph changes{count_str}",
            "Accept or reject before they enter your knowledge graph",
        ],
        border="simple",
    )

    if not all_proposals:
        print(f"  {C.DIM}No proposals yet. Capture some text first!{C.RESET}")
        return

    for p in all_proposals:
        pid = str(p.get("id", ""))[:8]
        status = p.get("status", "?")
        route = p.get("route", "?")
        conf = p.get("confidence", 0)
        summary = p.get("human_summary", "")[:50]

        status_color = {
            "pending": C.YELLOW,
            "approved": C.GREEN,
            "rejected": C.RED,
        }.get(status, C.DIM)

        dup_flag = f"  {C.YELLOW}⚠ possible dup{C.RESET}" if _resolutions(p) else ""

        print(f"  {C.DIM}{pid}{C.RESET}  {status_color}{status:<10}{C.RESET}"
              f"  {C.DIM}route={route:<8}{C.RESET}"
              f"  conf={horizontal_bar(conf, 10)}"
              f"  {summary}{dup_flag}")

    if pending_count > 0:
        print(f"\n  {C.BOLD}Approve a proposal?{C.RESET}")
        pid = prompt("  Proposal ID (or 'skip'): ")
        if pid and pid != "skip":
            approve_proposal(app, pid)


def _resolutions(proposal_row: dict) -> list[dict]:
    """Parse the persisted entity-resolution candidates for a proposal row, if any."""
    raw = proposal_row.get("resolution_data")
    if not raw:
        return []
    data = json.loads(raw) if isinstance(raw, str) else raw
    return data or []


def approve_proposal(app, partial_id: str):
    try:
        matching_ids = app.repo.find_proposals_by_id_prefix(partial_id)
    except Exception as e:
        print(f"  {C.RED}Error: {e}{C.RESET}")
        return

    if not matching_ids:
        print(f"  {C.DIM}No pending proposal found with ID '{partial_id}'.{C.RESET}")
        return

    full_id = UUID(str(matching_ids[0]))

    row = app.repo.get_proposal(full_id)
    resolutions = _resolutions(row) if row else []
    merge_choices: dict[str, dict] = {}
    for candidate in resolutions:
        print(
            f"\n  {C.YELLOW}⚠{C.RESET} '{candidate['title']}' may already exist as "
            f"'{candidate['existing_title']}' ({candidate['score']:.0%} match)"
        )
        print(f"  {C.DIM}{candidate['reason']}{C.RESET}")
        answer = prompt(f"  Merge into '{candidate['existing_title']}' instead of creating new? [y/{C.GREEN}N{C.RESET}] ")
        if answer.lower() in ("y", "yes"):
            merge_choices[candidate["temp_id"]] = candidate

    if merge_choices:
        _apply_merge_choices(app, full_id, row, merge_choices)

    confirm = prompt(f"\n  Approve proposal {str(full_id)[:8]}? [{C.GREEN}Y{C.RESET}/n] ")
    if confirm.lower() in ("n", "no"):
        return

    try:
        app.repo.update_proposal_status(full_id, ProposalStatus.APPROVED, reviewer="cli_user")
        success = app.repo.commit_proposal(full_id)
        if success:
            print(f"\n  {C.GREEN}Proposal approved and committed to graph!{C.RESET}")
            _run_post_commit_enrichment(app, full_id)
        else:
            print(f"\n  {C.YELLOW}Proposal approved but commit failed.{C.RESET}")
    except Exception as e:
        print(f"  {C.RED}Error: {e}{C.RESET}")


def _run_post_commit_enrichment(app, proposal_id: UUID) -> None:
    """Run the same embeddings/bridges/health/notifications/truth-layer enrichment
    the auto-approve path runs — manual review never goes through the pipeline,
    so without this, manually-approved nodes get no embeddings or health/bridge data.
    """
    import asyncio

    try:
        row = app.repo.get_proposal(proposal_id)
        if not row:
            return
        raw = row.get("proposal_data")
        proposal_data = json.loads(raw) if isinstance(raw, str) else raw
        proposal = GraphProposal.model_validate(proposal_data)

        from memora.core.pipeline import ExtractionPipeline

        pipeline = ExtractionPipeline(
            repo=app.repo,
            vector_store=app._get_vector_store(),
            embedding_engine=app._get_embedding_engine(),
            settings=app.settings,
        )
        warnings = asyncio.run(pipeline.run_post_commit(
            capture_id=row["capture_id"], proposal_id=str(proposal_id), proposal=proposal,
        ))
        for w in warnings:
            print(f"  {C.DIM}{w}{C.RESET}")
    except Exception as e:
        print(f"  {C.DIM}(post-commit enrichment skipped: {e}){C.RESET}")


def _apply_merge_choices(app, proposal_id: UUID, row: dict, merge_choices: dict[str, dict]) -> None:
    """Rewrite the stored proposal, converting chosen nodes-to-create into merges."""
    raw = row.get("proposal_data")
    data = json.loads(raw) if isinstance(raw, str) else raw
    proposal = GraphProposal.model_validate(data)

    resolutions = [
        ResolutionResult(
            proposed_temp_id=temp_id,
            proposed_title=c["title"],
            outcome=ResolutionOutcome.MERGE,
            chosen=ResolutionCandidate(
                existing_node_id=c["existing_id"],
                existing_title=c["existing_title"],
                existing_node_type=c["existing_node_type"],
                combined_score=c["score"],
            ),
        )
        for temp_id, c in merge_choices.items()
    ]

    resolver = EntityResolver(app.repo)
    merged = resolver.apply_merges(proposal, resolutions)
    app.repo.update_proposal_data(proposal_id, merged.model_dump(mode="json"))
