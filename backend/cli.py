#!/usr/bin/env python3
"""Memora CLI — Interactive terminal interface for your knowledge graph.

A rich ASCII-based CLI that lets you capture thoughts, query the AI council,
browse your knowledge graph, review proposals, and monitor network health.
"""

from __future__ import annotations

import os
import sys
import json
import shutil
import textwrap
import time
import asyncio
from datetime import datetime
from pathlib import Path
from uuid import UUID

# ── Ensure the backend package is importable ──────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

# Suppress noisy logs unless user wants them
os.environ.setdefault("MEMORA_LOG_LEVEL", "WARNING")

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from memora.config import load_settings, Settings
from memora.graph.repository import GraphRepository
from memora.graph.models import NodeType, NetworkType, ProposalRoute, ProposalStatus

# ══════════════════════════════════════════════════════════════════════
# ANSI Colors & Styles
# ══════════════════════════════════════════════════════════════════════

class C:
    """ANSI color codes."""
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    ITALIC  = "\033[3m"
    UNDER   = "\033[4m"

    BLACK   = "\033[30m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"

    BG_BLACK   = "\033[40m"
    BG_RED     = "\033[41m"
    BG_GREEN   = "\033[42m"
    BG_YELLOW  = "\033[43m"
    BG_BLUE    = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN    = "\033[46m"
    BG_WHITE   = "\033[47m"

    # 256-color extras
    ORANGE  = "\033[38;5;208m"
    PINK    = "\033[38;5;213m"
    TEAL    = "\033[38;5;30m"
    GRAY    = "\033[38;5;245m"
    LGRAY   = "\033[38;5;250m"


def term_width() -> int:
    return shutil.get_terminal_size((80, 24)).columns


# ══════════════════════════════════════════════════════════════════════
# ASCII Art & Drawing Helpers
# ══════════════════════════════════════════════════════════════════════

BANNER = r"""
{cyan}{bold}
    __  ___
   /  |/  /__  ____ ___  ____  _________ _
  / /|_/ / _ \/ __ `__ \/ __ \/ ___/ __ `/
 / /  / /  __/ / / / / / /_/ / /  / /_/ /
/_/  /_/\___/_/ /_/ /_/\____/_/   \__,_/
{reset}
{dim}  Decision Intelligence Platform  v0.1.0
  ─────────────────────────────────────────{reset}
"""

BRAIN_ART = r"""
{magenta}         .----.
        / .  . \
       |  /||\\  |
       |  ||||  |
        \ `--' /
    {cyan}____`----'{magenta}____
   {cyan}/    {magenta}NODES{cyan}     \
  |   {dim}Your knowledge{reset}{cyan}  |
  |   {dim}graph awaits...{reset}{cyan} |
   \_______________/{reset}
"""

NETWORK_ICONS = {
    "ACADEMIC":        f"{C.BLUE}[A]{C.RESET}",
    "PROFESSIONAL":    f"{C.CYAN}[P]{C.RESET}",
    "FINANCIAL":       f"{C.GREEN}[$]{C.RESET}",
    "HEALTH":          f"{C.RED}[H]{C.RESET}",
    "PERSONAL_GROWTH": f"{C.MAGENTA}[G]{C.RESET}",
    "SOCIAL":          f"{C.YELLOW}[S]{C.RESET}",
    "VENTURES":        f"{C.ORANGE}[V]{C.RESET}",
}

NODE_ICONS = {
    "EVENT":           f"{C.YELLOW}*{C.RESET}",
    "PERSON":          f"{C.CYAN}@{C.RESET}",
    "COMMITMENT":      f"{C.RED}!{C.RESET}",
    "DECISION":        f"{C.GREEN}?{C.RESET}",
    "GOAL":            f"{C.MAGENTA}>{C.RESET}",
    "FINANCIAL_ITEM":  f"{C.GREEN}${C.RESET}",
    "NOTE":            f"{C.LGRAY}#{C.RESET}",
    "IDEA":            f"{C.PINK}~{C.RESET}",
    "PROJECT":         f"{C.BLUE}P{C.RESET}",
    "CONCEPT":         f"{C.TEAL}C{C.RESET}",
    "REFERENCE":       f"{C.DIM}R{C.RESET}",
    "INSIGHT":         f"{C.ORANGE}!{C.RESET}",
}


def print_banner():
    print(BANNER.format(cyan=C.CYAN, bold=C.BOLD, reset=C.RESET, dim=C.DIM))


def box(title: str, content: str, color: str = C.CYAN, width: int | None = None) -> str:
    """Draw a box around content."""
    w = width or min(term_width() - 4, 76)
    inner = w - 4

    lines = []
    lines.append(f"{color}{'=' * w}{C.RESET}")
    lines.append(f"{color}|{C.RESET} {C.BOLD}{title.center(inner)}{C.RESET} {color}|{C.RESET}")
    lines.append(f"{color}|{'─' * (w - 2)}|{C.RESET}")

    for raw_line in content.split("\n"):
        wrapped = textwrap.wrap(raw_line, inner) if raw_line.strip() else [""]
        for wl in wrapped:
            pad = inner - _visible_len(wl)
            lines.append(f"{color}|{C.RESET} {wl}{' ' * pad} {color}|{C.RESET}")

    lines.append(f"{color}{'=' * w}{C.RESET}")
    return "\n".join(lines)


def _visible_len(s: str) -> int:
    """Length of string excluding ANSI escape codes."""
    import re
    return len(re.sub(r"\033\[[^m]*m", "", s))


def horizontal_bar(value: float, width: int = 30, color: str = C.GREEN) -> str:
    """Render a horizontal bar chart segment."""
    filled = int(value * width)
    empty = width - filled
    pct = f"{value * 100:.0f}%"
    return f"{color}{'█' * filled}{C.DIM}{'░' * empty}{C.RESET} {pct}"


def spark_line(values: list[float], width: int = 20) -> str:
    """Tiny sparkline chart from a list of 0-1 floats."""
    sparks = " ▁▂▃▄▅▆▇█"
    if not values:
        return C.DIM + "no data" + C.RESET
    mn, mx = min(values), max(values)
    rng = mx - mn if mx != mn else 1
    chars = []
    for v in values[-width:]:
        idx = int((v - mn) / rng * 8)
        chars.append(sparks[idx])
    return C.CYAN + "".join(chars) + C.RESET


