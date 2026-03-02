"""Council command — ask the AI council a question."""

from __future__ import annotations

import json
import textwrap

from cli.rendering import C, divider, horizontal_bar, prompt, spinner, term_width, council_header


def cmd_council(app):
    council_header()

    query = prompt(f"  What should the council deliberate?\n  {C.ACCENT}❯{C.RESET} ")
    if not query or query == "q":
        return

    orch = app._get_orchestrator()
    if not orch:
        print(f"\n  {C.RED}Council unavailable (no API key).{C.RESET}")
        return

    spinner("Routing query to agents", 0.8)
    spinner("Agents deliberating", 1.0)

    try:
        result = orch.run(query)
    except Exception as e:
        print(f"\n  {C.RED}Council error:{C.RESET} {e}")
        return

    _render_council_result(result)


def _render_council_result(result):
    print(f"\n{divider('═', C.CYAN)}")
    print(f"  {C.BOLD}{C.CYAN}COUNCIL RESPONSE{C.RESET}")
    print(f"  {C.DIM}Query type: {result.query_type.value} | "
          f"Confidence: {result.confidence:.0%} | "
          f"Rounds: {result.deliberation_rounds}{C.RESET}")

    if result.high_disagreement:
        print(f"  {C.YELLOW}High disagreement detected between agents{C.RESET}")
    print(divider())

    if result.agent_outputs:
        for out in result.agent_outputs:
            agent = out.get("agent", "unknown")
            conf = out.get("confidence", 0)
            color = {"archivist": C.YELLOW, "strategist": C.CYAN, "researcher": C.MAGENTA}.get(agent, C.WHITE)

            print(f"\n  {color}{C.BOLD}[{agent.upper()}]{C.RESET}  confidence: {horizontal_bar(conf, 15)}")

            content_text = out.get("content", "")
            if content_text:
                stripped = content_text.strip()
                if stripped.startswith("{") or stripped.startswith("["):
                    try:
                        parsed = json.loads(stripped)
                        if isinstance(parsed, dict) and parsed.get("human_summary"):
                            content_text = parsed["human_summary"]
                        else:
                            content_text = f"{C.DIM}(structured data returned){C.RESET}"
                    except json.JSONDecodeError:
                        pass
                for line in textwrap.wrap(content_text, min(term_width() - 6, 72)):
                    print(f"    {line}")

            citations = out.get("citations", [])
            if citations:
                print(f"    {C.DIM}Citations: {', '.join(citations[:5])}{C.RESET}")

    print(f"\n{divider()}")
    print(f"  {C.BOLD}{C.GREEN}SYNTHESIS{C.RESET}\n")
    for paragraph in result.synthesis.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        for line in textwrap.wrap(paragraph, min(term_width() - 6, 72)):
            print(f"    {line}")
        print()

    if result.citations:
        print(f"\n  {C.DIM}Sources: {', '.join(result.citations[:5])}{C.RESET}")

    print(f"\n{divider('═', C.CYAN)}")
