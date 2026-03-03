"""Live pipeline progress tracker for the terminal."""

from __future__ import annotations

import sys
import threading
import time

from memora.core.pipeline import PipelineStage, STAGE_NAMES

from cli.rendering import C, term_width

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

_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class PipelineTracker:
    """Renders a live ASCII pipeline progress display in the terminal.

    Shows a spinner animation and elapsed time for the currently running stage.
    A background thread redraws the tracker every 100ms while a stage is active.
    """

    def __init__(self) -> None:
        self._stage_status: dict[PipelineStage, str] = {
            s: "pending" for s in _PIPELINE_STAGES
        }
        self._stage_elapsed: dict[PipelineStage, float] = {}
        self._current_stage_start: float | None = None
        self._current_stage: PipelineStage | None = None
        self._spinner_idx = 0
        self._printed = False
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _render(self) -> str:
        """Build the full ASCII tracker string."""
        w = min(term_width() - 4, 72)
        lines = []
        lines.append(f"  {C.CYAN}{'─' * w}{C.RESET}")
        lines.append(f"  {C.BOLD}{C.CYAN} PIPELINE{C.RESET}")
        lines.append(f"  {C.CYAN}{'─' * w}{C.RESET}")

        for stage in _PIPELINE_STAGES:
            status = self._stage_status[stage]
            name = STAGE_NAMES.get(stage, stage.name)
            elapsed = self._stage_elapsed.get(stage)

            # Build elapsed time string
            time_str = ""
            if status == "running" and self._current_stage_start is not None:
                secs = time.monotonic() - self._current_stage_start
                time_str = f" {C.DIM}{self._fmt_elapsed(secs)}{C.RESET}"
            elif elapsed is not None:
                time_str = f" {C.DIM}{self._fmt_elapsed(elapsed)}{C.RESET}"

            if status == "running":
                frame = _SPINNER_FRAMES[self._spinner_idx % len(_SPINNER_FRAMES)]
                icon = f"{C.YELLOW} {frame} {C.RESET}"
                label = f"{C.YELLOW}{C.BOLD}{name}{C.RESET}{time_str}"
            elif status == "done":
                icon = f"{C.GREEN} + {C.RESET}"
                label = f"{C.GREEN}{name}{C.RESET}{time_str}"
            elif status == "failed":
                icon = f"{C.RED} x {C.RESET}"
                label = f"{C.RED}{name}{C.RESET}{time_str}"
            elif status == "skipped":
                icon = f"{C.DIM} - {C.RESET}"
                label = f"{C.DIM}{name}{C.RESET}"
            else:
                icon = f"{C.DIM}   {C.RESET}"
                label = f"{C.DIM}{name}{C.RESET}"

            lines.append(f"  {icon} {label}")

        lines.append(f"  {C.CYAN}{'─' * w}{C.RESET}")
        return "\n".join(lines)

    @staticmethod
    def _fmt_elapsed(secs: float) -> str:
        """Format elapsed seconds as a human-readable duration."""
        if secs < 60:
            return f"{secs:.1f}s"
        minutes = int(secs // 60)
        remaining = secs - minutes * 60
        return f"{minutes}m {remaining:.1f}s"

    def _line_count(self) -> int:
        """How many terminal lines the tracker occupies."""
        return len(_PIPELINE_STAGES) + 3  # stages + 3 border/header lines

    def _draw(self) -> None:
        """Write the tracker to stdout, overwriting the previous render."""
        if self._printed:
            n = self._line_count()
            sys.stdout.write(f"\033[{n}A")
        sys.stdout.write(self._render() + "\n")
        sys.stdout.flush()
        self._printed = True

    def _tick_loop(self) -> None:
        """Background thread: redraw the tracker every 100ms for spinner + timer."""
        while not self._stop_event.is_set():
            self._stop_event.wait(0.1)
            if self._stop_event.is_set():
                break
            with self._lock:
                self._spinner_idx += 1
                self._draw()

    def _start_ticker(self) -> None:
        """Start the background redraw thread if not already running."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._tick_loop, daemon=True)
        self._thread.start()

    def _stop_ticker(self) -> None:
        """Stop the background redraw thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=0.5)
            self._thread = None

    def on_stage(self, stage: PipelineStage, status: str) -> None:
        """Callback for pipeline stage transitions. Redraws the tracker."""
        with self._lock:
            now = time.monotonic()

            # Record elapsed time for the stage that just finished
            if (
                self._current_stage is not None
                and self._current_stage_start is not None
                and stage != self._current_stage
            ):
                self._stage_elapsed[self._current_stage] = (
                    now - self._current_stage_start
                )

            if status == "running":
                self._current_stage = stage
                self._current_stage_start = now
            elif status in ("done", "failed", "skipped"):
                if self._current_stage == stage and self._current_stage_start is not None:
                    self._stage_elapsed[stage] = now - self._current_stage_start
                self._current_stage = None
                self._current_stage_start = None

            self._stage_status[stage] = status
            self._draw()

        # Start/stop the background ticker based on whether a stage is running
        if status == "running":
            self._start_ticker()
        elif self._current_stage is None:
            self._stop_ticker()
