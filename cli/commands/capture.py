"""Capture command — record thoughts, events, decisions."""

from __future__ import annotations

import asyncio
import hashlib
import select
import sys
import textwrap

from cli.rendering import (
    C, NODE_ICONS, NETWORK_ICONS, box, divider, horizontal_bar, prompt, spinner, term_width,
    subcommand_header,
)
from cli.tracker import PipelineTracker


# Recommended max characters for a single capture.
CAPTURE_CHAR_LIMIT = 2000

# User-friendly messages for common pipeline errors.
_PIPELINE_ERROR_HINTS = {
    "IndexError": "The extraction model returned an unexpected format. Try rephrasing your capture.",
    "KeyError": "A required field was missing from the extraction result. Try simplifying your capture.",
    "TimeoutError": "The AI service took too long to respond. Please try again.",
    "ConnectionError": "Could not reach the AI service. Check your internet connection.",
    "AuthenticationError": "Your API key may be invalid or expired. Check your settings.",
    "RateLimitError": "Too many requests. Wait a moment and try again.",
}


def cmd_capture(app, force: bool = False):
    limit = CAPTURE_CHAR_LIMIT
    subcommand_header(
        title="CAPTURE",
        symbol="◆",
        color=C.ACCENT,
        taglines=[
            "Record a thought, event, decision, or observation.",
            f"Multi-line input · {limit:,} char recommended · Ctrl+C to cancel",
        ],
        border="simple",
    )
    print(f"  {C.DIM}Type your text below. Press Enter twice to submit, or 'cancel' to abort.{C.RESET}")
    print(f"  {C.DIM}{'─' * 60}{C.RESET}")

    text = _collect_input(limit)
    if text is None:
        return

    # Edit loop: let the user revise before submitting
    while True:
        _show_preview(text, limit)
        confirm = prompt(f"  Submit this capture? [{C.GREEN}Y{C.RESET}/n/e] ")
        choice = confirm.lower().strip()
        if choice in ("n", "no"):
            print(f"  {C.DIM}Discarded.{C.RESET}")
            return
        if choice in ("e", "edit"):
            edited = _edit_text(text)
            if edited is not None:
                text = edited
                continue
            # Edit cancelled, re-show preview
            continue
        # Y or empty = submit
        break

    pipeline = app._get_pipeline()
    if not pipeline:
        from memora.graph.models import Capture
        capture = Capture(
            modality="text",
            raw_content=text,
            content_hash=hashlib.sha256(text.encode()).hexdigest(),
        )
        cid = app.repo.create_capture(capture)
        _render_capture_stored(str(cid), text, ai=False)
        return

    from memora.graph.models import Capture
    content_hash = hashlib.sha256(text.encode()).hexdigest()

    if not force and app.repo.check_capture_exists(content_hash):
        print(f"\n  {C.YELLOW}Duplicate detected!{C.RESET} This content has already been captured.")
        override = prompt(f"  Submit anyway? [y/{C.GREEN}N{C.RESET}] ")
        if override.lower().strip() not in ("y", "yes"):
            return

    capture = Capture(
        modality="text",
        raw_content=text,
        content_hash=content_hash,
    )
    cid = app.repo.create_capture(capture)

    tracker = PipelineTracker()
    print()

    try:
        state = asyncio.run(pipeline.run(str(cid), text, on_stage=tracker.on_stage))
        _render_pipeline_result(state, text)

        if state.proposal_id and state.status == "awaiting_review" and not state.clarification_needed:
            _prompt_proposal_approval(app, state)

        if state.clarification_needed:
            print(f"\n  {C.YELLOW}The AI needs more context:{C.RESET}")
            print(f"  {C.DIM}{state.clarification_message}{C.RESET}")
            clarify = prompt(f"\n  {C.YELLOW}Provide clarification{C.RESET} (or 'skip'): ")
            if clarify and clarify.lower() != "skip":
                enriched = f"{text}\n\n[Clarification]: {clarify}"
                tracker2 = PipelineTracker()
                print()
                state2 = asyncio.run(pipeline.run(str(cid), enriched, on_stage=tracker2.on_stage))
                _render_pipeline_result(state2, enriched)
                if state2.proposal_id and state2.status == "awaiting_review":
                    _prompt_proposal_approval(app, state2)
    except Exception as e:
        _render_pipeline_error(e, str(cid), text)


