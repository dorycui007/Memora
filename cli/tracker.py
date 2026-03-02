"""Live pipeline progress tracker for the terminal."""

from __future__ import annotations

import sys

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
