"""Critique command — challenge a statement or decision."""

from __future__ import annotations

import textwrap

from cli.rendering import C, divider, horizontal_bar, prompt, spinner, term_width, subcommand_header
from memora.core.async_utils import run_async


def cmd_critique(app):
    subcommand_header(
        title="CRITIQUE",
        symbol="✕",
        color=C.DANGER,
        taglines=["Challenge assumptions · Counter-evidence", "Blind spot detection · Confidence scoring"],
        border="double",
    )

    statement = prompt(f"  Statement or decision to challenge\n  {C.DANGER}❯{C.RESET} ")
    if not statement or statement == "q":
        return

    strat = app._get_strategist()
    if not strat:
        print(f"\n  {C.RED}Strategist unavailable (no API key).{C.RESET}")
        return

    spinner("Gathering counter-evidence", 0.8)
    spinner("Identifying blind spots", 0.8)

    try:
        result = run_async(strat.critique(statement))
    except Exception as e:
        print(f"\n  {C.RED}Critique failed: {e}{C.RESET}")
        return

    print(f"\n{divider('═', C.RED)}")
    print(f"  {C.BOLD}{C.RED}CRITIQUE{C.RESET}")
    print(f"  {C.DIM}Confidence: {result.confidence:.0%}{C.RESET}")
    print(divider())

    if result.analysis:
        print()
        for line in textwrap.wrap(result.analysis, min(term_width() - 6, 68)):
            print(f"    {line}")

    if result.counter_evidence:
        print(f"\n  {C.BOLD}Counter-Evidence:{C.RESET}")
        for ce in result.counter_evidence:
            strength_color = {"strong": C.RED, "moderate": C.YELLOW, "weak": C.DIM}.get(ce.strength, C.WHITE)
            print(f"    {strength_color}[{ce.strength.upper()}]{C.RESET} {ce.point}")

    if result.blind_spots:
        print(f"\n  {C.BOLD}Blind Spots:{C.RESET}")
        for spot in result.blind_spots:
            print(f"    {C.YELLOW}!{C.RESET} {spot}")

    if result.citations:
        print(f"\n  {C.DIM}Evidence: {', '.join(result.citations[:5])}{C.RESET}")

    print(f"\n{divider('═', C.RED)}")