def _collect_input(limit: int) -> str | None:
    """Collect multi-line input from the user. Returns stripped text or None if cancelled."""
    lines: list[str] = []
    while True:
        running = "\n".join(lines)
        char_total = len(running.strip())

        line = _read_capture_line(
            f"  {C.YELLOW}| {C.RESET}", char_total, limit,
        )

        if line is None:
            print(f"  {C.DIM}Cancelled.{C.RESET}")
            return None
        if line.strip().lower() == "cancel":
            print(f"  {C.DIM}Cancelled.{C.RESET}")
            return None
        if line == "" and lines and lines[-1] == "":
            lines.pop()
            break
        lines.append(line)

    text = "\n".join(lines).strip()
    if not text:
        print(f"  {C.DIM}Nothing to capture.{C.RESET}")
        return None
    return text


def _show_preview(text: str, limit: int) -> None:
    """Display a word-wrapped preview of the capture text."""
    char_count = len(text)
    w = max(term_width() - 8, 40)
    print(f"\n{divider()}")
    if char_count > limit:
        print(f"  {C.YELLOW}Warning:{C.RESET} {char_count:,} chars exceeds the recommended {limit:,} limit.")
        print(f"  {C.DIM}The capture will still be saved, but long texts may lose detail during extraction.{C.RESET}")
    print(f"  {C.BOLD}Preview{C.RESET} {C.DIM}({char_count:,} chars):{C.RESET}")
    for line in text.split("\n"):
        wrapped = textwrap.wrap(line, w) if line.strip() else [""]
        for wl in wrapped:
            print(f"  {C.DIM}>{C.RESET} {wl}")
    print(divider())


def _edit_text(text: str) -> str | None:
    """Allow user to re-enter text. Returns new text or None if cancelled."""
    print(f"\n  {C.DIM}Re-enter your text (Enter twice to finish, 'cancel' to keep original):{C.RESET}")
    print(f"  {C.DIM}{'─' * 60}{C.RESET}")
    new_text = _collect_input(CAPTURE_CHAR_LIMIT)
    if new_text is None:
        print(f"  {C.DIM}Keeping original text.{C.RESET}")
        return None
    return new_text


def _prompt_proposal_approval(app, state) -> None:
    """Show proposal details and prompt for approval, defaulting based on route."""
    from memora.graph.models import ProposalRoute

    p = state.proposal
    if p:
        print(f"\n  {C.BOLD}Proposed changes:{C.RESET}")
        if p.nodes_to_create:
            print(f"    Create {len(p.nodes_to_create)} node(s): ", end="")
            print(", ".join(n.title for n in p.nodes_to_create[:5]))
        if p.nodes_to_update:
            print(f"    Update {len(p.nodes_to_update)} existing node(s)")
        if p.edges_to_create:
            print(f"    Create {len(p.edges_to_create)} relationship(s)")

    # EXPLICIT-routed proposals (merges, deferred) default to No
    if state.route == ProposalRoute.EXPLICIT:
        action = prompt(f"\n  Approve this proposal? [y/{C.GREEN}N{C.RESET}/skip] ")
        if action.lower().strip() not in ("y", "yes"):
            if action.lower().strip() != "skip":
                print(f"  {C.DIM}Proposal saved for later review.{C.RESET}")
            return
    else:
        action = prompt(f"\n  Approve this proposal? [{C.GREEN}Y{C.RESET}/n/skip] ")
        if action.lower().strip() in ("n", "no", "skip"):
            return

    from cli.commands.proposals import approve_proposal
    approve_proposal(app, state.proposal_id[:8])


def _render_pipeline_error(exc: Exception, cid: str, text: str) -> None:
    """Show a user-friendly pipeline error message."""
    exc_type = type(exc).__name__
    hint = _PIPELINE_ERROR_HINTS.get(exc_type)

    print(f"\n  {C.RED}Pipeline error:{C.RESET} Something went wrong during extraction.")
    if hint:
        print(f"  {C.DIM}{hint}{C.RESET}")
    else:
        # Show a sanitized version of the error
        msg = str(exc)
        if len(msg) > 120:
            msg = msg[:120] + "..."
        print(f"  {C.DIM}Detail: {msg}{C.RESET}")

    print(f"\n  {C.DIM}Your text was saved (ID: {cid[:8]}...) but not processed.{C.RESET}")
    print(f"  {C.DIM}You can retry by capturing the same text with --force.{C.RESET}")


def _show_capture_counter(chars: int, limit: int):
    """Render a right-aligned char counter on the current line."""
    w = term_width()
    if chars > limit:
        color = C.RED
    elif chars > int(limit * 0.8):
        color = C.YELLOW
    else:
        color = C.DIM
    label = f"{chars:,}/{limit:,}"
    col = w - len(label)
    sys.stdout.write(f"\033[s\033[{col}G{color}{label}{C.RESET}\033[u")
    sys.stdout.flush()


