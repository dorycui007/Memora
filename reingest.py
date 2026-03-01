#!/usr/bin/env python3
"""Re-ingest saved captures through the updated pipeline.

Reads captures from /tmp/memora_captures.json and runs each through
the full extraction pipeline sequentially.
"""

import asyncio
import hashlib
import json
import os
import sys
import time
import logging
from pathlib import Path

# Suppress noisy logs
os.environ.setdefault("MEMORA_LOG_LEVEL", "WARNING")
for name in [
    "sentence_transformers", "httpx", "huggingface_hub",
    "transformers", "torch", "tqdm",
    "memora.vector.embeddings", "memora.vector.store",
]:
    logging.getLogger(name).setLevel(logging.ERROR)
os.environ["TQDM_DISABLE"] = "1"

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from memora.config import load_settings
from memora.graph.repository import GraphRepository
from memora.graph.models import Capture
from memora.core.pipeline import ExtractionPipeline, PipelineStage, STAGE_NAMES
from memora.vector.embeddings import EmbeddingEngine
from memora.vector.store import VectorStore


def main():
    # Load captures
    with open("/tmp/memora_captures.json") as f:
        captures = json.load(f)

    print(f"\n  Loading {len(captures)} captures for re-ingestion...\n")

    # Init
    settings = load_settings()
    repo = GraphRepository(db_path=settings.db_path)

    if not settings.openai_api_key or settings.openai_api_key.startswith("sk-PASTE"):
        print("  ERROR: No valid OPENAI_API_KEY in .env")
        return

    print("  Initializing embedding engine...")
    embedding_engine = EmbeddingEngine(
        model_name=settings.embedding_model,
        cache_dir=settings.models_dir,
    )

    print("  Initializing vector store...")
    vector_store = VectorStore(db_path=settings.vector_dir)

    print("  Initializing pipeline...")
    pipeline = ExtractionPipeline(
        repo=repo,
        settings=settings,
        vector_store=vector_store,
        embedding_engine=embedding_engine,
    )

    print("  Ready.\n")
    print("=" * 70)

    succeeded = 0
    failed = 0

    for i, cap in enumerate(captures, 1):
        text = cap["raw_content"]
        preview = text[:70].replace("\n", " ")
        print(f"\n  [{i}/{len(captures)}] {preview}...")

        # Create capture record
        content_hash = hashlib.sha256(text.encode()).hexdigest()

        if repo.check_capture_exists(content_hash):
            print(f"    SKIP (duplicate content hash)")
            continue

        capture = Capture(
            modality="text",
            raw_content=text,
            content_hash=content_hash,
        )
        cid = repo.create_capture(capture)

        # Track stages
        stage_status = {}

        def on_stage(stage, status):
            stage_status[stage] = status
            name = STAGE_NAMES.get(stage, stage.name)
            icon = {"running": ">", "done": "+", "failed": "x", "skipped": "-"}.get(status, " ")
            if status == "running":
                print(f"    {icon} {name}...", end="", flush=True)
            elif status == "done":
                print(f" done")
            elif status == "failed":
                print(f" FAILED")

        t0 = time.time()
        try:
            state = asyncio.run(pipeline.run(str(cid), text, on_stage=on_stage))

            elapsed = time.time() - t0

            if state.error:
                print(f"    ERROR: {state.error}")
                failed += 1
            elif state.clarification_needed:
                print(f"    CLARIFICATION NEEDED: {state.clarification_message}")
                failed += 1
            else:
                p = state.proposal
                nodes_created = len(p.nodes_to_create) if p else 0
                edges_created = len(p.edges_to_create) if p else 0
                conf = f"{p.confidence:.0%}" if p else "?"
                route = state.route.value if state.route else "?"
                print(f"    OK ({elapsed:.1f}s) — {nodes_created} nodes, "
                      f"{edges_created} edges, conf={conf}, route={route}")

                # Auto-approve if awaiting review
                if state.proposal_id and state.status == "awaiting_review":
                    from uuid import UUID
                    from memora.graph.models import ProposalStatus
                    pid = UUID(state.proposal_id)
                    repo.update_proposal_status(pid, ProposalStatus.APPROVED, reviewer="reingest")
                    success = repo.commit_proposal(pid)
                    if success:
                        print(f"    AUTO-APPROVED and committed")
                        # Run post-commit manually
                        state.route = state.route  # keep as-is
                    else:
                        print(f"    AUTO-APPROVE commit failed")
                        failed += 1
                        continue

                succeeded += 1

        except Exception as e:
            elapsed = time.time() - t0
            print(f"    EXCEPTION ({elapsed:.1f}s): {e}")
            failed += 1

    print(f"\n{'=' * 70}")
    print(f"\n  Re-ingestion complete!")
    print(f"  Succeeded: {succeeded}")
    print(f"  Failed:    {failed}")

    # Final stats
    stats = repo.get_graph_stats()
    print(f"\n  Final graph: {stats['node_count']} nodes, {stats['edge_count']} edges")
    print(f"  Types: {stats.get('type_breakdown', {})}")
    print()

    repo.close()


if __name__ == "__main__":
    main()
