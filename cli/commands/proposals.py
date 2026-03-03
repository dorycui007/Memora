"""Proposals command — review and approve pending graph proposals."""

from __future__ import annotations

from uuid import UUID

from cli.rendering import C, horizontal_bar, prompt, subcommand_header

from memora.graph.models import ProposalStatus


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

        print(f"  {C.DIM}{pid}{C.RESET}  {status_color}{status:<10}{C.RESET}"
              f"  {C.DIM}route={route:<8}{C.RESET}"
              f"  conf={horizontal_bar(conf, 10)}"
              f"  {summary}")

    if pending_count > 0:
        print(f"\n  {C.BOLD}Approve a proposal?{C.RESET}")
        pid = prompt("  Proposal ID (or 'skip'): ")
        if pid and pid != "skip":
            approve_proposal(app, pid)


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
    confirm = prompt(f"  Approve proposal {str(full_id)[:8]}? [{C.GREEN}Y{C.RESET}/n] ")
    if confirm.lower() in ("n", "no"):
        return

    try:
        app.repo.update_proposal_status(full_id, ProposalStatus.APPROVED, reviewer="cli_user")
        success = app.repo.commit_proposal(full_id)
        if success:
            print(f"\n  {C.GREEN}Proposal approved and committed to graph!{C.RESET}")
        else:
            print(f"\n  {C.YELLOW}Proposal approved but commit failed.{C.RESET}")
    except Exception as e:
        print(f"  {C.RED}Error: {e}{C.RESET}")
