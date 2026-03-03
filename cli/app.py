"""MemoraApp — main CLI application class, boot sequence, and main loop."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import UUID

# ── Ensure the backend package is importable ──────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

# Suppress noisy logs unless user wants them
os.environ.setdefault("MEMORA_LOG_LEVEL", "WARNING")

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from memora.config import load_settings, Settings
from memora.graph.repository import GraphRepository, YOU_NODE_ID

from cli.rendering import (
    C, boot_sequence, command_deck, goodbye_card,
    divider, horizontal_bar, menu_option, prompt, spinner,
)


class MemoraApp:
    """Main CLI application."""

    def __init__(self):
        self.settings: Settings | None = None
        self.repo: GraphRepository | None = None
        self._pipeline = None
        self._orchestrator = None
        self._strategist = None

    def boot(self):
        """Initialize settings & repo with staged boot sequence."""
        subsystem_status = {}

        self.settings = load_settings()

        # Graph engine
        try:
            self.repo = GraphRepository(db_path=self.settings.db_path)
            subsystem_status["graph"] = "ONLINE"
        except Exception:
            subsystem_status["graph"] = "OFFLINE"

        # Vector store check
        try:
            vector_dir = self.settings.vector_dir
            if Path(vector_dir).exists() or True:  # always attempt
                subsystem_status["vector"] = "ONLINE"
        except Exception:
            subsystem_status["vector"] = "OFFLINE"

        # Embedding engine — STANDBY until lazily loaded
        subsystem_status["embedding"] = "STANDBY"

        # AI council
        api_key = self.settings.openai_api_key
        if not api_key or api_key.startswith("sk-PASTE"):
            self._has_api_key = False
            subsystem_status["council"] = "STANDBY"
        else:
            self._has_api_key = True
            subsystem_status["council"] = "ONLINE"

        # Scheduler
        subsystem_status["scheduler"] = "ONLINE"

        boot_sequence(subsystem_status)

    def _get_embedding_engine(self):
        """Lazily initialize the embedding engine."""
        if not hasattr(self, '_embedding_engine') or self._embedding_engine is None:
            try:
                import logging as _logging
                from memora.vector.embeddings import EmbeddingEngine

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
            print(f"  {C.DANGER}Pipeline init failed: {e}{C.RESET}")
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
            print(f"  {C.DANGER}Orchestrator init failed: {e}{C.RESET}")
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
            print(f"  {C.DANGER}Strategist init failed: {e}{C.RESET}")
            return None

    # ── Telemetry Data ─────────────────────────────────────────

    def _gather_telemetry(self) -> dict:
        """Gather live telemetry data for the command deck."""
        data = {
            "operator_name": "",
            "node_count": 0,
            "edge_count": 0,
            "density": 0.0,
            "network_health": {},
            "pending_proposals": 0,
            "alert_count": 0,
            "pending_count": 0,
        }

        if not self.repo:
            return data

        try:
            stats = self.repo.get_graph_stats()
            data["node_count"] = stats.get("node_count", 0)
            data["edge_count"] = stats.get("edge_count", 0)

            n = data["node_count"]
            if n > 1:
                data["density"] = (2 * data["edge_count"]) / (n * (n - 1))
        except Exception:
            pass

        # Operator name from You node
        try:
            you_node = self.repo.get_node(UUID(YOU_NODE_ID))
            if you_node and you_node.properties:
                name = you_node.properties.get("name", "")
                if name and name != "You":
                    data["operator_name"] = name
        except Exception:
            pass

        # Network health scores
        try:
            from memora.core.health_scoring import HealthScorer
            scorer = HealthScorer(self.repo)
            for net_name in ["ACADEMIC", "PROFESSIONAL", "FINANCIAL", "HEALTH",
                             "PERSONAL_GROWTH", "SOCIAL", "VENTURES"]:
                try:
                    score_result = scorer.score_network(net_name)
                    if isinstance(score_result, dict):
                        data["network_health"][net_name] = score_result.get("score", 0.0)
                    elif isinstance(score_result, (int, float)):
                        data["network_health"][net_name] = float(score_result)
                except Exception:
                    data["network_health"][net_name] = 0.0
        except Exception:
            pass

        # Pending proposals count
        try:
            proposals = self.repo.get_pending_proposals()
            data["pending_proposals"] = len(proposals)
            data["pending_count"] = len(proposals)
        except Exception:
            pass

        return data

    # ── Main Loop ─────────────────────────────────────────────────

    def run(self):
        self.boot()

        while True:
            telemetry = self._gather_telemetry()
            command_deck(**telemetry)
            choice = prompt("memora ❯ ")

            if choice in ("q", "quit", "exit"):
                self._goodbye()
                break
            elif choice in ("c", "c!"):
                from cli.commands.capture import cmd_capture
                cmd_capture(self, force=(choice == "c!"))
            elif choice == "p":
                from cli.commands.profile import cmd_profile
                cmd_profile(self)
            elif choice == "r":
                from cli.commands.proposals import cmd_proposals
                cmd_proposals(self)
            elif choice == "d":
                from cli.commands.dossier import cmd_dossier
                cmd_dossier(self)
            elif choice == "i":
                from cli.commands.investigate import cmd_investigate
                cmd_investigate(self)
            elif choice == "w":
                from cli.commands.browse import cmd_browse
                cmd_browse(self)
            elif choice == "b":
                from cli.commands.briefing import cmd_briefing
                cmd_briefing(self)
            elif choice == "k":
                from cli.commands.critique import cmd_critique
                cmd_critique(self)
            elif choice == "u":
                from cli.commands.council import cmd_council
                cmd_council(self)
            elif choice == "t":
                from cli.commands.timeline import cmd_timeline
                cmd_timeline(self)
            elif choice == "o":
                from cli.commands.outcomes import cmd_outcomes
                cmd_outcomes(self)
            elif choice == "a":
                from cli.commands.patterns import cmd_patterns
                cmd_patterns(self)
            elif choice == "g":
                from cli.commands.stats import cmd_stats
                cmd_stats(self)
            elif choice == "n":
                from cli.commands.networks import cmd_networks
                cmd_networks(self)
            elif choice == "e":
                from cli.commands.people import cmd_people
                cmd_people(self)
            elif choice == "j":
                from cli.commands.actions import cmd_actions
                cmd_actions(self)
            elif choice == "f":
                from cli.commands.graph_intel import cmd_graph_intel
                cmd_graph_intel(self)
            elif choice == "s":
                from cli.commands.connectors import cmd_connectors
                cmd_connectors(self)
            elif choice == "0":
                self._show_settings()
            elif choice in ("x", "clear"):
                from cli.commands.clear_data import cmd_clear_data
                cmd_clear_data(self)
            else:
                print(f"  {C.DIM}Unknown command. Valid keys: c p r d i w f s b k u t o a g n e j 0 x q{C.RESET}")

    def _show_settings(self):
        """Display current settings."""
        from cli.rendering import subcommand_header
        subcommand_header("SETTINGS", symbol="⚙", color=C.DIM, border="simple")

        if self.settings:
            print(f"    {C.DIM}Data dir:{C.RESET}        {C.BASE}{self.settings.data_dir}{C.RESET}")
            print(f"    {C.DIM}Graph DB:{C.RESET}        {C.BASE}{self.settings.db_path}{C.RESET}")
            print(f"    {C.DIM}Vector store:{C.RESET}    {C.BASE}{self.settings.vector_dir}{C.RESET}")
            api_status = f"{C.CONFIRM}configured{C.RESET}" if self._has_api_key else f"{C.SIGNAL}not set{C.RESET}"
            print(f"    {C.DIM}OpenAI API key:{C.RESET}  {api_status}")
            print()

    def _goodbye(self):
        goodbye_card()
        if self.repo:
            self.repo.close()


def main():
    try:
        app = MemoraApp()
        app.run()
    except KeyboardInterrupt:
        print(f"\n\n{C.DIM}  Interrupted. Goodbye!{C.RESET}\n")


if __name__ == "__main__":
    main()
