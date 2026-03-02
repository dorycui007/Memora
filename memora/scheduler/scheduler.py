"""APScheduler Setup — background job scheduler for the living graph engine."""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from memora.scheduler.jobs import (
    run_bridge_discovery_batch,
    run_commitment_scan,
    run_daily_briefing,
    run_decay_scoring,
    run_gap_detection,
    run_network_health,
    run_outcome_review,
    run_pattern_detection,
    run_relationship_decay,
    run_spaced_repetition_queue,
)

logger = logging.getLogger(__name__)


class MemoraScheduler:
    """Manage background jobs for the Memora living graph engine.

    Wraps an APScheduler ``AsyncIOScheduler`` and registers all recurring
    jobs defined in :mod:`memora.scheduler.jobs`.
    """

    def __init__(
        self,
        repo,
        app_state=None,
        vector_store=None,
        embedding_engine=None,
        truth_layer=None,
        settings=None,
    ) -> None:
        self._repo = repo
        self._app_state = app_state
        self._vector_store = vector_store
        self._embedding_engine = embedding_engine
        self._truth_layer = truth_layer
        self._settings = settings

        self._scheduler = AsyncIOScheduler(
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 3600,  # 1 hour grace period
            },
        )

    # ── Lazy dependency resolution ─────────────────────────────────

    def _resolve(self, attr: str):
        """Resolve a dependency, falling back to app_state for lazy-init deps."""
        val = getattr(self, f"_{attr}", None)
        if val is not None:
            return val
        if self._app_state is not None:
            return getattr(self._app_state, attr, None)
        return None

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the scheduler and register all recurring jobs."""
        self._register_jobs()
        self._scheduler.start()
        logger.info("MemoraScheduler started with %d jobs", len(self._scheduler.get_jobs()))

    def shutdown(self) -> None:
        """Gracefully shut down the scheduler, waiting for running jobs."""
        try:
            self._scheduler.shutdown(wait=True)
            logger.info("MemoraScheduler shut down gracefully")
        except Exception:
            logger.error("Error during scheduler shutdown", exc_info=True)

    # ── Job Registration ─────────────────────────────────────────────

    def _register_jobs(self) -> None:
        """Register all background jobs with their schedules."""

        # Decay scoring — daily at 2:00 AM
        self._scheduler.add_job(
            run_decay_scoring,
            trigger=CronTrigger(hour=2, minute=0),
            kwargs={"repo": self._repo, "settings": self._settings},
            id="decay_scoring",
            name="Decay Scoring",
            replace_existing=True,
        )

        # Bridge discovery batch — daily at 3:00 AM
        # Use a wrapper to resolve lazy-init dependencies at runtime
        async def _bridge_discovery_wrapper():
            await run_bridge_discovery_batch(
                repo=self._repo,
                vector_store=self._resolve("vector_store"),
                embedding_engine=self._resolve("embedding_engine"),
            )

        self._scheduler.add_job(
            _bridge_discovery_wrapper,
            trigger=CronTrigger(hour=3, minute=0),
            id="bridge_discovery_batch",
            name="Bridge Discovery Batch",
            replace_existing=True,
        )

        # Network health — every 6 hours
        self._scheduler.add_job(
            run_network_health,
            trigger=IntervalTrigger(hours=6),
            kwargs={"repo": self._repo},
            id="network_health",
            name="Network Health",
            replace_existing=True,
        )

        # Commitment scan — daily at 6:00 AM
        self._scheduler.add_job(
            run_commitment_scan,
            trigger=CronTrigger(hour=6, minute=0),
            kwargs={"repo": self._repo},
            id="commitment_scan",
            name="Commitment Scan",
            replace_existing=True,
        )

        # Relationship decay — weekly Sunday at midnight
        self._scheduler.add_job(
            run_relationship_decay,
            trigger=CronTrigger(day_of_week="sun", hour=0, minute=0),
            kwargs={"repo": self._repo},
            id="relationship_decay",
            name="Relationship Decay",
            replace_existing=True,
        )

        # Spaced repetition — daily at 5:00 AM
        self._scheduler.add_job(
            run_spaced_repetition_queue,
            trigger=CronTrigger(hour=5, minute=0),
            kwargs={"repo": self._repo},
            id="spaced_repetition",
            name="Spaced Repetition Queue",
            replace_existing=True,
        )

        # Gap detection — weekly Sunday at 1:00 AM
        self._scheduler.add_job(
            run_gap_detection,
            trigger=CronTrigger(day_of_week="sun", hour=1, minute=0),
            kwargs={"repo": self._repo},
            id="gap_detection",
            name="Gap Detection",
            replace_existing=True,
        )

        # Daily briefing — daily at 7:00 AM
        async def _daily_briefing_wrapper():
            await run_daily_briefing(
                repo=self._repo,
                vector_store=self._resolve("vector_store"),
                embedding_engine=self._resolve("embedding_engine"),
                truth_layer=self._resolve("truth_layer"),
                settings=self._settings,
            )

        self._scheduler.add_job(
            _daily_briefing_wrapper,
            trigger=CronTrigger(hour=7, minute=0),
            id="daily_briefing",
            name="Daily Briefing",
            replace_existing=True,
        )

        # Pattern detection — daily at 4:00 AM
        self._scheduler.add_job(
            run_pattern_detection,
            trigger=CronTrigger(hour=4, minute=0),
            kwargs={"repo": self._repo},
            id="pattern_detection",
            name="Pattern Detection",
            replace_existing=True,
        )

        # Outcome review — daily at 6:30 AM
        self._scheduler.add_job(
            run_outcome_review,
            trigger=CronTrigger(hour=6, minute=30),
            kwargs={"repo": self._repo},
            id="outcome_review",
            name="Outcome Review",
            replace_existing=True,
        )

        logger.info("Registered %d scheduled jobs", len(self._scheduler.get_jobs()))