def _read_capture_line(
    prompt_str: str, char_total: int, limit: int,
) -> str | None:
    """Read one line char-by-char so the counter updates per keystroke."""
    try:
        import tty, termios
    except ImportError:
        try:
            return input(f"\n{prompt_str}").strip()
        except (EOFError, KeyboardInterrupt):
            return None

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    buf: list[str] = []

    sys.stdout.write(f"\n{prompt_str}")
    sys.stdout.flush()
    _show_capture_counter(char_total, limit)

    try:
        tty.setcbreak(fd)
        while True:
            ch = sys.stdin.read(1)

            if ch in ("\r", "\n"):
                sys.stdout.write("\n")
                break
            elif ch in ("\x7f", "\x08"):
                if buf:
                    buf.pop()
                    sys.stdout.write("\b \b")
            elif ch == "\x03":
                # Ctrl+C — cancel
                sys.stdout.write("\n")
                return None
            elif ch == "\x04":
                # Ctrl+D — submit current line (like Enter)
                sys.stdout.write("\n")
                break
            elif ch == "\x1b":
                # Escape sequence (arrow keys, etc.) — consume and notify
                if select.select([sys.stdin], [], [], 0.05)[0]:
                    sys.stdin.read(1)
                    if select.select([sys.stdin], [], [], 0.05)[0]:
                        sys.stdin.read(1)
                # Brief visual feedback: bell character
                sys.stdout.write("\a")
                sys.stdout.flush()
                continue
            elif ch == "\t":
                for _ in range(4):
                    buf.append(" ")
                    sys.stdout.write(" ")
            elif ch >= " ":
                buf.append(ch)
                sys.stdout.write(ch)

            _show_capture_counter(
                char_total + len(buf), limit,
            )
            sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    return "".join(buf)


def _render_capture_stored(cid: str, text: str, ai: bool = True):
    preview = text[:80] + ("..." if len(text) > 80 else "")
    print(f"\n  {C.GREEN}Captured successfully!{C.RESET}")
    print(f"  {C.DIM}ID:{C.RESET}      {cid[:8]}...")
    print(f"  {C.DIM}Text:{C.RESET}    {preview}")
    print(f"  {C.DIM}AI:{C.RESET}      {'Processed' if ai else 'Stored only (no API key)'}")
    print()


def _render_pipeline_result(state, text: str):
    status_color = C.GREEN if state.status == "completed" else C.YELLOW if state.status == "awaiting_review" else C.RED

    content = f"  {C.DIM}ID:{C.RESET}       {state.capture_id[:8]}...\n"
    content += f"  {C.DIM}Status:{C.RESET}   {status_color}{state.status}{C.RESET}\n"
    content += f"  {C.DIM}Stage:{C.RESET}    {state.stage.name}\n"

    if state.proposal:
        p = state.proposal
        content += f"\n  {C.BOLD}Extraction Results:{C.RESET}\n"
        content += f"  {C.DIM}Confidence:{C.RESET}  {horizontal_bar(p.confidence, 20)}\n"
        content += f"  {C.DIM}Nodes:{C.RESET}       {len(p.nodes_to_create)} to create"
        if p.nodes_to_update:
            content += f", {len(p.nodes_to_update)} to update"
        content += f"\n  {C.DIM}Edges:{C.RESET}       {len(p.edges_to_create)} to create\n"

        if p.nodes_to_create:
            content += f"\n  {C.BOLD}Extracted Nodes:{C.RESET}\n"
            for node in p.nodes_to_create:
                icon = NODE_ICONS.get(node.node_type.value, " ")
                nets = " ".join(NETWORK_ICONS.get(n.value, f"[{n.value}]") for n in node.networks)
                content += f"    {icon} {C.BOLD}{node.title}{C.RESET} ({node.node_type.value})  {nets}\n"
                if node.content:
                    content += f"      {C.DIM}{node.content[:60]}{C.RESET}\n"

        if p.human_summary:
            content += f"\n  {C.BOLD}Summary:{C.RESET} {p.human_summary}\n"

    if state.clarification_needed:
        content += f"\n  {C.YELLOW}Clarification needed:{C.RESET} {state.clarification_message}\n"

    if state.error:
        content += f"\n  {C.RED}Error:{C.RESET} {state.error}\n"

    # Show post-commit warnings if any substages failed
    if hasattr(state, "warnings") and state.warnings:
        content += f"\n  {C.YELLOW}Post-processing warnings:{C.RESET}\n"
        for warning in state.warnings:
            content += f"    {C.DIM}- {warning}{C.RESET}\n"

    if state.proposal_id:
        content += f"\n  {C.DIM}Proposal ID:{C.RESET} {state.proposal_id[:8]}...\n"
        route_label = state.route.value if state.route else "?"
        content += f"  {C.DIM}Route:{C.RESET}       {route_label}\n"

    print()
    print(content)