def spinner(msg: str, duration: float = 1.5):
    """Show a quick spinner animation."""
    frames = ["   [    ]", "   [=   ]", "   [==  ]", "   [=== ]", "   [====]",
              "   [ ===]", "   [  ==]", "   [   =]", "   [    ]"]
    end_time = time.time() + duration
    i = 0
    while time.time() < end_time:
        print(f"\r{C.CYAN}{frames[i % len(frames)]}{C.RESET} {C.DIM}{msg}{C.RESET}", end="", flush=True)
        time.sleep(0.12)
        i += 1
    print(f"\r{' ' * (len(msg) + 20)}\r", end="", flush=True)


def divider(char: str = "─", color: str = C.DIM) -> str:
    return f"{color}{char * min(term_width() - 2, 76)}{C.RESET}"


def menu_option(key: str, label: str, desc: str = "") -> str:
    extra = f"  {C.DIM}{desc}{C.RESET}" if desc else ""
    return f"  {C.BOLD}{C.CYAN}[{key}]{C.RESET}  {label}{extra}"


def prompt(msg: str = "> ") -> str:
    try:
        return input(f"\n{C.BOLD}{C.GREEN}{msg}{C.RESET}").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return "q"


# ══════════════════════════════════════════════════════════════════════
# Application State
# ══════════════════════════════════════════════════════════════════════

