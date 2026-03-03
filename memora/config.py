"""Memora configuration management.

Loads settings from environment variables and ~/.memora/config.yaml.
Creates the data directory structure on first run.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path.home() / ".memora"
DEFAULT_LLM_MODEL = "gpt-5-nano"

DATA_SUBDIRS = [
    "graph",
    "vectors",
    "models",
    "backups",
    "logs",
]

# Full default config.yaml schema
DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "auto_approve_threshold": 0.85,
    "decay_lambda": {
        "academic": 0.05,
        "professional": 0.03,
        "financial": 0.02,
        "health": 0.05,
        "personal_growth": 0.04,
        "social": 0.07,
        "ventures": 0.03,
    },
    "relationship_decay_thresholds": {
        "close": 7,
        "regular": 14,
        "acquaintance": 30,
    },
    "sm2_default_easiness": 2.5,
    "bridge_similarity_threshold": 0.75,
    "embedding_model": "all-mpnet-base-v2",
    "data_dir": "~/.memora",
    "log_level": "INFO",
}


class Settings(BaseSettings):
    """Application settings loaded from env vars and config file."""

    model_config = SettingsConfigDict(
        env_prefix="MEMORA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API keys
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")

    # Paths
    data_dir: Path = Field(default=DEFAULT_DATA_DIR)

    # Embedding
    embedding_model: str = "all-mpnet-base-v2"

    # Confidence & governance
    auto_approve_threshold: float = Field(default=0.85, ge=0.0, le=1.0)

    # Decay parameters (per-network overrides possible via config.yaml)
    decay_lambda: float = Field(default=0.01, ge=0.0)

    # Per-network decay lambdas
    decay_lambda_overrides: dict[str, float] = Field(default_factory=lambda: {
        "ACADEMIC": 0.05,
        "PROFESSIONAL": 0.03,
        "FINANCIAL": 0.02,
        "HEALTH": 0.05,
        "PERSONAL_GROWTH": 0.04,
        "SOCIAL": 0.07,
        "VENTURES": 0.03,
    })

    # Relationship decay thresholds (days)
    relationship_decay_thresholds: dict[str, int] = Field(default_factory=lambda: {
        "close": 7,
        "regular": 14,
        "acquaintance": 30,
    })

    # Spaced repetition
    sm2_default_easiness: float = Field(default=2.5, ge=1.3)

    # Bridge discovery
    bridge_similarity_threshold: float = Field(default=0.75, ge=0.0, le=1.0)

    # LLM retry settings
    llm_max_retries: int = Field(default=3, ge=0)
    llm_retry_base_delay: float = Field(default=1.0, ge=0.1)
    llm_retry_max_delay: float = Field(default=30.0, ge=1.0)

    # CRAG (Corrective RAG) settings
    crag_relevance_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    crag_min_results: int = Field(default=3, ge=1)
    crag_term_coverage_threshold: float = Field(default=0.3, ge=0.0, le=1.0)

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Connectors
    connectors: dict[str, dict] = Field(default_factory=dict)
    connector_sync_interval_minutes: int = Field(default=60, ge=1)

    @field_validator("data_dir", mode="before")
    @classmethod
    def expand_home(cls, v: str | Path) -> Path:
        return Path(str(v)).expanduser().resolve()

    # ----- derived paths -----

    @property
    def graph_dir(self) -> Path:
        return self.data_dir / "graph"

    @property
    def vector_dir(self) -> Path:
        return self.data_dir / "vectors"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def db_path(self) -> Path:
        return self.graph_dir / "memora.duckdb"

    @property
    def config_yaml_path(self) -> Path:
        return self.data_dir / "config.yaml"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"


def init_data_directory(settings: Settings) -> None:
    """Create the ~/.memora/ directory structure on first run."""
    for subdir in DATA_SUBDIRS:
        path = settings.data_dir / subdir
        path.mkdir(parents=True, exist_ok=True)
        logger.debug("Ensured directory: %s", path)

    # Create default config.yaml if it doesn't exist
    if not settings.config_yaml_path.exists():
        settings.config_yaml_path.write_text(
            yaml.dump(DEFAULT_CONFIG, default_flow_style=False, sort_keys=False)
        )
        logger.info("Created default config at %s", settings.config_yaml_path)


def load_settings() -> Settings:
    """Load settings, merging env vars with config.yaml overrides."""
    settings = Settings()
    init_data_directory(settings)

    # Merge config.yaml overrides if file exists
    if settings.config_yaml_path.exists():
        with open(settings.config_yaml_path) as f:
            yaml_config = yaml.safe_load(f) or {}

        # Apply any top-level overrides from YAML
        if "log_level" in yaml_config:
            settings.log_level = yaml_config["log_level"]
        if "auto_approve_threshold" in yaml_config:
            settings.auto_approve_threshold = yaml_config["auto_approve_threshold"]
        if "decay_lambda" in yaml_config and isinstance(yaml_config["decay_lambda"], (int, float)):
            settings.decay_lambda = yaml_config["decay_lambda"]
        if "decay_lambda" in yaml_config and isinstance(yaml_config["decay_lambda"], dict):
            settings.decay_lambda_overrides = yaml_config["decay_lambda"]
        if "relationship_decay_thresholds" in yaml_config:
            settings.relationship_decay_thresholds = yaml_config["relationship_decay_thresholds"]
        if "sm2_default_easiness" in yaml_config:
            settings.sm2_default_easiness = yaml_config["sm2_default_easiness"]
        if "bridge_similarity_threshold" in yaml_config:
            settings.bridge_similarity_threshold = yaml_config["bridge_similarity_threshold"]
        if "embedding_model" in yaml_config:
            settings.embedding_model = yaml_config["embedding_model"]
        if "connectors" in yaml_config and isinstance(yaml_config["connectors"], dict):
            settings.connectors = yaml_config["connectors"]
        if "connector_sync_interval_minutes" in yaml_config:
            settings.connector_sync_interval_minutes = yaml_config["connector_sync_interval_minutes"]

    # Configure structured logging
    from memora.core.logging_config import configure_logging
    configure_logging(
        log_level=settings.log_level,
        log_dir=settings.log_dir,
        json_format=True,
    )

    return settings
