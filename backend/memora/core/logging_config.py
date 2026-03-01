"""Structured JSON logging for Memora.

Provides a JSON formatter for log records that outputs structured data
suitable for log aggregation and analysis. Includes pipeline stage timing,
LLM call logging, and background job execution logging.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info and record.exc_info[1]:
            log_data["exception"] = self.formatException(record.exc_info)

        # Attach extra structured fields if present
        for key in ("stage", "capture_id", "duration_ms", "tokens", "cost",
                     "job_name", "node_count", "model", "component"):
            val = getattr(record, key, None)
            if val is not None:
                log_data[key] = val

        return json.dumps(log_data, default=str)


class PipelineTimingLogger:
    """Helper for logging pipeline stage durations."""

    def __init__(self, logger_instance: logging.Logger) -> None:
        self._logger = logger_instance

    def start_stage(self, stage_name: str, capture_id: str) -> float:
        """Log stage start and return the start timestamp."""
        self._logger.info(
            "Pipeline stage started: %s",
            stage_name,
            extra={"stage": stage_name, "capture_id": capture_id, "component": "pipeline"},
        )
        return time.time()

    def end_stage(self, stage_name: str, capture_id: str, start_time: float) -> None:
        """Log stage completion with duration."""
        duration_ms = round((time.time() - start_time) * 1000, 2)
        self._logger.info(
            "Pipeline stage completed: %s in %.2fms",
            stage_name,
            duration_ms,
            extra={
                "stage": stage_name,
                "capture_id": capture_id,
                "duration_ms": duration_ms,
                "component": "pipeline",
            },
        )


class LLMCallLogger:
    """Helper for logging LLM API calls with token usage and cost."""

    # Approximate costs per 1K tokens (Claude models)
    COSTS_PER_1K = {
        "claude-haiku-4-5-20251001": {"input": 0.00025, "output": 0.00125},
        "claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
        "claude-opus-4-6": {"input": 0.015, "output": 0.075},
    }

    def __init__(self, logger_instance: logging.Logger) -> None:
        self._logger = logger_instance

    def log_call(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        purpose: str = "",
    ) -> None:
        """Log an LLM API call with token usage and estimated cost."""
        costs = self.COSTS_PER_1K.get(model, {"input": 0.003, "output": 0.015})
        cost = (
            (input_tokens / 1000) * costs["input"]
            + (output_tokens / 1000) * costs["output"]
        )

        self._logger.info(
            "LLM call: %s — %d in, %d out, $%.6f (%s)",
            model,
            input_tokens,
            output_tokens,
            cost,
            purpose,
            extra={
                "model": model,
                "tokens": {"input": input_tokens, "output": output_tokens},
                "cost": round(cost, 6),
                "component": "llm",
            },
        )


def configure_logging(
    log_level: str = "INFO",
    log_dir: Path | None = None,
    json_format: bool = True,
) -> None:
    """Configure Memora logging with optional JSON output to file.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR).
        log_dir: Directory for log files. If None, logs only to stderr.
        json_format: If True, use JSON formatting for file output.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Silence noisy third-party loggers
    for name in ("httpx", "huggingface_hub", "sentence_transformers"):
        logging.getLogger(name).setLevel(logging.WARNING)

    # Console handler (human-readable)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root_logger.addHandler(console_handler)

    # File handler (JSON structured)
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "memora.log"
        file_handler = logging.FileHandler(str(log_file))

        if json_format:
            file_handler.setFormatter(JSONFormatter())
        else:
            file_handler.setFormatter(
                logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
            )

        root_logger.addHandler(file_handler)
