"""Memora 2.0 server entry point.

Boots the FastAPI server with all dependencies.
Usage: python serve.py
"""

from __future__ import annotations

import sys


def main() -> None:
    """Start the Memora server."""
    import uvicorn

    from memora.config import load_settings

    settings = load_settings()

    print(f"\n  Memora 2.0 — Strategic Intelligence Platform")
    print(f"  Dashboard: http://{settings.api_host}:{settings.api_port}")
    print(f"  API:       http://{settings.api_host}:{settings.api_port}/api")
    print(f"  Docs:      http://{settings.api_host}:{settings.api_port}/docs\n")

    uvicorn.run(
        "memora.api.server:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