class MemoraApp:
    """Main CLI application."""

    def __init__(self):
        self.settings: Settings | None = None
        self.repo: GraphRepository | None = None
        self._pipeline = None
        self._orchestrator = None
        self._strategist = None

    def boot(self):
        """Initialize settings & repo."""
        print(f"\n{C.DIM}  Booting Memora...{C.RESET}")
        spinner("Loading configuration")

        self.settings = load_settings()
        self.repo = GraphRepository(db_path=self.settings.db_path)

        spinner("Connecting to graph database")

        api_key = self.settings.openai_api_key
        if not api_key or api_key.startswith("sk-PASTE"):
            print(f"\n  {C.YELLOW}Warning:{C.RESET} No valid OPENAI_API_KEY found in .env")
            print(f"  {C.DIM}AI features (capture, council, briefing) will be disabled.{C.RESET}")
            self._has_api_key = False
        else:
            self._has_api_key = True

        print(f"  {C.GREEN}Ready.{C.RESET} Data dir: {C.DIM}{self.settings.data_dir}{C.RESET}\n")

    def _get_pipeline(self):
        if self._pipeline:
            return self._pipeline
        if not self._has_api_key:
            return None
        try:
            from memora.core.pipeline import ExtractionPipeline
            self._pipeline = ExtractionPipeline(
                repo=self.repo,
                settings=self.settings,
            )
            return self._pipeline
        except Exception as e:
            print(f"  {C.RED}Pipeline init failed: {e}{C.RESET}")
            return None

    def _get_orchestrator(self):
        if self._orchestrator:
            return self._orchestrator
        if not self._has_api_key:
            return None
        try:
            from memora.agents.orchestrator import Orchestrator
            self._orchestrator = Orchestrator(
                api_key=self.settings.openai_api_key,
                repo=self.repo,
            )
            return self._orchestrator
        except Exception as e:
            print(f"  {C.RED}Orchestrator init failed: {e}{C.RESET}")
            return None

    def _get_strategist(self):
        if self._strategist:
            return self._strategist
        if not self._has_api_key:
            return None
        try:
            from memora.agents.strategist import StrategistAgent
            self._strategist = StrategistAgent(
                api_key=self.settings.openai_api_key,
                repo=self.repo,
            )
            return self._strategist
        except Exception as e:
            print(f"  {C.RED}Strategist init failed: {e}{C.RESET}")
            return None

    # ── Main Loop ─────────────────────────────────────────────────

    def run(self):
        self.boot()
        print_banner()
        self.show_quick_stats()

        while True:
            self.show_main_menu()
            choice = prompt("memora> ")

            if choice in ("q", "quit", "exit"):
                self.goodbye()
                break
            elif choice == "1":
                self.cmd_capture()
            elif choice == "2":
                self.cmd_council()
            elif choice == "3":
                self.cmd_browse()
            elif choice == "4":
                self.cmd_proposals()
            elif choice == "5":
                self.cmd_networks()
            elif choice == "6":
                self.cmd_stats()
            elif choice == "7":
                self.cmd_briefing()
            elif choice == "8":
                self.cmd_critique()
            else:
                print(f"  {C.DIM}Unknown command. Try 1-8 or 'q' to quit.{C.RESET}")

    def show_main_menu(self):
        print(f"\n{divider('═', C.CYAN)}")
        print(f"  {C.BOLD}{C.CYAN}MAIN MENU{C.RESET}")
        print(divider())
        print(menu_option("1", "Capture",    "Record a thought, event, or decision"))
        print(menu_option("2", "Council",    "Ask the AI council a question"))
        print(menu_option("3", "Browse",     "Explore your knowledge graph"))
        print(menu_option("4", "Proposals",  "Review pending graph proposals"))
        print(menu_option("5", "Networks",   "View network health & stats"))
        print(menu_option("6", "Stats",      "Full graph statistics & charts"))
        print(menu_option("7", "Briefing",   "Generate your daily briefing"))
        print(menu_option("8", "Critique",   "Challenge a statement or decision"))
        print(divider())
        print(f"  {C.DIM}[q] Quit{C.RESET}")

    def show_quick_stats(self):
        """Show a compact stats bar on startup."""
        if not self.repo:
            return
        try:
            stats = self.repo.get_graph_stats()
            nodes = stats.get("total_nodes", 0)
            edges = stats.get("total_edges", 0)
            nets = len(stats.get("nodes_by_network", {}))

            api_status = f"{C.GREEN}connected{C.RESET}" if self._has_api_key else f"{C.RED}no key{C.RESET}"
            status = (f"  {C.BOLD}{nodes}{C.RESET} nodes  {C.DIM}|{C.RESET}  "
                      f"{C.BOLD}{edges}{C.RESET} edges  {C.DIM}|{C.RESET}  "
                      f"{C.BOLD}{nets}{C.RESET} networks  {C.DIM}|{C.RESET}  "
                      f"API: {api_status}")

            print(box("GRAPH STATUS", status, C.DIM))
        except Exception:
            pass

    # ── 1. Capture ────────────────────────────────────────────────

    def cmd_capture(self):
        print(f"\n{box('CAPTURE', 'Record a new thought, event, meeting note, decision, or anything.', C.YELLOW)}")
        print(f"\n  {C.DIM}Type your text below. Press Enter twice to submit, or 'cancel' to abort.{C.RESET}")
        print(f"  {C.DIM}{'─' * 60}{C.RESET}")

        lines = []
        while True:
            line = prompt(f"  {C.YELLOW}| {C.RESET}")
            if line.lower() == "cancel":
                print(f"  {C.DIM}Cancelled.{C.RESET}")
                return
            if line == "" and lines and lines[-1] == "":
                lines.pop()
                break
            lines.append(line)

        text = "\n".join(lines).strip()
        if not text:
            print(f"  {C.DIM}Nothing to capture.{C.RESET}")
            return

        # Show preview
        print(f"\n{divider()}")
        print(f"  {C.BOLD}Preview:{C.RESET}")
        for line in text.split("\n"):
            print(f"  {C.DIM}>{C.RESET} {line}")
        print(divider())

        confirm = prompt(f"  Submit this capture? [{C.GREEN}Y{C.RESET}/n] ")
        if confirm.lower() in ("n", "no"):
            print(f"  {C.DIM}Discarded.{C.RESET}")
            return

        pipeline = self._get_pipeline()
        if not pipeline:
            # Still store the capture even without AI
            from memora.graph.models import Capture
            import hashlib
            capture = Capture(
                modality="text",
                raw_content=text,
                content_hash=hashlib.sha256(text.encode()).hexdigest(),
            )
            cid = self.repo.create_capture(capture)
            self._render_capture_stored(str(cid), text, ai=False)
            return

        # Run the pipeline
        from memora.graph.models import Capture
        import hashlib
        content_hash = hashlib.sha256(text.encode()).hexdigest()

        if self.repo.check_capture_exists(content_hash):
            print(f"\n  {C.YELLOW}Duplicate detected!{C.RESET} This content has already been captured.")
            return

        capture = Capture(
            modality="text",
            raw_content=text,
            content_hash=content_hash,
        )
        cid = self.repo.create_capture(capture)

        self._render_capture_animation()

        try:
            state = asyncio.run(pipeline.run(str(cid), text))
            self._render_pipeline_result(state, text)
        except Exception as e:
            print(f"\n  {C.RED}Pipeline error:{C.RESET} {e}")
            self._render_capture_stored(str(cid), text, ai=False)

    def _render_capture_animation(self):
        stages = [
            "Preprocessing text...",
            "Running archivist extraction...",
            "Resolving entities...",
            "Assembling proposal...",
            "Validating...",
        ]
        print()
        for stage in stages:
            spinner(stage, 0.6)

    def _render_capture_stored(self, cid: str, text: str, ai: bool = True):
        preview = text[:80] + ("..." if len(text) > 80 else "")
        content = f"""
  {C.GREEN}Captured successfully!{C.RESET}

  {C.DIM}ID:{C.RESET}      {cid[:8]}...
  {C.DIM}Text:{C.RESET}    {preview}
  {C.DIM}AI:{C.RESET}      {"Processed" if ai else "Stored only (no API key)"}
"""
        art = f"""
    {C.GREEN}     .---.
    ( o o )    Stored!
     \\   /
      '-'{C.RESET}
"""
        print(art)
        print(content)

    def _render_pipeline_result(self, state, text: str):
        preview = text[:80] + ("..." if len(text) > 80 else "")
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

        if state.proposal_id:
            content += f"\n  {C.DIM}Proposal ID:{C.RESET} {state.proposal_id[:8]}...\n"
            route_label = state.route.value if state.route else "?"
            content += f"  {C.DIM}Route:{C.RESET}       {route_label}\n"

        art = f"""
    {C.GREEN}     .------.
    |  {C.BOLD}DONE{C.RESET}{C.GREEN}  |
    |  {C.CYAN}====={C.RESET}{C.GREEN}  |
    |  {C.CYAN}====={C.RESET}{C.GREEN}  |
     '------'{C.RESET}
"""
        print(art)
        print(content)

    # ── 2. Council ────────────────────────────────────────────────

    def cmd_council(self):
        council_art = f"""
{C.CYAN}      .---.       .---.       .---.
     / A   \\     / S   \\     / R   \\
    |rchvst |   |trtgst |   |srcher |
     \\     /     \\     /     \\     /
      '---'       '---'       '---'
        \\           |           /
         '-----.----'-----.----'
               |  COUNCIL |
               '---------'{C.RESET}
"""
        print(council_art)
        print(f"  {C.BOLD}Ask the AI Council{C.RESET}")
        print(f"  {C.DIM}Your query will be routed to the best agent(s).{C.RESET}\n")

        query = prompt(f"  {C.CYAN}Query: {C.RESET}")
        if not query or query == "q":
            return

        orch = self._get_orchestrator()
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

        self._render_council_result(result)

    def _render_council_result(self, result):
        print(f"\n{divider('═', C.CYAN)}")
        print(f"  {C.BOLD}{C.CYAN}COUNCIL RESPONSE{C.RESET}")
        print(f"  {C.DIM}Query type: {result.query_type.value} | "
              f"Confidence: {result.confidence:.0%} | "
              f"Rounds: {result.deliberation_rounds}{C.RESET}")

        if result.high_disagreement:
            print(f"  {C.YELLOW}High disagreement detected between agents{C.RESET}")
        print(divider())

        # Agent outputs
        if result.agent_outputs:
            for out in result.agent_outputs:
                agent = out.get("agent", "unknown")
                conf = out.get("confidence", 0)
                color = {"archivist": C.YELLOW, "strategist": C.CYAN, "researcher": C.MAGENTA}.get(agent, C.WHITE)

                print(f"\n  {color}{C.BOLD}[{agent.upper()}]{C.RESET}  confidence: {horizontal_bar(conf, 15)}")

                content_text = out.get("content", "")
                if content_text:
                    for line in textwrap.wrap(content_text, min(term_width() - 6, 72)):
                        print(f"    {line}")

                citations = out.get("citations", [])
                if citations:
                    print(f"    {C.DIM}Citations: {', '.join(citations[:5])}{C.RESET}")

        # Synthesis
        print(f"\n{divider()}")
        print(f"  {C.BOLD}{C.GREEN}SYNTHESIS{C.RESET}\n")
        for line in textwrap.wrap(result.synthesis, min(term_width() - 6, 72)):
            print(f"    {line}")

        if result.citations:
            print(f"\n  {C.DIM}Sources: {', '.join(result.citations[:5])}{C.RESET}")

        print(f"\n{divider('═', C.CYAN)}")

    # ── 3. Browse Graph ───────────────────────────────────────────

    def cmd_browse(self):
        while True:
            print(f"\n{divider('═', C.BLUE)}")
            print(f"  {C.BOLD}{C.BLUE}BROWSE GRAPH{C.RESET}")
            print(divider())
            print(menu_option("1", "All nodes",     "List all nodes in the graph"))
            print(menu_option("2", "By type",       "Filter nodes by type"))
            print(menu_option("3", "By network",    "Filter by network"))
            print(menu_option("4", "Search",        "Search nodes by title"))
            print(menu_option("5", "Node detail",   "View a node and its connections"))
            print(menu_option("6", "Graph map",     "ASCII relationship graph around a node"))
            print(menu_option("7", "Full map",      "Visualize the entire graph"))
            print(menu_option("b", "Back",          "Return to main menu"))
            print(divider())

            choice = prompt("browse> ")
            if choice in ("b", "back", "q"):
                return
            elif choice == "1":
                self._browse_all_nodes()
            elif choice == "2":
                self._browse_by_type()
            elif choice == "3":
                self._browse_by_network()
            elif choice == "4":
                self._browse_search()
            elif choice == "5":
                self._browse_node_detail()
            elif choice == "6":
                self._browse_graph_map()
            elif choice == "7":
                self._browse_full_map()

    def _browse_all_nodes(self, filters=None):
        from memora.graph.models import NodeFilter
        f = filters or NodeFilter()
        try:
            nodes = self.repo.query_nodes(f)
        except Exception as e:
            print(f"  {C.RED}Error: {e}{C.RESET}")
            return

        if not nodes:
            print(f"\n  {C.DIM}No nodes found.{C.RESET}")
            print(BRAIN_ART.format(magenta=C.MAGENTA, cyan=C.CYAN, dim=C.DIM, reset=C.RESET))
            return

        print(f"\n  {C.BOLD}{len(nodes)} node(s) found{C.RESET}\n")
        self._render_node_table(nodes[:30])
        if len(nodes) > 30:
            print(f"\n  {C.DIM}... and {len(nodes) - 30} more{C.RESET}")

    def _browse_by_type(self):
        print(f"\n  {C.BOLD}Node Types:{C.RESET}")
        types = list(NodeType)
        for i, nt in enumerate(types, 1):
            icon = NODE_ICONS.get(nt.value, " ")
            print(f"    {C.DIM}{i:2}.{C.RESET} {icon} {nt.value}")

        choice = prompt("Type number: ")
        try:
            idx = int(choice) - 1
            selected = types[idx]
        except (ValueError, IndexError):
            print(f"  {C.RED}Invalid selection.{C.RESET}")
            return

        from memora.graph.models import NodeFilter
        self._browse_all_nodes(NodeFilter(node_types=[selected]))

    def _browse_by_network(self):
        print(f"\n  {C.BOLD}Networks:{C.RESET}")
        nets = list(NetworkType)
        for i, nt in enumerate(nets, 1):
            icon = NETWORK_ICONS.get(nt.value, f"[{nt.value[0]}]")
            print(f"    {C.DIM}{i}.{C.RESET} {icon} {nt.value}")

        choice = prompt("Network number: ")
        try:
            idx = int(choice) - 1
            selected = nets[idx]
        except (ValueError, IndexError):
            print(f"  {C.RED}Invalid selection.{C.RESET}")
            return

        from memora.graph.models import NodeFilter
        self._browse_all_nodes(NodeFilter(networks=[selected]))

    def _browse_search(self):
        query = prompt("Search title: ")
        if not query:
            return
        try:
            rows = self.repo._conn.execute(
                "SELECT id, node_type, title, content, networks, confidence, created_at "
                "FROM nodes WHERE deleted = FALSE AND title ILIKE ? LIMIT 20",
                [f"%{query}%"],
            ).fetchall()
        except Exception as e:
            print(f"  {C.RED}Search error: {e}{C.RESET}")
            return

        if not rows:
            print(f"\n  {C.DIM}No nodes matching '{query}'.{C.RESET}")
            return

        print(f"\n  {C.BOLD}{len(rows)} result(s){C.RESET}\n")
        for row in rows:
            nid, ntype, title, content, networks, conf, created = row
            icon = NODE_ICONS.get(ntype, " ")
            nets = " ".join(NETWORK_ICONS.get(n, f"[{n}]") for n in (networks or []))
            short_id = str(nid)[:8]
            print(f"  {C.DIM}{short_id}{C.RESET}  {icon} {C.BOLD}{title}{C.RESET}  {nets}  conf={conf:.0%}")
            if content:
                print(f"           {C.DIM}{content[:60]}{C.RESET}")

    def _browse_node_detail(self):
        nid = prompt("Node ID (first 8 chars ok): ")
        if not nid:
            return

        try:
            rows = self.repo._conn.execute(
                "SELECT id FROM nodes WHERE deleted = FALSE AND CAST(id AS VARCHAR) LIKE ?",
                [f"{nid}%"],
            ).fetchall()
        except Exception as e:
            print(f"  {C.RED}Error: {e}{C.RESET}")
            return

        if not rows:
            print(f"  {C.DIM}Node not found.{C.RESET}")
            return

        full_id = rows[0][0]
        try:
            node = self.repo.get_node(UUID(str(full_id)))
        except Exception as e:
            print(f"  {C.RED}Error: {e}{C.RESET}")
            return

        if not node:
            print(f"  {C.DIM}Node not found.{C.RESET}")
            return

        self._render_node_detail(node)

        # Show edges
        try:
            edges = self.repo.get_edges(node.id)
            if edges:
                print(f"\n  {C.BOLD}Connections ({len(edges)}):{C.RESET}")
                for edge in edges[:15]:
                    direction = "-->" if str(edge.source_id) == str(node.id) else "<--"
                    other_id = edge.target_id if direction == "-->" else edge.source_id
                    short = str(other_id)[:8]
                    # Try to get the other node's title
                    other_title = ""
                    try:
                        other_node = self.repo.get_node(UUID(str(other_id)))
                        if other_node:
                            other_icon = NODE_ICONS.get(other_node.node_type.value, " ")
                            other_title = f" {other_icon} {C.BOLD}{other_node.title[:25]}{C.RESET}"
                    except Exception:
                        pass
                    etype = edge.edge_type.value if hasattr(edge.edge_type, 'value') else str(edge.edge_type)
                    print(f"    {C.CYAN}{direction}{C.RESET} {C.DIM}{short}{C.RESET}{other_title}  "
                          f"{C.DIM}[{etype}]{C.RESET} conf={edge.confidence:.0%}")
                if len(edges) > 15:
                    print(f"    {C.DIM}... and {len(edges) - 15} more{C.RESET}")
                print(f"\n  {C.DIM}Tip: Use option [6] Graph map to visualize this node's neighborhood{C.RESET}")
            else:
                print(f"\n  {C.DIM}No connections yet.{C.RESET}")
        except Exception:
            pass

    def _browse_graph_map(self):
        """Show an ASCII relationship graph centered on a node."""
        nid = prompt("Center node ID (first 8 chars ok): ")
        if not nid:
            return

        try:
            rows = self.repo._conn.execute(
                "SELECT id FROM nodes WHERE deleted = FALSE AND CAST(id AS VARCHAR) LIKE ?",
                [f"{nid}%"],
            ).fetchall()
        except Exception as e:
            print(f"  {C.RED}Error: {e}{C.RESET}")
            return

        if not rows:
            print(f"  {C.DIM}Node not found.{C.RESET}")
            return

        full_id = UUID(str(rows[0][0]))

        hops_str = prompt(f"  Hops (depth) [{C.GREEN}1{C.RESET}-3, default 1]: ")
        hops = 1
        if hops_str.isdigit() and 1 <= int(hops_str) <= 3:
            hops = int(hops_str)

        spinner("Traversing graph neighborhood", 0.5)

        try:
            subgraph = self.repo.get_neighborhood(full_id, hops=hops)
        except Exception as e:
            print(f"  {C.RED}Error: {e}{C.RESET}")
            return

        if not subgraph.nodes:
            print(f"  {C.DIM}No neighborhood found.{C.RESET}")
            return

        self._render_ascii_graph(subgraph, center_id=full_id)

    def _browse_full_map(self):
        """Visualize the entire graph as an ASCII map."""
        from memora.graph.models import NodeFilter, Subgraph
        try:
            nodes = self.repo.query_nodes(NodeFilter())
        except Exception as e:
            print(f"  {C.RED}Error: {e}{C.RESET}")
            return

        if not nodes:
            print(f"\n  {C.DIM}Graph is empty.{C.RESET}")
            print(BRAIN_ART.format(magenta=C.MAGENTA, cyan=C.CYAN, dim=C.DIM, reset=C.RESET))
            return

        if len(nodes) > 60:
            print(f"\n  {C.YELLOW}Graph has {len(nodes)} nodes. Showing first 60.{C.RESET}")
            nodes = nodes[:60]

        # Gather all edges between these nodes
        node_ids = {str(n.id) for n in nodes}
        all_edges = []
        seen_edge_ids = set()
        for node in nodes:
            try:
                edges = self.repo.get_edges(node.id)
                for e in edges:
                    eid = str(e.id) if hasattr(e, 'id') else f"{e.source_id}-{e.target_id}"
                    if eid not in seen_edge_ids:
                        # Only include edges where both endpoints are in our set
                        if str(e.source_id) in node_ids and str(e.target_id) in node_ids:
                            all_edges.append(e)
                            seen_edge_ids.add(eid)
            except Exception:
                pass

        subgraph = Subgraph(nodes=nodes, edges=all_edges)
        self._render_ascii_graph(subgraph, center_id=None)

    def _render_ascii_graph(self, subgraph, center_id: UUID | None = None):
        """Render a subgraph as an ASCII radial/tree relationship map.

        Layout strategy:
        - Center node in the middle
        - Neighbors arranged around it in concentric rings
        - Edges drawn with ASCII connectors
        """
        from memora.graph.models import Subgraph

        nodes = subgraph.nodes
        edges = subgraph.edges

        if not nodes:
            print(f"  {C.DIM}Empty graph.{C.RESET}")
            return

        # Build adjacency
        node_map = {str(n.id): n for n in nodes}
        adj: dict[str, list[tuple[str, str]]] = {str(n.id): [] for n in nodes}
        for e in edges:
            src, tgt = str(e.source_id), str(e.target_id)
            label = e.edge_type.value if hasattr(e.edge_type, 'value') else str(e.edge_type)
            if src in adj:
                adj[src].append((tgt, label))
            if tgt in adj:
                adj[tgt].append((src, label))

        # Determine center
        if center_id and str(center_id) in node_map:
            center_str = str(center_id)
        else:
            # Pick the most connected node
            center_str = max(adj, key=lambda k: len(adj[k])) if adj else str(nodes[0].id)

        center_node = node_map[center_str]

        # BFS to assign layers
        layers: list[list[str]] = []
        visited = {center_str}
        current_layer = [center_str]
        layers.append(current_layer)

        while current_layer:
            next_layer = []
            for nid in current_layer:
                for neighbor_id, _ in adj.get(nid, []):
                    if neighbor_id not in visited and neighbor_id in node_map:
                        visited.add(neighbor_id)
                        next_layer.append(neighbor_id)
            if next_layer:
                layers.append(next_layer)
            current_layer = next_layer

        # Add isolated nodes
        isolated = [str(n.id) for n in nodes if str(n.id) not in visited]
        if isolated:
            layers.append(isolated)

        # Header
        total_e = len(edges)
        total_n = len(nodes)
        print(f"\n{divider('═', C.CYAN)}")
        print(f"  {C.BOLD}{C.CYAN}RELATIONSHIP GRAPH{C.RESET}"
              f"  {C.DIM}({total_n} nodes, {total_e} edges, {len(layers)} layer(s)){C.RESET}")
        print(divider())

        # ── Render the radial ASCII map ──

        w = min(term_width() - 2, 78)

        # Helper: format a node label
        def node_label(nid: str, highlight: bool = False) -> str:
            n = node_map.get(nid)
            if not n:
                return f"{C.DIM}[?]{C.RESET}"
            icon = NODE_ICONS.get(n.node_type.value, " ")
            title = n.title[:18] + (".." if len(n.title) > 18 else "")
            if highlight:
                return f"{C.BG_CYAN}{C.BLACK} {icon} {title} {C.RESET}"
            return f"[{icon} {C.BOLD}{title}{C.RESET}]"

        def edge_label_between(nid_a: str, nid_b: str) -> str:
            for e in edges:
                src, tgt = str(e.source_id), str(e.target_id)
                if (src == nid_a and tgt == nid_b) or (src == nid_b and tgt == nid_a):
                    label = e.edge_type.value if hasattr(e.edge_type, 'value') else str(e.edge_type)
                    return label
            return ""

        # Layer 0: Center node
        center_label = node_label(center_str, highlight=True)
        center_nets = ""
        for net in center_node.networks:
            center_nets += f" {NETWORK_ICONS.get(net.value, '')}"

        print(f"\n{'':>{w // 2 - 15}}{C.DIM}center{C.RESET}")
        print(f"{'':>{w // 2 - 15}}{center_label}{center_nets}")

        # Draw connections from center to layer 1
        if len(layers) > 1 and layers[1]:
            layer1 = layers[1]
            n_nodes = len(layer1)

            # Draw connector lines
            if n_nodes == 1:
                connectors = "       |       "
            elif n_nodes == 2:
                connectors = "      / \\      "
            elif n_nodes == 3:
                connectors = "     /  |  \\     "
            elif n_nodes <= 5:
                connectors = "   /" + "──" * (n_nodes - 2) + "┼" + "──" * (n_nodes - 2) + "\\   "
            else:
                connectors = "  /" + "─┬" * min(n_nodes - 2, 8) + "─\\  "

            print(f"{'':>{w // 2 - len(connectors) // 2}}{C.DIM}{connectors}{C.RESET}")

            # Edge labels row
            edge_labels_row = ""
            for nid in layer1:
                elabel = edge_label_between(center_str, nid)
                short = elabel[:12] if elabel else ""
                edge_labels_row += f" {C.DIM}{short:<13}{C.RESET}"
            # Center the row roughly
            pad = max(0, (w // 2) - (_visible_len(edge_labels_row) // 2) - 4)
            print(f"{'':>{pad}}{edge_labels_row}")

            # Render layer 1 nodes
            node_row = ""
            for nid in layer1:
                node_row += f" {node_label(nid)} "
            pad = max(0, (w // 2) - (_visible_len(node_row) // 2) - 2)
            print(f"{'':>{pad}}{node_row}")

            # Networks for layer 1
            net_row = ""
            for nid in layer1:
                n = node_map.get(nid)
                if n:
                    nets = "".join(NETWORK_ICONS.get(nt.value, "") for nt in n.networks)
                    net_row += f" {nets:<22}"
                else:
                    net_row += " " * 22
            pad = max(0, (w // 2) - (_visible_len(net_row) // 2) - 2)
            print(f"{'':>{pad}}{net_row}")

        # Deeper layers
        for layer_idx in range(2, len(layers)):
            layer = layers[layer_idx]
            if not layer:
                continue

            # Connector
            if layer_idx < len(layers) - 1 or str(layer[0]) not in [str(n.id) for n in nodes if str(n.id) not in visited]:
                print(f"\n{'':>{w // 2 - 8}}{C.DIM}{'·' * 16}  (hop {layer_idx}){C.RESET}")
            else:
                print(f"\n{'':>{w // 2 - 8}}{C.DIM}{'·' * 16}  (isolated){C.RESET}")

            # Render in rows of up to 4
            for chunk_start in range(0, len(layer), 4):
                chunk = layer[chunk_start:chunk_start + 4]

                # Edge labels
                edge_row = ""
                for nid in chunk:
                    # Find which parent this connects to
                    parent = None
                    for prev_layer in layers[:layer_idx]:
                        for prev_nid in prev_layer:
                            for neighbor_id, _ in adj.get(prev_nid, []):
                                if neighbor_id == nid:
                                    parent = prev_nid
                                    break
                            if parent:
                                break
                        if parent:
                            break
                    elabel = edge_label_between(parent, nid) if parent else ""
                    short = elabel[:12] if elabel else ""
                    edge_row += f" {C.DIM}{short:<13}{C.RESET}"

                pad = max(0, (w // 2) - (_visible_len(edge_row) // 2) - 4)
                print(f"{'':>{pad}}{edge_row}")

                # Nodes
                node_row = ""
                for nid in chunk:
                    node_row += f" {node_label(nid)} "
                pad = max(0, (w // 2) - (_visible_len(node_row) // 2) - 2)
                print(f"{'':>{pad}}{node_row}")

        # ── Legend ──
        print(f"\n{divider()}")
        print(f"  {C.BOLD}LEGEND{C.RESET}")

        # Node types present
        types_present = set()
        for n in nodes:
            types_present.add(n.node_type.value)
        type_legend = "  Types:    "
        for t in sorted(types_present):
            icon = NODE_ICONS.get(t, " ")
            type_legend += f" {icon}={t} "
        print(type_legend)

        # Networks present
        nets_present = set()
        for n in nodes:
            for nt in n.networks:
                nets_present.add(nt.value)
        net_legend = "  Networks: "
        for nt in sorted(nets_present):
            icon = NETWORK_ICONS.get(nt, f"[{nt[0]}]")
            net_legend += f" {icon}={nt} "
        print(net_legend)

        # Edge types present
        edge_types_present = set()
        for e in edges:
            label = e.edge_type.value if hasattr(e.edge_type, 'value') else str(e.edge_type)
            edge_types_present.add(label)
        if edge_types_present:
            print(f"  {C.DIM}Edges:   {', '.join(sorted(edge_types_present))}{C.RESET}")

        # Summary
        print(f"\n  {C.DIM}Highlighted node = center   [ ] = graph node{C.RESET}")
        print(f"{divider('═', C.CYAN)}")

    # ── Existing node detail edge view: add graph hint ──

    def _render_node_table(self, nodes):
        """Render a compact table of nodes."""
        for node in nodes:
            icon = NODE_ICONS.get(node.node_type.value, " ")
            nets = " ".join(NETWORK_ICONS.get(n.value, f"[{n.value[0]}]") for n in node.networks)
            short_id = str(node.id)[:8]
            title = node.title[:40] + ("..." if len(node.title) > 40 else "")
            print(f"  {C.DIM}{short_id}{C.RESET}  {icon} {C.BOLD}{title:<44}{C.RESET} {nets}")

    def _render_node_detail(self, node):
        icon = NODE_ICONS.get(node.node_type.value, " ")
        nets = " ".join(NETWORK_ICONS.get(n.value, f"[{n.value[0]}]") for n in node.networks)

        art = f"""
{C.BOLD}    .───────────────────────────────────────.
    |  {icon} {node.title[:35]:<35}  |
    '───────────────────────────────────────'{C.RESET}"""
        print(art)

        print(f"\n  {C.DIM}ID:{C.RESET}         {node.id}")
        print(f"  {C.DIM}Type:{C.RESET}       {node.node_type.value}")
        print(f"  {C.DIM}Networks:{C.RESET}   {nets}")
        print(f"  {C.DIM}Confidence:{C.RESET} {horizontal_bar(node.confidence, 20)}")
        print(f"  {C.DIM}Created:{C.RESET}    {node.created_at}")

        if node.content:
            print(f"\n  {C.BOLD}Content:{C.RESET}")
            for line in textwrap.wrap(node.content, min(term_width() - 6, 68)):
                print(f"    {line}")

        if node.properties:
            print(f"\n  {C.BOLD}Properties:{C.RESET}")
            for k, v in node.properties.items():
                print(f"    {C.DIM}{k}:{C.RESET} {v}")

        if node.tags:
            print(f"\n  {C.DIM}Tags:{C.RESET} {', '.join(node.tags)}")

    # ── 4. Proposals ──────────────────────────────────────────────

    def cmd_proposals(self):
        try:
            proposals = self.repo.get_pending_proposals()
        except Exception:
            proposals = []

        # Also get recent non-pending
        try:
            all_proposals = self.repo.query_proposals(limit=20)
        except Exception:
            all_proposals = []

        pending_count = len(proposals)

        header_art = f"""
{C.YELLOW}     .-------.
    / REVIEW  \\
   |  {C.BOLD}{pending_count} pending{C.RESET}{C.YELLOW} |
    \\_________/{C.RESET}
"""
        print(header_art)

        if not all_proposals:
            print(f"  {C.DIM}No proposals yet. Capture some text first!{C.RESET}")
            return

        for p in all_proposals:
            pid = str(p.get("id", ""))[:8]
            status = p.get("status", "?")
            route = p.get("route", "?")
            conf = p.get("confidence", 0)
            summary = p.get("human_summary", "")[:50]
            created = p.get("created_at", "")

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
                self._approve_proposal(pid)

    def _approve_proposal(self, partial_id: str):
        try:
            rows = self.repo._conn.execute(
                "SELECT id FROM proposals WHERE CAST(id AS VARCHAR) LIKE ? AND status = 'pending'",
                [f"{partial_id}%"],
            ).fetchall()
        except Exception as e:
            print(f"  {C.RED}Error: {e}{C.RESET}")
            return

        if not rows:
            print(f"  {C.DIM}No pending proposal found with ID '{partial_id}'.{C.RESET}")
            return

        full_id = UUID(str(rows[0][0]))
        confirm = prompt(f"  Approve proposal {str(full_id)[:8]}? [{C.GREEN}Y{C.RESET}/n] ")
        if confirm.lower() in ("n", "no"):
            return

        try:
            self.repo.update_proposal_status(full_id, ProposalStatus.APPROVED, reviewer="cli_user")
            success = self.repo.commit_proposal(full_id)
            if success:
                print(f"\n  {C.GREEN}Proposal approved and committed to graph!{C.RESET}")
            else:
                print(f"\n  {C.YELLOW}Proposal approved but commit failed.{C.RESET}")
        except Exception as e:
            print(f"  {C.RED}Error: {e}{C.RESET}")

    # ── 5. Networks ───────────────────────────────────────────────

    def cmd_networks(self):
        stats = self.repo.get_graph_stats()
        nodes_by_net = stats.get("nodes_by_network", {})

        total_nodes = stats.get("total_nodes", 0) or 1

        header = f"""
{C.MAGENTA}{C.BOLD}  THE 7 NETWORKS{C.RESET}
{C.DIM}  Each life domain tracked independently{C.RESET}
"""
        print(header)

        # Network bar chart
        max_count = max(nodes_by_net.values()) if nodes_by_net else 1

        for net_name in ["ACADEMIC", "PROFESSIONAL", "FINANCIAL", "HEALTH",
                         "PERSONAL_GROWTH", "SOCIAL", "VENTURES"]:
            count = nodes_by_net.get(net_name, 0)
            icon = NETWORK_ICONS.get(net_name, f"[{net_name[0]}]")
            ratio = count / max_count if max_count else 0
            bar = horizontal_bar(ratio, 25, {
                "ACADEMIC": C.BLUE, "PROFESSIONAL": C.CYAN,
                "FINANCIAL": C.GREEN, "HEALTH": C.RED,
                "PERSONAL_GROWTH": C.MAGENTA, "SOCIAL": C.YELLOW,
                "VENTURES": C.ORANGE,
            }.get(net_name, C.WHITE))

            print(f"  {icon} {net_name:<17} {bar}  {C.BOLD}{count}{C.RESET} nodes")

        # Health scores
        try:
            health = self.repo.get_latest_health_scores()
            if health:
                print(f"\n{divider()}")
                print(f"  {C.BOLD}Network Health{C.RESET}\n")
                for h in health:
                    net = h.get("network", "?")
                    status = h.get("status", "unknown")
                    momentum = h.get("momentum", "stable")
                    completion = h.get("commitment_completion_rate", 0)

                    icon = NETWORK_ICONS.get(net, f"[{net[0]}]")
                    status_color = {
                        "thriving": C.GREEN, "active": C.CYAN,
                        "stable": C.YELLOW, "falling_behind": C.RED,
                    }.get(status, C.DIM)

                    momentum_arrow = {"rising": f"{C.GREEN}^{C.RESET}",
                                      "stable": f"{C.YELLOW}-{C.RESET}",
                                      "declining": f"{C.RED}v{C.RESET}"}.get(momentum, "?")

                    print(f"  {icon} {net:<17} {status_color}{status:<15}{C.RESET} "
                          f"{momentum_arrow}  completion: {horizontal_bar(completion, 12)}")
        except Exception:
            pass

        # Bridges
        try:
            bridges = self.repo.get_recent_bridges(limit=5)
            if bridges:
                print(f"\n{divider()}")
                print(f"  {C.BOLD}Recent Cross-Network Bridges{C.RESET}\n")
                for b in bridges:
                    src = NETWORK_ICONS.get(b["source_network"], b["source_network"])
                    tgt = NETWORK_ICONS.get(b["target_network"], b["target_network"])
                    sim = b.get("similarity", 0)
                    meaningful = b.get("meaningful")
                    marker = f"{C.GREEN}meaningful{C.RESET}" if meaningful else f"{C.DIM}unvalidated{C.RESET}" if meaningful is None else f"{C.RED}spurious{C.RESET}"
                    print(f"    {src} <==> {tgt}  sim={sim:.2f}  {marker}")
        except Exception:
            pass

        print()

    # ── 6. Stats ──────────────────────────────────────────────────

    def cmd_stats(self):
        stats = self.repo.get_graph_stats()

        total_nodes = stats.get("total_nodes", 0)
        total_edges = stats.get("total_edges", 0)
        nodes_by_type = stats.get("nodes_by_type", {})
        nodes_by_net = stats.get("nodes_by_network", {})

        graph_visual = f"""
{C.CYAN}{C.BOLD}
    GRAPH OVERVIEW
    ══════════════{C.RESET}

         {C.BOLD}{total_nodes}{C.RESET}              {C.BOLD}{total_edges}{C.RESET}
       {C.DIM}nodes{C.RESET}            {C.DIM}edges{C.RESET}

    {C.CYAN}  o───o───o
     /|   |\\
    o─┼─o─┼─o
     \\|   |/
      o───o{C.RESET}
"""
        print(graph_visual)

        # Node type breakdown
        if nodes_by_type:
            print(f"  {C.BOLD}Nodes by Type{C.RESET}\n")
            max_count = max(nodes_by_type.values()) if nodes_by_type else 1
            for ntype, count in sorted(nodes_by_type.items(), key=lambda x: -x[1]):
                icon = NODE_ICONS.get(ntype, " ")
                ratio = count / max_count if max_count else 0
                bar_width = int(ratio * 25)
                print(f"    {icon} {ntype:<17} {C.CYAN}{'█' * bar_width}{C.DIM}{'░' * (25 - bar_width)}{C.RESET} {count}")
            print()

        # Network breakdown
        if nodes_by_net:
            print(f"  {C.BOLD}Nodes by Network{C.RESET}\n")
            max_count = max(nodes_by_net.values()) if nodes_by_net else 1
            for net, count in sorted(nodes_by_net.items(), key=lambda x: -x[1]):
                icon = NETWORK_ICONS.get(net, f"[{net[0]}]")
                ratio = count / max_count if max_count else 0
                bar_width = int(ratio * 25)
                color = {"ACADEMIC": C.BLUE, "PROFESSIONAL": C.CYAN,
                         "FINANCIAL": C.GREEN, "HEALTH": C.RED,
                         "PERSONAL_GROWTH": C.MAGENTA, "SOCIAL": C.YELLOW,
                         "VENTURES": C.ORANGE}.get(net, C.WHITE)
                print(f"    {icon} {net:<17} {color}{'█' * bar_width}{C.DIM}{'░' * (25 - bar_width)}{C.RESET} {count}")

        # Edge density
        if total_nodes > 0:
            density = total_edges / total_nodes
            print(f"\n  {C.BOLD}Edge Density:{C.RESET} {density:.2f} edges/node")

        # Commitments summary
        try:
            commits = self.repo.get_open_commitments_raw(limit=100)
            if commits:
                print(f"\n  {C.BOLD}Open Commitments:{C.RESET} {len(commits)}")
        except Exception:
            pass

        print()

    # ── 7. Briefing ───────────────────────────────────────────────

    def cmd_briefing(self):
        briefing_art = f"""
{C.CYAN}    .─────────────────────────.
    |   {C.BOLD}DAILY BRIEFING{C.RESET}{C.CYAN}          |
    |   {C.DIM}{datetime.utcnow().strftime('%A, %B %d, %Y')}{C.RESET}{C.CYAN}  |
    '─────────────────────────'{C.RESET}
"""
        print(briefing_art)

        strat = self._get_strategist()
        if not strat:
            print(f"  {C.YELLOW}Strategist unavailable (no API key).{C.RESET}")
            print(f"  {C.DIM}Showing raw stats instead...{C.RESET}\n")
            self.cmd_stats()
            return

        spinner("Gathering network data", 0.8)

        health = self.repo.get_latest_health_scores()
        bridges = self.repo.get_recent_bridges(limit=10)
        try:
            from memora.core.commitment_scan import CommitmentScanner
            commitments = CommitmentScanner(self.repo).scan()
        except Exception:
            commitments = {}
        try:
            from memora.core.spaced_repetition import SpacedRepetition
            review_items = SpacedRepetition(self.repo).get_review_queue()
        except Exception:
            review_items = []

        alerts = list(commitments.get("overdue", []))

        spinner("Strategist composing briefing", 1.5)

        try:
            briefing = asyncio.run(strat.generate_briefing(
                health_scores=health,
                alerts=alerts,
                bridges=bridges,
                commitments=commitments,
                review_items=review_items,
            ))
        except Exception as e:
            print(f"\n  {C.RED}Briefing failed: {e}{C.RESET}")
            return

        # Render sections
        if briefing.sections:
            for section in briefing.sections:
                priority_color = {"high": C.RED, "medium": C.YELLOW, "low": C.DIM}.get(section.priority, C.WHITE)
                print(f"\n  {priority_color}[{section.priority.upper()}]{C.RESET} {C.BOLD}{section.title}{C.RESET}")
                for item in section.items:
                    print(f"    - {item}")

        if briefing.summary:
            print(f"\n{divider()}")
            print(f"  {C.BOLD}Summary:{C.RESET}\n")
            for line in textwrap.wrap(briefing.summary, min(term_width() - 6, 68)):
                print(f"    {line}")

        print()

    # ── 8. Critique ───────────────────────────────────────────────

    def cmd_critique(self):
        critique_art = f"""
{C.RED}     .---.
    / ??? \\
   |  !!!  |     {C.BOLD}CRITIC MODE{C.RESET}{C.RED}
    \\_____/
     |   |       {C.DIM}Challenge assumptions.{C.RESET}{C.RED}
     '---'{C.RESET}
"""
        print(critique_art)

        statement = prompt(f"  {C.RED}Statement to challenge: {C.RESET}")
        if not statement or statement == "q":
            return

        strat = self._get_strategist()
        if not strat:
            print(f"\n  {C.RED}Strategist unavailable (no API key).{C.RESET}")
            return

        spinner("Gathering counter-evidence", 0.8)
        spinner("Identifying blind spots", 0.8)

        try:
            result = asyncio.run(strat.critique(statement))
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

        if result.recommendations:
            print(f"\n  {C.BOLD}Recommendations:{C.RESET}")
            for rec in result.recommendations:
                action = rec.get("action", str(rec))
                print(f"    {C.YELLOW}>{C.RESET} {action}")

        if result.citations:
            print(f"\n  {C.DIM}Evidence: {', '.join(result.citations[:5])}{C.RESET}")

        print(f"\n{divider('═', C.RED)}")

    # ── Goodbye ───────────────────────────────────────────────────

    def goodbye(self):
        art = f"""
{C.CYAN}
    ╔═══════════════════════════════╗
    ║                               ║
    ║   {C.BOLD}Thanks for using Memora!{C.RESET}{C.CYAN}    ║
    ║                               ║
    ║   {C.DIM}Your knowledge persists.{C.RESET}{C.CYAN}    ║
    ║   {C.DIM}See you next time.{C.RESET}{C.CYAN}          ║
    ║                               ║
    ╚═══════════════════════════════╝
{C.RESET}"""
        print(art)

        if self.repo:
            self.repo.close()


# ══════════════════════════════════════════════════════════════════════
# Entry Point
# ══════════════════════════════════════════════════════════════════════

def main():
    try:
        app = MemoraApp()
        app.run()
    except KeyboardInterrupt:
        print(f"\n\n{C.DIM}  Interrupted. Goodbye!{C.RESET}\n")


if __name__ == "__main__":
    main()
