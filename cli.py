#!/usr/bin/env python3
"""Memora CLI — Interactive terminal interface for your knowledge graph.

A rich ASCII-based CLI that lets you capture thoughts, query the AI council,
browse your knowledge graph, review proposals, and monitor network health.
"""

from __future__ import annotations

import os
import sys
import json
import select
import shutil
import textwrap
import time
import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

# ── Ensure the backend package is importable ──────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

# Suppress noisy logs unless user wants them
os.environ.setdefault("MEMORA_LOG_LEVEL", "WARNING")

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from memora.config import load_settings, Settings
from memora.graph.repository import GraphRepository, YOU_NODE_ID
from memora.graph.models import NodeType, NetworkType, ProposalRoute, ProposalStatus
from memora.core.pipeline import PipelineStage, STAGE_NAMES

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
# Live Pipeline Tracker
# ══════════════════════════════════════════════════════════════════════

# All stages in order for display
_PIPELINE_STAGES = [
    PipelineStage.PREPROCESSING,
    PipelineStage.EXTRACTION,
    PipelineStage.ENTITY_RESOLUTION,
    PipelineStage.PROPOSAL_ASSEMBLY,
    PipelineStage.VALIDATION_GATE,
    PipelineStage.REVIEW,
    PipelineStage.GRAPH_COMMIT,
    PipelineStage.POST_COMMIT,
]

_STAGE_ICONS = {
    "pending":  f"{C.DIM}   {C.RESET}",
    "running":  f"{C.YELLOW} > {C.RESET}",
    "done":     f"{C.GREEN} + {C.RESET}",
    "failed":   f"{C.RED} x {C.RESET}",
    "skipped":  f"{C.DIM} - {C.RESET}",
}


class PipelineTracker:
    """Renders a live ASCII pipeline progress display in the terminal."""

    def __init__(self) -> None:
        self._stage_status: dict[PipelineStage, str] = {
            s: "pending" for s in _PIPELINE_STAGES
        }
        self._printed = False

    def _render(self) -> str:
        """Build the full ASCII tracker string."""
        w = min(term_width() - 4, 72)
        lines = []
        lines.append(f"  {C.CYAN}{'─' * w}{C.RESET}")
        lines.append(f"  {C.BOLD}{C.CYAN} PIPELINE{C.RESET}")
        lines.append(f"  {C.CYAN}{'─' * w}{C.RESET}")

        for stage in _PIPELINE_STAGES:
            status = self._stage_status[stage]
            icon = _STAGE_ICONS.get(status, "   ")
            name = STAGE_NAMES.get(stage, stage.name)
            if status == "running":
                label = f"{C.YELLOW}{C.BOLD}{name}{C.RESET}"
            elif status == "done":
                label = f"{C.GREEN}{name}{C.RESET}"
            elif status == "failed":
                label = f"{C.RED}{name}{C.RESET}"
            else:
                label = f"{C.DIM}{name}{C.RESET}"
            lines.append(f"  {icon} {label}")

        lines.append(f"  {C.CYAN}{'─' * w}{C.RESET}")
        return "\n".join(lines)

    def _line_count(self) -> int:
        """How many terminal lines the tracker occupies."""
        return len(_PIPELINE_STAGES) + 3  # stages + 3 border/header lines

    def on_stage(self, stage: PipelineStage, status: str) -> None:
        """Callback for pipeline stage transitions. Redraws the tracker."""
        self._stage_status[stage] = status

        if self._printed:
            # Move cursor up to overwrite the previous render
            n = self._line_count()
            sys.stdout.write(f"\033[{n}A")

        sys.stdout.write(self._render() + "\n")
        sys.stdout.flush()
        self._printed = True


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

    def _get_embedding_engine(self):
        """Lazily initialize the embedding engine."""
        if not hasattr(self, '_embedding_engine') or self._embedding_engine is None:
            try:
                import logging as _logging
                from memora.vector.embeddings import EmbeddingEngine

                # Suppress noisy model-loading logs
                _noisy = ["sentence_transformers", "httpx", "huggingface_hub",
                           "transformers", "torch", "tqdm"]
                _prev = {n: _logging.getLogger(n).level for n in _noisy}
                for n in _noisy:
                    _logging.getLogger(n).setLevel(_logging.ERROR)

                import os as _os
                _prev_tqdm = _os.environ.get("TQDM_DISABLE")
                _os.environ["TQDM_DISABLE"] = "1"

                try:
                    self._embedding_engine = EmbeddingEngine(
                        model_name=self.settings.embedding_model,
                        cache_dir=self.settings.models_dir,
                    )
                finally:
                    for n, lvl in _prev.items():
                        _logging.getLogger(n).setLevel(lvl)
                    if _prev_tqdm is None:
                        _os.environ.pop("TQDM_DISABLE", None)
                    else:
                        _os.environ["TQDM_DISABLE"] = _prev_tqdm
            except Exception as e:
                print(f"  {C.DIM}(embedding engine unavailable: {e}){C.RESET}")
                self._embedding_engine = None
        return self._embedding_engine

    def _get_vector_store(self):
        """Lazily initialize the vector store."""
        if not hasattr(self, '_vector_store') or self._vector_store is None:
            try:
                from memora.vector.store import VectorStore
                self._vector_store = VectorStore(db_path=self.settings.vector_dir)
            except Exception as e:
                print(f"  {C.DIM}(vector store unavailable: {e}){C.RESET}")
                self._vector_store = None
        return self._vector_store

    def _get_pipeline(self):
        if self._pipeline:
            return self._pipeline
        if not self._has_api_key:
            return None
        try:
            from memora.core.pipeline import ExtractionPipeline

            spinner("Loading embedding model", 0.3)
            vector_store = self._get_vector_store()
            embedding_engine = self._get_embedding_engine()

            self._pipeline = ExtractionPipeline(
                repo=self.repo,
                settings=self.settings,
                vector_store=vector_store,
                embedding_engine=embedding_engine,
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
            elif choice == "0":
                self.cmd_profile()
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
            elif choice == "9":
                self.cmd_dossier()
            elif choice in ("c", "clear"):
                self.cmd_clear_data()
            else:
                print(f"  {C.DIM}Unknown command. Try 0-9, 'c', or 'q' to quit.{C.RESET}")

    def show_main_menu(self):
        print(f"\n{divider('═', C.CYAN)}")
        print(f"  {C.BOLD}{C.CYAN}MAIN MENU{C.RESET}")
        print(divider())
        print(menu_option("0", "Profile",    "Tell Memora about yourself"))
        print(menu_option("1", "Capture",    "Record a thought, event, or decision"))
        print(menu_option("2", "Council",    "Ask the AI council a question"))
        print(menu_option("3", "Browse",     "Explore your knowledge graph"))
        print(menu_option("4", "Proposals",  "Review pending graph proposals"))
        print(menu_option("5", "Networks",   "View network health & stats"))
        print(menu_option("6", "Stats",      "Full graph statistics & charts"))
        print(menu_option("7", "Briefing",   "Generate your daily briefing"))
        print(menu_option("8", "Critique",   "Challenge a statement or decision"))
        print(menu_option("9", "Dossier",    "Deep search — everything about an entity"))
        print()
        print(menu_option("c", "Clear data", "Erase all databases and start fresh"))
        print(divider())
        print(f"  {C.DIM}[q] Quit{C.RESET}")

    def show_quick_stats(self):
        """Show a compact stats bar on startup."""
        if not self.repo:
            return
        try:
            stats = self.repo.get_graph_stats()
            nodes = stats.get("node_count", 0)
            edges = stats.get("edge_count", 0)
            nets = len(stats.get("network_breakdown", {}))

            api_status = f"{C.GREEN}connected{C.RESET}" if self._has_api_key else f"{C.RED}no key{C.RESET}"

            # Show You node profile hint
            you_node = self.repo.get_node(UUID(YOU_NODE_ID))
            you_label = ""
            if you_node and you_node.properties:
                name = you_node.properties.get("name", "")
                role = you_node.properties.get("role", "")
                if name and name != "You":
                    you_label = f"  {C.YELLOW}\u2605{C.RESET} {name}"
                    if role:
                        you_label += f" ({role})"
                    you_label += f"  {C.DIM}|{C.RESET}"

            status = (f"{you_label}  {C.BOLD}{nodes}{C.RESET} nodes  {C.DIM}|{C.RESET}  "
                      f"{C.BOLD}{edges}{C.RESET} edges  {C.DIM}|{C.RESET}  "
                      f"{C.BOLD}{nets}{C.RESET} networks  {C.DIM}|{C.RESET}  "
                      f"API: {api_status}")

            print(box("GRAPH STATUS", status, C.DIM))
        except Exception:
            pass

    # ── 0. Profile ─────────────────────────────────────────────────

    def cmd_profile(self):
        """View and update the central You node."""
        from uuid import UUID as _UUID

        you_id = _UUID(YOU_NODE_ID)
        you_node = self.repo.get_node(you_id)

        if not you_node:
            print(f"  {C.RED}You node not found.{C.RESET}")
            return

        # Show current profile
        profile_art = f"""
{C.CYAN}{C.BOLD}
         .---.
        / YOU \\
       |  {C.YELLOW}★{C.RESET}{C.CYAN}{C.BOLD}   |    YOUR PROFILE
        \\_____/
{C.RESET}"""
        print(profile_art)

        props = you_node.properties or {}
        content = you_node.content or ""

        # Show identity fields
        if props.get("name") and props["name"] != "You":
            print(f"  {C.BOLD}Name:{C.RESET}      {props['name']}")
        if props.get("role"):
            print(f"  {C.BOLD}Role:{C.RESET}      {props['role']}")
        if props.get("location"):
            print(f"  {C.BOLD}Location:{C.RESET}  {props['location']}")
        if props.get("organization"):
            print(f"  {C.BOLD}Org:{C.RESET}       {props['organization']}")
        if props.get("interests"):
            interests = props["interests"]
            if isinstance(interests, list):
                interests = ", ".join(interests)
            print(f"  {C.BOLD}Interests:{C.RESET} {interests}")
        if props.get("skills"):
            skills = props["skills"]
            if isinstance(skills, list):
                skills = ", ".join(skills)
            print(f"  {C.BOLD}Skills:{C.RESET}    {skills}")
        if props.get("bio"):
            print(f"  {C.BOLD}Bio:{C.RESET}       {props['bio']}")

        # Show other custom properties
        shown = {"name", "role", "location", "organization", "interests",
                 "skills", "bio", "relationship_to_user"}
        extras = {k: v for k, v in props.items() if k not in shown}
        if extras:
            for k, v in extras.items():
                print(f"  {C.DIM}{k}:{C.RESET}  {v}")

        # Show content (accumulated self-descriptions)
        if content and content != "Central node representing the user":
            print(f"\n  {C.BOLD}About you:{C.RESET}")
            for line in textwrap.wrap(content, min(term_width() - 6, 68)):
                print(f"    {C.DIM}{line}{C.RESET}")

        # Show connections count
        try:
            edges = self.repo.get_edges(you_id)
            print(f"\n  {C.BOLD}Connections:{C.RESET} {len(edges)} nodes in your galaxy")
        except Exception:
            pass

        # Menu: update profile or view galaxy
        print(f"\n{divider()}")
        print(menu_option("1", "Update profile",  "Tell Memora about yourself"))
        print(menu_option("2", "View galaxy",     "See your galaxy graph"))
        print(menu_option("b", "Back",            "Return to main menu"))

        choice = prompt("profile> ")
        if choice == "1":
            self._profile_update()
        elif choice == "2":
            self._browse_galaxy()

    def _profile_update(self):
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

        pipeline = self._get_pipeline()
        if pipeline:
            # Run through pipeline — the archivist will detect self-description
            # and add nodes_to_update for the You node
            from memora.graph.models import Capture
            import hashlib
            content_hash = hashlib.sha256(text.encode()).hexdigest()
            capture = Capture(modality="text", raw_content=text, content_hash=content_hash)
            cid = self.repo.create_capture(capture)

            tracker = PipelineTracker()
            print()
            try:
                state = asyncio.run(pipeline.run(str(cid), text, on_stage=tracker.on_stage))
                self._render_pipeline_result(state, text)
                if state.proposal_id and state.status == "awaiting_review":
                    action = prompt(f"\n  Approve this proposal? [{C.GREEN}Y{C.RESET}/n/skip] ")
                    if action.lower() not in ("n", "no", "skip"):
                        self._approve_proposal(state.proposal_id[:8])
            except Exception as e:
                print(f"\n  {C.RED}Pipeline error: {e}{C.RESET}")
                # Fall back to direct update
                self._profile_direct_update(text)
        else:
            # No API key — update You node directly
            self._profile_direct_update(text)

    def _profile_direct_update(self, text: str):
        """Directly update the You node content without AI processing."""
        import json as _json
        from uuid import UUID as _UUID

        you_id = _UUID(YOU_NODE_ID)
        you_node = self.repo.get_node(you_id)
        if not you_node:
            return

        # Append to content
        current = you_node.content or ""
        if current == "Central node representing the user":
            new_content = text
        else:
            new_content = f"{current}\n{text}"

        self.repo.update_node(you_id, {"content": new_content})

        print(f"\n  {C.GREEN}Profile updated!{C.RESET}")
        print(f"  {C.DIM}Added: {text[:60]}{'...' if len(text) > 60 else ''}{C.RESET}")

    # ── 1. Capture ────────────────────────────────────────────────

    # Recommended max characters for a single capture.  Longer text still
    # works but may degrade extraction quality in the archivist LLM call.
    CAPTURE_CHAR_LIMIT = 2000

    # ── Raw-mode capture input with live character counter ─────────

    def _show_capture_counter(self, chars: int, limit: int):
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
        # Save cursor ➜ jump to column ➜ print ➜ restore cursor
        sys.stdout.write(f"\033[s\033[{col}G{color}{label}{C.RESET}\033[u")
        sys.stdout.flush()

    def _read_capture_line(
        self, prompt_str: str, char_total: int, limit: int,
    ) -> str | None:
        """Read one line char-by-char so the counter updates per keystroke.

        Returns the line text, or *None* on Ctrl-C / Ctrl-D.
        """
        try:
            import tty, termios
        except ImportError:
            # Fallback (e.g. Windows) — use plain input(), no live counter
            try:
                return input(f"\n{prompt_str}").strip()
            except (EOFError, KeyboardInterrupt):
                return None

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        buf: list[str] = []

        sys.stdout.write(f"\n{prompt_str}")
        sys.stdout.flush()
        self._show_capture_counter(char_total, limit)

        try:
            tty.setcbreak(fd)
            while True:
                ch = sys.stdin.read(1)

                if ch in ("\r", "\n"):
                    sys.stdout.write("\n")
                    break
                elif ch in ("\x7f", "\x08"):          # Backspace
                    if buf:
                        buf.pop()
                        sys.stdout.write("\b \b")
                elif ch == "\x03":                     # Ctrl-C
                    sys.stdout.write("\n")
                    return None
                elif ch == "\x04":                     # Ctrl-D
                    sys.stdout.write("\n")
                    return None
                elif ch == "\x1b":                     # ESC sequence (arrows)
                    # Consume remaining bytes of the sequence
                    if select.select([sys.stdin], [], [], 0.05)[0]:
                        sys.stdin.read(1)
                        if select.select([sys.stdin], [], [], 0.05)[0]:
                            sys.stdin.read(1)
                    continue
                elif ch == "\t":                       # Tab → 4 spaces
                    for _ in range(4):
                        buf.append(" ")
                        sys.stdout.write(" ")
                elif ch >= " ":                        # Printable
                    buf.append(ch)
                    sys.stdout.write(ch)

                self._show_capture_counter(
                    char_total + len(buf), limit,
                )
                sys.stdout.flush()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

        return "".join(buf)

    def cmd_capture(self):
        limit = self.CAPTURE_CHAR_LIMIT
        print(f"\n{box('CAPTURE', 'Record a new thought, event, meeting note, decision, or anything.', C.YELLOW)}")
        print(f"\n  {C.DIM}Type your text below. Press Enter twice to submit, or 'cancel' to abort.{C.RESET}")
        print(f"  {C.DIM}Recommended limit: {limit:,} characters{C.RESET}")
        print(f"  {C.DIM}{'─' * 60}{C.RESET}")

        lines: list[str] = []
        while True:
            # Current accumulated length (including newlines between lines)
            running = "\n".join(lines)
            char_total = len(running.strip())
            if lines:
                char_total += 1          # the newline before this new line

            line = self._read_capture_line(
                f"  {C.YELLOW}| {C.RESET}", char_total, limit,
            )

            if line is None:                           # Ctrl-C / Ctrl-D
                print(f"  {C.DIM}Cancelled.{C.RESET}")
                return
            if line.strip().lower() == "cancel":
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
        char_count = len(text)
        print(f"\n{divider()}")
        if char_count > limit:
            print(f"  {C.YELLOW}Warning:{C.RESET} {char_count:,} chars exceeds the recommended {limit:,} limit.")
            print(f"  {C.DIM}The capture will still be saved, but extraction quality may be reduced.{C.RESET}")
        print(f"  {C.BOLD}Preview{C.RESET} {C.DIM}({char_count:,} chars):{C.RESET}")
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

        tracker = PipelineTracker()
        print()  # blank line before tracker

        try:
            state = asyncio.run(pipeline.run(str(cid), text, on_stage=tracker.on_stage))
            self._render_pipeline_result(state, text)

            # If proposal awaiting review, prompt to approve immediately
            if state.proposal_id and state.status == "awaiting_review" and not state.clarification_needed:
                action = prompt(f"\n  Approve this proposal? [{C.GREEN}Y{C.RESET}/n/skip] ")
                if action.lower() not in ("n", "no", "skip"):
                    self._approve_proposal(state.proposal_id[:8])

            # If clarification needed, let user provide more context and re-run
            if state.clarification_needed:
                clarify = prompt(f"\n  {C.YELLOW}Provide clarification{C.RESET} (or 'skip'): ")
                if clarify and clarify.lower() != "skip":
                    enriched = f"{text}\n\n[Clarification]: {clarify}"
                    tracker2 = PipelineTracker()
                    print()
                    state2 = asyncio.run(pipeline.run(str(cid), enriched, on_stage=tracker2.on_stage))
                    self._render_pipeline_result(state2, enriched)
                    if state2.proposal_id and state2.status == "awaiting_review":
                        action = prompt(f"\n  Approve this proposal? [{C.GREEN}Y{C.RESET}/n/skip] ")
                        if action.lower() not in ("n", "no", "skip"):
                            self._approve_proposal(state2.proposal_id[:8])
        except Exception as e:
            print(f"\n  {C.RED}Pipeline error:{C.RESET} {e}")
            self._render_capture_stored(str(cid), text, ai=False)

    def _render_capture_animation(self):
        """Legacy static animation — replaced by live pipeline tracker."""
        pass

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
{C.DIM}       ┌────────────┐ ┌─────────────┐ ┌─────────────┐{C.RESET}
       {C.DIM}│{C.RESET} {C.YELLOW}☽ ARCHIVIST{C.RESET}{C.DIM}│ │{C.RESET} {C.CYAN}⚖ STRATEGIST{C.RESET}{C.DIM} │ │{C.RESET} {C.MAGENTA}☀ RESEARCHER{C.RESET}{C.DIM} │{C.RESET}
{C.DIM}       └─────┬──────┘ └──────┬──────┘ └──────┬──────┘
             │               │               │
             ▼               ▼               ▼
       ══════╪═══════════════╪═══════════════╪══════
             ║     ┏━━━━━━━━━━━━━━━━┓        ║
             ╚═════┫{C.RESET}  {C.BOLD}{C.CYAN}  COUNCIL     {C.RESET}{C.DIM}┣════════╝
                   ┗━━━━━━━━━━━━━━━━┛{C.RESET}
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
                    # Detect raw JSON and format it as a summary instead
                    stripped = content_text.strip()
                    if stripped.startswith("{") or stripped.startswith("["):
                        try:
                            parsed = json.loads(stripped)
                            # Extract human_summary if present in JSON
                            if isinstance(parsed, dict) and parsed.get("human_summary"):
                                content_text = parsed["human_summary"]
                            else:
                                content_text = f"{C.DIM}(structured data returned){C.RESET}"
                        except json.JSONDecodeError:
                            pass  # Not valid JSON, display as-is
                    for line in textwrap.wrap(content_text, min(term_width() - 6, 72)):
                        print(f"    {line}")

                citations = out.get("citations", [])
                if citations:
                    print(f"    {C.DIM}Citations: {', '.join(citations[:5])}{C.RESET}")

        # Synthesis
        print(f"\n{divider()}")
        print(f"  {C.BOLD}{C.GREEN}SYNTHESIS{C.RESET}\n")
        # Preserve paragraph breaks in synthesis
        for paragraph in result.synthesis.split("\n\n"):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            for line in textwrap.wrap(paragraph, min(term_width() - 6, 72)):
                print(f"    {line}")
            print()  # blank line between paragraphs

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
            print(menu_option("8", "Galaxy",        "Your universe centered on You"))
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
            elif choice == "8":
                self._browse_galaxy()

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
        # Center on the You node if present
        you_center = UUID(YOU_NODE_ID) if YOU_NODE_ID in node_ids else None
        self._render_ascii_graph(subgraph, center_id=you_center)

    def _browse_galaxy(self):
        """Galaxy view — centered on the You node with configurable depth."""
        from uuid import UUID as _UUID

        you_id = _UUID(YOU_NODE_ID)

        hops_str = prompt(f"  Depth [{C.GREEN}1{C.RESET}-3, default 2]: ")
        hops = 2
        if hops_str.isdigit() and 1 <= int(hops_str) <= 3:
            hops = int(hops_str)

        spinner("Mapping your galaxy", 0.5)

        try:
            subgraph = self.repo.get_neighborhood(you_id, hops=hops)
        except Exception as e:
            print(f"  {C.RED}Error: {e}{C.RESET}")
            return

        if not subgraph.nodes:
            print(f"\n  {C.DIM}Your galaxy is empty. Start by capturing some thoughts!{C.RESET}")
            return

        self._render_ascii_graph(subgraph, center_id=you_id)

    def _render_ascii_graph(self, subgraph, center_id: UUID | None = None):
        """Render a subgraph as a 2D mind-map / flowchart with boxed nodes
        and routed connectors.

        Layout strategy:
        - Find connected components
        - BFS tree per component, slot-based vertical positioning
        - Render on a character grid: boxed nodes in columns, connectors
          with junction routing and edge labels between them
        - Cross-edges listed below the diagram
        """
        from collections import defaultdict, deque

        nodes = subgraph.nodes
        edges = subgraph.edges

        if not nodes:
            print(f"  {C.DIM}Empty graph.{C.RESET}")
            return

        w = term_width()

        # ── 1. Build data structures ──────────────────────────────
        node_map = {str(n.id): n for n in nodes}
        adj: dict[str, list[tuple[str, str, bool]]] = defaultdict(list)
        edge_index: dict[frozenset, tuple] = {}

        for e in edges:
            src, tgt = str(e.source_id), str(e.target_id)
            label = (e.edge_type.value if hasattr(e.edge_type, 'value')
                     else str(e.edge_type))
            bidi = getattr(e, 'bidirectional', False)
            if src in node_map and tgt in node_map:
                adj[src].append((tgt, label, bidi))
                adj[tgt].append((src, label, bidi))
                edge_index[frozenset({src, tgt})] = (label, src, tgt, bidi)

        center_str = (str(center_id)
                      if center_id and str(center_id) in node_map else None)

        # ── 2. Find connected components ──────────────────────────
        unvisited = set(node_map.keys())
        components: list[list[str]] = []
        while unvisited:
            seed = next(iter(unvisited))
            comp: list[str] = []
            q = deque([seed])
            while q:
                nid = q.popleft()
                if nid not in unvisited:
                    continue
                unvisited.discard(nid)
                comp.append(nid)
                for nb, _, _ in adj.get(nid, []):
                    if nb in unvisited:
                        q.append(nb)
            components.append(comp)
        components.sort(key=len, reverse=True)

        multi = [c for c in components if len(c) > 1]
        isolated = [c[0] for c in components if len(c) == 1]

        if center_str:
            for i, c in enumerate(multi):
                if center_str in c:
                    multi.insert(0, multi.pop(i))
                    break

        n_comps = len(multi) + (1 if isolated else 0)

        # ── 3. Header ────────────────────────────────────────────
        is_galaxy = center_str and center_str == YOU_NODE_ID
        hdr_color = C.YELLOW if is_galaxy else C.CYAN
        print(f"\n{divider('\u2550', hdr_color)}")
        if is_galaxy:
            mode = "galaxy"
            title = "YOUR GALAXY"
        elif center_id:
            mode = "neighborhood"
            title = "RELATIONSHIP GRAPH"
        else:
            mode = "full graph"
            title = "RELATIONSHIP GRAPH"
        print(f"  {C.BOLD}{hdr_color}{title}{C.RESET}  "
              f"{C.DIM}({len(nodes)} nodes, {len(edges)} edges, "
              f"{n_comps} component"
              f"{'s' if n_comps != 1 else ''}, {mode}){C.RESET}")
        print(divider())

        # ── 4. Character grid ─────────────────────────────────────
        class Grid:
            """2D character buffer with per-cell foreground color + bold."""
            def __init__(self, gw, gh):
                self.gw, self.gh = gw, gh
                self.ch = [[' '] * gw for _ in range(gh)]
                self.fg = [[None] * gw for _ in range(gh)]
                self.bd = [[False] * gw for _ in range(gh)]

            def put(self, x, y, c, fg=None, bold=False):
                if 0 <= x < self.gw and 0 <= y < self.gh:
                    self.ch[y][x] = c
                    self.fg[y][x] = fg
                    self.bd[y][x] = bold

            def puts(self, x, y, text, fg=None, bold=False):
                for i, c in enumerate(text):
                    self.put(x + i, y, c, fg, bold)

            def render(self):
                out: list[str] = []
                for y in range(self.gh):
                    last = -1
                    for x in range(self.gw - 1, -1, -1):
                        if self.ch[y][x] != ' ':
                            last = x
                            break
                    if last < 0:
                        out.append('')
                        continue
                    line = ''
                    cf, cb = None, False
                    for x in range(last + 1):
                        c = self.ch[y][x]
                        f, b = self.fg[y][x], self.bd[y][x]
                        if f != cf or b != cb:
                            if cf or cb:
                                line += C.RESET
                            if b:
                                line += C.BOLD
                            if f:
                                line += f
                            cf, cb = f, b
                        line += c
                    if cf or cb:
                        line += C.RESET
                    out.append(line)
                while out and not out[-1]:
                    out.pop()
                return out

        # ── 5. Icon / color maps (plain chars, no ANSI) ───────────
        ICHARS = {
            "EVENT": "*", "PERSON": "@", "COMMITMENT": "!",
            "DECISION": "?", "GOAL": ">", "FINANCIAL_ITEM": "$",
            "NOTE": "#", "IDEA": "~", "PROJECT": "P",
            "CONCEPT": "C", "REFERENCE": "R", "INSIGHT": "!",
        }
        ICOLORS = {
            "EVENT": C.YELLOW, "PERSON": C.CYAN, "COMMITMENT": C.RED,
            "DECISION": C.GREEN, "GOAL": C.MAGENTA,
            "FINANCIAL_ITEM": C.GREEN, "NOTE": C.LGRAY, "IDEA": C.PINK,
            "PROJECT": C.BLUE, "CONCEPT": C.TEAL, "REFERENCE": C.DIM,
            "INSIGHT": C.ORANGE,
        }
        NCHARS = {
            "ACADEMIC": "A", "PROFESSIONAL": "P", "FINANCIAL": "$",
            "HEALTH": "H", "PERSONAL_GROWTH": "G", "SOCIAL": "S",
            "VENTURES": "V",
        }
        NCOLORS = {
            "ACADEMIC": C.BLUE, "PROFESSIONAL": C.CYAN,
            "FINANCIAL": C.GREEN, "HEALTH": C.RED,
            "PERSONAL_GROWTH": C.MAGENTA, "SOCIAL": C.YELLOW,
            "VENTURES": C.ORANGE,
        }

        # ── 6. Junction character lookup ──────────────────────────
        _JUNC = {
            0b0011: '\u250c', 0b0111: '\u251c', 0b0110: '\u2514',
            0b1011: '\u252c', 0b1111: '\u253c', 0b1110: '\u2534',
            0b1001: '\u2510', 0b1101: '\u2524', 0b1100: '\u2518',
            0b1010: '\u2500', 0b0101: '\u2502',
            0b1000: '\u2500', 0b0010: '\u2500',
            0b0100: '\u2502', 0b0001: '\u2502',
        }

        def junc(left, up, right, down):
            return _JUNC.get(
                (left << 3) | (up << 2) | (right << 1) | down, ' ')

        # ── 7. Constants ─────────────────────────────────────────
        BOX_H = 3       # top border, content, bottom border
        GAP_Y = 1       # vertical gap between adjacent boxes
        SLOT_H = BOX_H + GAP_Y   # = 4 rows per slot
        CONN_W = 14     # horizontal gap between columns (connectors)
        LABEL_MAX = 8   # max edge-label chars on a connector

        # Cross-edge (non-tree edge) rendering
        CROSS_CHAR_H = '╌'   # dotted horizontal
        CROSS_CHAR_V = '╎'   # dotted vertical
        CROSS_COLOR = C.MAGENTA
        CROSS_MAX_ROUTES = 8  # max cross-edges to draw visually

        # ── 8. Draw a node box on the grid ────────────────────────
        def draw_box(g, x, y, bw, nid,
                     highlight=False, right_conn=False, left_conn=False):
            n = node_map[nid]
            is_you = (nid == YOU_NODE_ID)
            bc = C.YELLOW if is_you else (C.CYAN if highlight else C.DIM)

            # -- borders (double-line for You node) --
            if is_you:
                g.put(x, y, '\u2554', bc)
                for i in range(1, bw - 1):
                    g.put(x + i, y, '\u2550', bc)
                g.put(x + bw - 1, y, '\u2557', bc)

                lc = '\u2562' if left_conn else '\u2551'
                rc = '\u255f' if right_conn else '\u2551'
                g.put(x, y + 1, lc, bc)
                g.put(x + bw - 1, y + 1, rc, bc)

                g.put(x, y + 2, '\u255a', bc)
                for i in range(1, bw - 1):
                    g.put(x + i, y + 2, '\u2550', bc)
                g.put(x + bw - 1, y + 2, '\u255d', bc)
            else:
                g.put(x, y, '\u250c', bc)
                for i in range(1, bw - 1):
                    g.put(x + i, y, '\u2500', bc)
                g.put(x + bw - 1, y, '\u2510', bc)

                lc = '\u2524' if left_conn else '\u2502'
                rc = '\u251c' if right_conn else '\u2502'
                g.put(x, y + 1, lc, bc)
                g.put(x + bw - 1, y + 1, rc, bc)

                g.put(x, y + 2, '\u2514', bc)
                for i in range(1, bw - 1):
                    g.put(x + i, y + 2, '\u2500', bc)
                g.put(x + bw - 1, y + 2, '\u2518', bc)

            # -- content --
            inner = bw - 2
            ic = '\u2605' if is_you else ICHARS.get(n.node_type.value, ' ')
            icol = C.YELLOW if is_you else ICOLORS.get(n.node_type.value, None)
            sid = str(n.id)[:6]

            nets = n.networks[:1]
            net_w = 4 if nets else 0       # " [X]"
            overhead = 3 + 9 + net_w       # " i " + " [xxxxxx]" + net
            title_max = max(3, inner - overhead)
            title = n.title[:title_max]
            if len(n.title) > title_max and title_max > 4:
                title = title[:-2] + '..'

            cx = x + 1
            g.put(cx, y + 1, ' ')
            g.put(cx + 1, y + 1, ic, icol, bold=highlight)
            g.put(cx + 2, y + 1, ' ')
            cx += 3

            tc = C.YELLOW if is_you else (C.CYAN if highlight else None)
            for ch in title:
                g.put(cx, y + 1, ch, tc, bold=True)
                cx += 1

            # right-align [id] and optional [net]
            right_start = x + bw - 1 - (9 + net_w)
            if right_start > cx:
                cx = right_start

            g.put(cx, y + 1, ' ', C.DIM)
            cx += 1
            g.puts(cx, y + 1, '[' + sid + ']', C.DIM)
            cx += 8

            if nets and cx < x + bw - 4:
                nt = nets[0].value
                nc = NCOLORS.get(nt, C.DIM)
                nch = NCHARS.get(nt, '?')
                g.puts(cx, y + 1, '[' + nch + ']', nc)

        # ── 9. Draw connectors from a parent to its children ─────
        def draw_connectors(g, par_nid, kids, ngx, ngy, bw):
            par_mid = ngy[par_nid] + 1          # connector row
            gap_start = ngx[par_nid] + bw       # first col after parent box
            jx = gap_start + 2                  # junction column

            child_info = [(k, ngx[k], ngy[k] + 1)
                          for k in kids if k in ngy]
            if not child_info:
                return
            child_info.sort(key=lambda t: t[2])

            top_y = min(par_mid, child_info[0][2])
            bot_y = max(par_mid, child_info[-1][2])

            # horizontal from parent right-edge to junction
            for cx in range(gap_start, min(jx + 1, g.gw)):
                g.put(cx, par_mid, '\u2500', C.DIM)

            # vertical at junction column
            for cy in range(top_y, bot_y + 1):
                g.put(jx, cy, '\u2502', C.DIM)

            # junction characters (overwrite plain │ / ─)
            child_mids = {ci[2] for ci in child_info}
            for cy in range(top_y, bot_y + 1):
                ch = junc(cy == par_mid, cy > top_y,
                          cy in child_mids, cy < bot_y)
                if ch != ' ':
                    g.put(jx, cy, ch, C.DIM)

            # horizontal branches + edge labels to each child
            for kid, kid_x, kid_mid in child_info:
                for cx in range(jx + 1, kid_x):
                    g.put(cx, kid_mid, '\u2500', C.DIM)

                einfo = edge_index.get(frozenset({par_nid, kid}),
                                       ('', par_nid, kid, False))
                elabel, esrc, _, ebidi = einfo
                if ebidi:
                    arrow = '\u2194'
                elif esrc == par_nid:
                    arrow = '\u2192'
                else:
                    arrow = '\u2190'

                ltxt = elabel[:LABEL_MAX] + arrow
                avail = kid_x - jx - 2
                if len(ltxt) > avail > 0:
                    ltxt = ltxt[:avail]
                g.puts(jx + 1, kid_mid, ltxt, C.DIM)

        # ── 10. Render one connected component ────────────────────
        def render_component(comp, center_nid):
            comp_set = set(comp)

            # pick root — prefer You node, then center, then highest-degree
            if YOU_NODE_ID in comp_set:
                root = YOU_NODE_ID
            elif center_nid and center_nid in comp_set:
                root = center_nid
            else:
                root = max(comp_set, key=lambda k: len(adj.get(k, [])))

            # BFS tree
            parent_map = {root: None}
            depth_map = {root: 0}
            children_map: dict[str, list[str]] = defaultdict(list)
            q = deque([root])
            while q:
                nid = q.popleft()
                for nb, _, _ in adj.get(nid, []):
                    if nb in comp_set and nb not in parent_map:
                        parent_map[nb] = nid
                        depth_map[nb] = depth_map[nid] + 1
                        children_map[nid].append(nb)
                        q.append(nb)

            for par in children_map:
                children_map[par].sort(
                    key=lambda k: (node_map[k].node_type.value,
                                   node_map[k].title))

            # Re-parent depth-1 nodes to create sub-clusters
            # If two depth-1 nodes share an edge, move one under the other
            # to avoid flat star topology
            d1_nodes = [nid for nid, d in depth_map.items() if d == 1]
            if len(d1_nodes) > 3:
                # find edges between depth-1 nodes
                d1_set = set(d1_nodes)
                d1_edges: list[tuple[str, str]] = []
                for nid in d1_nodes:
                    for nb, _, _ in adj.get(nid, []):
                        if nb in d1_set and nb > nid:
                            d1_edges.append((nid, nb))
                # pick "hub" nodes: depth-1 nodes with most cross-edges
                d1_degree: dict[str, int] = defaultdict(int)
                for a, b in d1_edges:
                    d1_degree[a] += 1
                    d1_degree[b] += 1
                # hubs = top nodes by cross-degree among d1 peers
                hubs = sorted(d1_degree, key=lambda n: d1_degree[n],
                              reverse=True)
                moved: set[str] = set()
                for hub in hubs:
                    if hub in moved:
                        continue
                    # find peers connected to this hub
                    peers = [nb for nb, _, _ in adj.get(hub, [])
                             if nb in d1_set and nb != hub
                             and nb not in moved and nb != root
                             and hub != root]
                    if not peers or hub == root:
                        continue
                    for peer in peers[:4]:  # max 4 children per hub
                        # re-parent: remove peer from root's children,
                        # add under hub
                        if peer in children_map.get(root, []):
                            children_map[root].remove(peer)
                            children_map[hub].append(peer)
                            parent_map[peer] = hub
                            depth_map[peer] = 2
                            # also update any children of peer
                            q2 = deque(children_map.get(peer, []))
                            while q2:
                                ch = q2.popleft()
                                depth_map[ch] = depth_map[parent_map[ch]] + 1
                                q2.extend(children_map.get(ch, []))
                            moved.add(peer)
                    moved.add(hub)

            # re-sort children after re-parenting
            for par in children_map:
                children_map[par].sort(
                    key=lambda k: (node_map[k].node_type.value,
                                   node_map[k].title))

            max_depth = max(depth_map.values()) if depth_map else 0

            # determine how many layers fit in the terminal
            vis = max_depth + 1
            box_w = 24
            while vis > 1:
                needed = vis * box_w + (vis - 1) * CONN_W + 4
                if needed <= w:
                    break
                vis -= 1
            box_w = max(16, min(28,
                        (w - 4 - max(0, vis - 1) * CONN_W) // max(1, vis)))
            while vis > 1:
                needed = vis * box_w + (vis - 1) * CONN_W + 4
                if needed <= w:
                    break
                vis -= 1

            # prune children beyond visible depth
            if vis < max_depth + 1:
                for nid in list(children_map.keys()):
                    if depth_map.get(nid, 0) >= vis - 1:
                        children_map[nid] = []

            # slot-based layout (DFS assignment, parents centred)
            positions: dict[str, tuple[int, int]] = {}
            slot_ctr = [0]

            def assign(nid):
                kids = children_map.get(nid, [])
                if not kids:
                    positions[nid] = (depth_map[nid], slot_ctr[0])
                    slot_ctr[0] += 1
                    return slot_ctr[0] - 1, slot_ctr[0] - 1
                first = slot_ctr[0]
                for kid in kids:
                    assign(kid)
                last = slot_ctr[0] - 1
                positions[nid] = (depth_map[nid], (first + last) // 2)
                return first, last

            assign(root)
            total_slots = slot_ctr[0]

            # grid coordinates
            mx, my = 1, 0
            ngx: dict[str, int] = {}
            ngy: dict[str, int] = {}
            for nid, (col, slot) in positions.items():
                ngx[nid] = mx + col * (box_w + CONN_W)
                ngy[nid] = my + slot * SLOT_H

            # identify tree edges and cross-edges for this component
            tree_edge_set = {frozenset({nid, par})
                             for nid, par in parent_map.items()
                             if par is not None}
            cross_edges = []
            for nid in comp_set:
                for nb, lbl, bidi in adj.get(nid, []):
                    if nb in comp_set and nb > nid:
                        pair = frozenset({nid, nb})
                        if pair not in tree_edge_set:
                            cross_edges.append((nid, nb, lbl, bidi))

            # determine gutter width for cross-edge routing
            n_routes = min(len(cross_edges), CROSS_MAX_ROUTES)
            gutter_w = n_routes * 2 + (2 if n_routes else 0)

            base_grid_w = (mx + vis * box_w + max(0, vis - 1) * CONN_W
                           + mx + 1)
            grid_w = min(base_grid_w + gutter_w, w - 2)
            # recalculate how many routes actually fit
            actual_gutter = grid_w - base_grid_w
            if actual_gutter < 4:
                n_routes = 0
                actual_gutter = 0
                grid_w = min(base_grid_w, w - 2)
            else:
                n_routes = min(n_routes, (actual_gutter - 2) // 2)

            grid_h = min(my + total_slots * SLOT_H + my, 200)

            g = Grid(grid_w, grid_h)

            # which nodes have outgoing / incoming connectors?
            has_right = {nid for nid in children_map if children_map[nid]}
            has_left = {nid for nid, par in parent_map.items()
                        if par is not None}

            # draw connectors first (behind boxes)
            for par_nid in children_map:
                if children_map[par_nid]:
                    draw_connectors(g, par_nid, children_map[par_nid],
                                    ngx, ngy, box_w)

            # draw boxes on top
            for nid in positions:
                if nid in ngx and nid in ngy:
                    draw_box(g, ngx[nid], ngy[nid], box_w, nid,
                             highlight=(nid == center_nid or nid == YOU_NODE_ID),
                             right_conn=(nid in has_right),
                             left_conn=(nid in has_left))

            # draw cross-edges in the right-side gutter
            def draw_cross_edges(g, cross_edges, ngx, ngy, box_w,
                                 n_routes, base_grid_w):
                """Route cross-edges as dotted lines through the gutter."""
                if n_routes <= 0:
                    return
                gutter_start = base_grid_w
                routed = 0
                for a, b, lbl, bidi in cross_edges[:n_routes]:
                    if a not in ngy or b not in ngy:
                        continue
                    col_idx = gutter_start + 1 + routed * 2
                    if col_idx >= g.gw:
                        break
                    a_mid = ngy[a] + 1  # middle row of box
                    b_mid = ngy[b] + 1
                    a_right = ngx[a] + box_w
                    b_right = ngx[b] + box_w

                    # skip if rows are out of grid bounds
                    if (a_mid < 0 or a_mid >= g.gh
                            or b_mid < 0 or b_mid >= g.gh):
                        continue

                    top_y = min(a_mid, b_mid)
                    bot_y = max(a_mid, b_mid)

                    # horizontal from A's box right edge to gutter col
                    for cx in range(a_right, min(col_idx + 1, g.gw)):
                        if g.ch[a_mid][cx] == ' ':
                            g.put(cx, a_mid, CROSS_CHAR_H, CROSS_COLOR)

                    # horizontal from B's box right edge to gutter col
                    for cx in range(b_right, min(col_idx + 1, g.gw)):
                        if g.ch[b_mid][cx] == ' ':
                            g.put(cx, b_mid, CROSS_CHAR_H, CROSS_COLOR)

                    # vertical in the gutter column
                    for cy in range(top_y, min(bot_y + 1, g.gh)):
                        if col_idx < g.gw and g.ch[cy][col_idx] == ' ':
                            g.put(col_idx, cy, CROSS_CHAR_V, CROSS_COLOR)

                    # place abbreviated edge label in vertical run
                    mid_y = (top_y + bot_y) // 2
                    short_lbl = lbl[:5]
                    for li, lch in enumerate(short_lbl):
                        ly = mid_y - len(short_lbl) // 2 + li
                        if (top_y < ly < bot_y and 0 <= ly < g.gh
                                and col_idx < g.gw
                                and g.ch[ly][col_idx] in (' ', CROSS_CHAR_V)):
                            g.put(col_idx, ly, lch, CROSS_COLOR)

                    routed += 1

            draw_cross_edges(g, cross_edges, ngx, ngy, box_w,
                             n_routes, base_grid_w)

            for line in g.render():
                print(f"  {line}")

            if vis < max_depth + 1:
                deeper = sum(1 for d in depth_map.values() if d >= vis)
                print(f"\n  {C.DIM}(+{deeper} nodes beyond depth "
                      f"{vis - 1} not shown){C.RESET}")

            return (tree_edge_set, n_routes)

        # ── 11. Main render loop ─────────────────────────────────
        all_tree_edges: set[frozenset] = set()
        total_routes = 0

        for ci, comp in enumerate(multi):
            if len(multi) > 1:
                print(f"\n  {C.BOLD}Component {ci + 1} of "
                      f"{len(multi)}{C.RESET}"
                      f"  {C.DIM}({len(comp)} nodes){C.RESET}")

            tree_edges, n_routes = render_component(comp, center_str)
            all_tree_edges |= tree_edges
            total_routes += n_routes

            # cross-edges for this component
            cs = set(comp)
            cross = [
                e for e in edges
                if (frozenset({str(e.source_id), str(e.target_id)})
                    not in all_tree_edges)
                and str(e.source_id) in cs
                and str(e.target_id) in cs
            ]
            if cross:
                # bold magenta boxed header
                hdr_text = " CROSS-CONNECTIONS "
                rule_w = max(0, w - len(hdr_text) - 8)
                print(f"\n  {C.BOLD}{CROSS_COLOR}"
                      f"╌╌{hdr_text}"
                      f"{'╌' * rule_w}{C.RESET}")
                if n_routes > 0:
                    print(f"  {C.DIM}({n_routes} shown as dotted "
                          f"lines above){C.RESET}")

                # group by edge type
                by_type: dict[str, list] = defaultdict(list)
                for e in cross:
                    el = (e.edge_type.value
                          if hasattr(e.edge_type, 'value')
                          else str(e.edge_type))
                    by_type[el].append(e)

                shown = 0
                for etype in sorted(by_type):
                    if shown >= 15:
                        break
                    print(f"  {CROSS_COLOR}{C.BOLD}{etype}:{C.RESET}")
                    for e in by_type[etype]:
                        if shown >= 15:
                            break
                        src, tgt = str(e.source_id), str(e.target_id)
                        sn, tn = node_map.get(src), node_map.get(tgt)
                        si = ICHARS.get(sn.node_type.value, ' ') if sn else ' '
                        ti = ICHARS.get(tn.node_type.value, ' ') if tn else ' '
                        sicol = ICOLORS.get(sn.node_type.value, '') if sn else ''
                        ticol = ICOLORS.get(tn.node_type.value, '') if tn else ''
                        st = sn.title[:16] if sn else src[:8]
                        tt = tn.title[:16] if tn else tgt[:8]
                        bd = getattr(e, 'bidirectional', False)
                        arr = '\u2194' if bd else '\u2192'
                        print(f"    {sicol}{si}{C.RESET} {st} "
                              f"{C.DIM}[{src[:6]}]{C.RESET} "
                              f"{CROSS_COLOR}╌╌[{arr}]╌╌{C.RESET} "
                              f"{ticol}{ti}{C.RESET} {tt} "
                              f"{C.DIM}[{tgt[:6]}]{C.RESET}")
                        shown += 1
                remaining = len(cross) - shown
                if remaining > 0:
                    print(f"  {C.DIM}  ... and "
                          f"{remaining} more{C.RESET}")
                all_tree_edges |= {
                    frozenset({str(e.source_id), str(e.target_id)})
                    for e in cross}

        # ── 12. Isolated singletons ──────────────────────────────
        if isolated:
            rule_w = max(0, w - 35)
            print(f"\n  {C.DIM}\u2500\u2500 unconnected nodes "
                  f"({len(isolated)}) "
                  + "\u2500" * rule_w + f"{C.RESET}")
            for nid in isolated:
                n = node_map[nid]
                ic = ICHARS.get(n.node_type.value, ' ')
                icol = ICOLORS.get(n.node_type.value, '')
                nets = ''.join(
                    NETWORK_ICONS.get(nt.value, '') for nt in n.networks[:2])
                print(f"  {icol}{ic}{C.RESET} {C.BOLD}"
                      f"{n.title[:24]}{C.RESET} "
                      f"{C.DIM}[{str(n.id)[:6]}]{C.RESET} {nets}")

        # ── 13. Legend ───────────────────────────────────────────
        print(f"\n{divider()}")
        print(f"  {C.BOLD}LEGEND{C.RESET}")

        # You node legend entry
        if any(str(n.id) == YOU_NODE_ID for n in nodes):
            print(f"  {C.YELLOW}\u2605{C.RESET}={C.DIM}YOU (center){C.RESET}  "
                  f"{C.YELLOW}\u2554\u2550\u2557{C.RESET} {C.DIM}double border = You node{C.RESET}")

        types_present = sorted({n.node_type.value for n in nodes})
        tl = "  Types:     "
        for t in types_present:
            ic = ICHARS.get(t, ' ')
            icol = ICOLORS.get(t, '')
            tl += f" {icol}{ic}{C.RESET}={C.DIM}{t}{C.RESET}"
        print(tl)

        nets_present = sorted(
            {nt.value for n in nodes for nt in n.networks})
        if nets_present:
            nl = "  Networks:  "
            for nt in nets_present:
                icon = NETWORK_ICONS.get(nt, f"[{nt[0]}]")
                nl += f" {icon}={C.DIM}{nt}{C.RESET}"
            print(nl)

        edge_types = sorted({
            e.edge_type.value if hasattr(e.edge_type, 'value')
            else str(e.edge_type) for e in edges})
        if edge_types:
            print(f"  {C.DIM}Edges:      "
                  f"{', '.join(edge_types)}{C.RESET}")

        print(f"\n  {C.DIM}Arrows: \u2192 directed  "
              f"\u2190 inbound  \u2194 bidirectional{C.RESET}")
        print(f"  {C.DIM}\u251c\u2500\u2500 connector exit   "
              f"\u2524\u2500\u2500 connector entry{C.RESET}")
        print(f"  {CROSS_COLOR}╌╌╌{C.RESET}"
              f" {C.DIM}= cross-connection (non-tree edge){C.RESET}")
        if center_id:
            print(f"  {C.CYAN}Colored box{C.RESET}"
                  f" {C.DIM}= center node{C.RESET}")
        print(divider('\u2550', C.CYAN))

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
        nodes_by_net = stats.get("network_breakdown", {})

        total_nodes = stats.get("node_count", 0) or 1

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

        total_nodes = stats.get("node_count", 0)
        total_edges = stats.get("edge_count", 0)
        nodes_by_type = stats.get("type_breakdown", {})
        nodes_by_net = stats.get("network_breakdown", {})

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
    |   {C.DIM}{datetime.now(UTC).strftime('%A, %B %d, %Y')}{C.RESET}{C.CYAN}  |
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
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            coro = strat.generate_briefing(
                health_scores=health,
                alerts=alerts,
                bridges=bridges,
                commitments=commitments,
                review_items=review_items,
            )

            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    briefing = pool.submit(asyncio.run, coro).result()
            else:
                briefing = asyncio.run(coro)
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

    # ── 9. Dossier ────────────────────────────────────────────────

    def cmd_dossier(self):
        dossier_art = f"""
{C.MAGENTA}     .─────────.
    /  DOSSIER  \\
   |  ┌──┬──┐   |    {C.BOLD}ENTITY DOSSIER{C.RESET}{C.MAGENTA}
   |  │▓▓│  │   |
   |  ├──┼──┤   |    {C.DIM}Multi-signal deep search.{C.RESET}{C.MAGENTA}
   |  │  │▓▓│   |    {C.DIM}Title + graph + semantic.{C.RESET}{C.MAGENTA}
   |  └──┴──┘   |
    \\_________/{C.RESET}
"""
        print(dossier_art)

        query = prompt(f"  {C.MAGENTA}Search entity: {C.RESET}")
        if not query or query == "q":
            return

        spinner("Searching by title", 0.4)

        # 1. Title match
        title_matches = self.repo.search_by_title(query, limit=10)
        if not title_matches:
            # Fallback: semantic search via embeddings
            spinner("No title match — trying semantic search", 0.4)
            title_matches = self._dossier_semantic_fallback(query)
            if not title_matches:
                print(f"\n  {C.DIM}No entities matching '{query}'.{C.RESET}")
                return

        # Score and pick best match
        lower_q = query.lower()
        scored: list[tuple[float, object]] = []
        for node in title_matches:
            lt = node.title.lower()
            if lt == lower_q:
                score = 1.0
            elif lt.startswith(lower_q):
                score = 0.9
            else:
                score = 0.7
            scored.append((score, node))
        scored.sort(key=lambda x: x[0], reverse=True)

        # If multiple matches, let user pick
        if len(scored) > 1:
            print(f"\n  {C.BOLD}{len(scored)} matches found:{C.RESET}\n")
            for i, (sc, n) in enumerate(scored, 1):
                icon = NODE_ICONS.get(n.node_type.value, " ")
                nets = " ".join(NETWORK_ICONS.get(nt.value, f"[{nt.value[0]}]") for nt in n.networks)
                print(f"  {C.DIM}{i:2}.{C.RESET} {icon} {C.BOLD}{n.title}{C.RESET}  {nets}  "
                      f"conf={n.confidence:.0%}  {C.DIM}{str(n.id)[:8]}{C.RESET}")
            choice = prompt(f"  Select [1-{len(scored)}, default 1]: ")
            try:
                idx = int(choice) - 1 if choice else 0
                entity = scored[idx][1]
            except (ValueError, IndexError):
                entity = scored[0][1]
        else:
            entity = scored[0][1]

        print()
        self._render_node_detail(entity)

        # 2. Neighborhood
        spinner("Traversing graph neighborhood (2-hop)", 0.5)
        subgraph = self.repo.get_neighborhood(entity.id, hops=2)

        # Direct connections (sorted by strength)
        entity_str = str(entity.id)
        direct_edges = [e for e in subgraph.edges
                        if str(e.source_id) == entity_str or str(e.target_id) == entity_str]
        nodes_by_id = {str(n.id): n for n in subgraph.nodes}

        connections = []
        for edge in direct_edges:
            neighbor_id = str(edge.target_id) if str(edge.source_id) == entity_str else str(edge.source_id)
            neighbor_node = nodes_by_id.get(neighbor_id)
            if neighbor_node:
                strength = edge.weight * edge.confidence
                connections.append((strength, edge, neighbor_node))
        connections.sort(key=lambda x: x[0], reverse=True)

        min_strength = 0.75
        top_connections = [(s, e, n) for s, e, n in connections if s >= min_strength]
        if connections:
            hidden = len(connections) - len(top_connections)
            print(f"\n{divider('─', C.CYAN)}")
            print(f"  {C.BOLD}{C.CYAN}CONNECTIONS ({len(top_connections)}){C.RESET}  {C.DIM}sorted by strength, ≥{min_strength:.0%}{C.RESET}")
            print(divider())
            for i, (strength, edge, neighbor) in enumerate(top_connections, 1):
                direction = "→" if str(edge.source_id) == entity_str else "←"
                icon = NODE_ICONS.get(neighbor.node_type.value, " ")
                etype = edge.edge_type.value if hasattr(edge.edge_type, 'value') else str(edge.edge_type)
                bar = horizontal_bar(min(strength, 1.0), 10, C.CYAN)
                print(f"  {C.DIM}{i}.{C.RESET} {C.CYAN}{direction}{C.RESET} {icon} {C.BOLD}{neighbor.title[:35]:<35}{C.RESET} "
                      f"{C.DIM}[{etype}]{C.RESET}  {bar}")
            if hidden:
                print(f"    {C.DIM}... {hidden} weaker connections below {min_strength:.0%}{C.RESET}")
        else:
            print(f"\n  {C.DIM}No direct connections.{C.RESET}")

        # 3. Vector-similar entities (not in neighborhood)
        neighborhood_ids = {str(n.id) for n in subgraph.nodes}
        related = self._dossier_find_related(entity, neighborhood_ids)
        if related:
            print(f"\n{divider('─', C.MAGENTA)}")
            print(f"  {C.BOLD}{C.MAGENTA}RELATED ENTITIES ({len(related)}){C.RESET}  {C.DIM}semantically similar, not directly connected{C.RESET}")
            print(divider())
            for sim_score, rel_node in related:
                icon = NODE_ICONS.get(rel_node.node_type.value, " ")
                nets = " ".join(NETWORK_ICONS.get(nt.value, f"[{nt.value[0]}]") for nt in rel_node.networks)
                pct = f"{sim_score * 100:.0f}%"
                print(f"  {C.MAGENTA}~{C.RESET} {icon} {C.BOLD}{rel_node.title[:35]:<35}{C.RESET} "
                      f"{nets}  {C.DIM}similarity {pct}{C.RESET}")

        # 4. Facts
        facts = self._dossier_get_facts(entity_str)
        if facts:
            print(f"\n{divider('─', C.GREEN)}")
            print(f"  {C.BOLD}{C.GREEN}VERIFIED FACTS ({len(facts)}){C.RESET}")
            print(divider())
            for fact in facts[:15]:
                conf = fact.get("confidence", 0)
                lifecycle = fact.get("lifecycle", "")
                lc_color = C.GREEN if lifecycle == "static" else C.YELLOW
                statement = fact.get("statement", "")
                print(f"  {C.GREEN}✓{C.RESET} {statement[:70]}")
                print(f"    {horizontal_bar(conf, 10, C.GREEN)}  "
                      f"{lc_color}{lifecycle}{C.RESET}")
            if len(facts) > 15:
                print(f"    {C.DIM}... and {len(facts) - 15} more{C.RESET}")
        else:
            print(f"\n  {C.DIM}No verified facts for this entity.{C.RESET}")

        # 5. Graph summary
        print(f"\n{divider('─', C.BLUE)}")
        n_nodes = len(subgraph.nodes)
        n_edges = len(subgraph.edges)
        print(f"  {C.BOLD}{C.BLUE}SUBGRAPH{C.RESET}  "
              f"{C.BOLD}{n_nodes}{C.RESET} nodes  {C.DIM}|{C.RESET}  "
              f"{C.BOLD}{n_edges}{C.RESET} edges  {C.DIM}(2-hop neighborhood){C.RESET}")

        # Offer actions
        drill_hint = f"[1-{len(top_connections)}] Drill into connection  " if connections else ""
        print(f"\n  {C.DIM}{drill_hint}[v] Visualize graph map  [b] Back{C.RESET}")
        action = prompt("dossier> ").strip()
        if action == "v":
            self._render_ascii_graph(subgraph, center_id=entity.id)
        elif action.isdigit() and connections:
            idx = int(action) - 1
            if 0 <= idx < len(top_connections):
                _, _, drill_node = top_connections[idx]
                print(f"\n  {C.DIM}Drilling into {drill_node.title}...{C.RESET}")
                self._render_node_detail(drill_node)

                drill_sub = self.repo.get_neighborhood(drill_node.id, hops=2)
                drill_str = str(drill_node.id)
                drill_edges = [e for e in drill_sub.edges
                               if str(e.source_id) == drill_str or str(e.target_id) == drill_str]
                drill_nodes_by_id = {str(n.id): n for n in drill_sub.nodes}

                drill_conns = []
                for edge in drill_edges:
                    nid = str(edge.target_id) if str(edge.source_id) == drill_str else str(edge.source_id)
                    nn = drill_nodes_by_id.get(nid)
                    if nn:
                        s = edge.weight * edge.confidence
                        drill_conns.append((s, edge, nn))
                drill_conns.sort(key=lambda x: x[0], reverse=True)

                top_drill = [(s, e, n) for s, e, n in drill_conns if s >= min_strength]
                if top_drill:
                    drill_hidden = len(drill_conns) - len(top_drill)
                    print(f"\n{divider('─', C.CYAN)}")
                    print(f"  {C.BOLD}{C.CYAN}CONNECTIONS ({len(top_drill)}){C.RESET}  {C.DIM}sorted by strength, ≥{min_strength:.0%}{C.RESET}")
                    print(divider())
                    for j, (s, edge, nn) in enumerate(top_drill, 1):
                        d = "→" if str(edge.source_id) == drill_str else "←"
                        ic = NODE_ICONS.get(nn.node_type.value, " ")
                        et = edge.edge_type.value if hasattr(edge.edge_type, 'value') else str(edge.edge_type)
                        bar = horizontal_bar(min(s, 1.0), 10, C.CYAN)
                        print(f"  {C.DIM}{j}.{C.RESET} {C.CYAN}{d}{C.RESET} {ic} {C.BOLD}{nn.title[:35]:<35}{C.RESET} "
                              f"{C.DIM}[{et}]{C.RESET}  {bar}")
                    if drill_hidden:
                        print(f"    {C.DIM}... {drill_hidden} weaker connections below {min_strength:.0%}{C.RESET}")
                else:
                    print(f"\n  {C.DIM}No direct connections.{C.RESET}")
            else:
                print(f"  {C.DIM}Invalid selection.{C.RESET}")

    def _dossier_semantic_fallback(self, query: str) -> list:
        """Fall back to vector/semantic search when title search finds nothing."""
        try:
            engine = self._get_embedding_engine()
            store = self._get_vector_store()
            if not engine or not store:
                return []

            embedding = engine.embed_text(query)
            results = store.dense_search(query_vector=embedding["dense"], top_k=10)

            nodes = []
            for sr in results:
                if sr.score >= 0.5:
                    node = self.repo.get_node(UUID(sr.node_id))
                    if node:
                        nodes.append(node)
            return nodes
        except Exception as e:
            print(f"  {C.DIM}(semantic fallback unavailable: {e}){C.RESET}")
            return []

    def _dossier_find_related(self, entity, exclude_ids: set[str]) -> list[tuple[float, object]]:
        """Find vector-similar entities not in the given ID set."""
        try:
            engine = self._get_embedding_engine()
            store = self._get_vector_store()
            if not engine or not store:
                return []

            spinner("Finding semantically similar entities", 0.5)

            text = f"{entity.title} {entity.content or ''}"
            embedding = engine.embed_text(text)
            results = store.dense_search(query_vector=embedding["dense"], top_k=20)

            entity_str = str(entity.id)
            related = []
            for sr in results:
                if sr.node_id not in exclude_ids and sr.node_id != entity_str:
                    node = self.repo.get_node(UUID(sr.node_id))
                    if node:
                        related.append((sr.score, node))
            related.sort(key=lambda x: x[0], reverse=True)
            return [(s, n) for s, n in related if s >= 0.75]
        except Exception as e:
            print(f"  {C.DIM}(vector search unavailable: {e}){C.RESET}")
            return []

    def _dossier_get_facts(self, node_id: str) -> list[dict]:
        """Get verified facts for a node."""
        try:
            from memora.core.truth_layer import TruthLayer
            truth = TruthLayer(conn=self.repo._conn)
            return truth.query_facts(node_id=node_id, status="active", limit=50)
        except Exception as e:
            print(f"  {C.DIM}(facts query unavailable: {e}){C.RESET}")
            return []

    # ── Goodbye ───────────────────────────────────────────────────

    def cmd_clear_data(self):
        """Erase all databases (DuckDB, LanceDB, SQLite, backups) and start fresh."""
        print(f"\n{divider('═', C.RED)}")
        print(f"  {C.BOLD}{C.RED}CLEAR ALL DATA{C.RESET}")
        print(divider())
        print(f"  {C.YELLOW}This will permanently delete:{C.RESET}")
        print(f"    - Graph database   {C.DIM}({self.settings.graph_dir}){C.RESET}")
        print(f"    - Vector store     {C.DIM}({self.settings.vector_dir}){C.RESET}")
        print(f"    - Backups          {C.DIM}({self.settings.backups_dir}){C.RESET}")

        sqlite_path = Path(__file__).parent / "memora.db"
        if sqlite_path.exists():
            print(f"    - SQLite file      {C.DIM}({sqlite_path}){C.RESET}")

        print()
        confirm = prompt(f"  {C.RED}Type 'yes' to confirm: {C.RESET}")
        if confirm.lower() != "yes":
            print(f"  {C.DIM}Cancelled.{C.RESET}")
            return

        # Close the repo connection before deleting
        if self.repo:
            self.repo.close()
            self.repo = None

        deleted = []

        # Delete DuckDB graph database
        graph_dir = self.settings.graph_dir
        if graph_dir.exists():
            shutil.rmtree(graph_dir)
            deleted.append("Graph database")

        # Delete LanceDB vector store
        vector_dir = self.settings.vector_dir
        if vector_dir.exists():
            shutil.rmtree(vector_dir)
            deleted.append("Vector store")

        # Delete backups
        backups_dir = self.settings.backups_dir
        if backups_dir.exists():
            shutil.rmtree(backups_dir)
            deleted.append("Backups")

        # Delete local SQLite file
        if sqlite_path.exists():
            sqlite_path.unlink()
            deleted.append("SQLite file")

        if deleted:
            print(f"\n  {C.GREEN}Deleted:{C.RESET} {', '.join(deleted)}")
        else:
            print(f"\n  {C.DIM}Nothing to delete.{C.RESET}")

        # Re-initialize directories and reconnect
        from memora.config import init_data_directory
        init_data_directory(self.settings)
        self.repo = GraphRepository(db_path=self.settings.db_path)

        print(f"  {C.GREEN}Fresh databases initialized. Memora is ready.{C.RESET}\n")

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
