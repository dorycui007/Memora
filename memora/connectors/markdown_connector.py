"""Markdown Connector — imports notes from .md files with frontmatter.

Watches a directory for .md files, parses frontmatter + content,
detects [[wikilinks]] for RELATED_TO edges and #tags for node tags.
Supports Obsidian vaults out of the box.

Requires: python-frontmatter>=1.0
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from memora.connectors.base import BaseConnector
from memora.graph.models import Capture

logger = logging.getLogger(__name__)

# Patterns
WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
TAG_RE = re.compile(r"(?:^|\s)#([a-zA-Z][a-zA-Z0-9_/-]+)", re.MULTILINE)


class MarkdownConnector(BaseConnector):
    """Import notes from a directory of Markdown files."""

    connector_type = "markdown"

    def __init__(self, name: str, config: dict | None = None) -> None:
        super().__init__(name, config)
        self._root: Path | None = None

    def validate_config(self) -> list[str]:
        errors = []
        if not self.config.get("path"):
            errors.append("Markdown connector requires 'path' in config (directory to watch)")
        return errors

    def connect(self) -> bool:
        """Validate that frontmatter is available and the directory exists."""
        try:
            import frontmatter  # noqa: F401
        except ImportError:
            logger.error(
                "python-frontmatter not installed. Install with: pip install python-frontmatter>=1.0"
            )
            return False

        root = Path(self.config.get("path", "")).expanduser()
        if not root.exists():
            logger.error("Markdown directory does not exist: %s", root)
            return False
        if not root.is_dir():
            logger.error("Markdown path is not a directory: %s", root)
            return False

        self._root = root
        md_count = len(list(root.rglob("*.md")))
        logger.info("Markdown connector: found %d .md files in %s", md_count, root)
        return True

    def get_items(self, since: datetime | None = None) -> list[dict]:
        """Parse .md files from the configured directory."""
        import frontmatter

        if not self._root:
            return []

        # Support configurable file patterns
        patterns = self.config.get("patterns", ["**/*.md"])
        exclude_dirs = set(self.config.get("exclude_dirs", [".obsidian", ".trash", "node_modules"]))

        items = []
        for pattern in patterns:
            for md_path in self._root.glob(pattern):
                # Skip excluded directories
                if any(part in exclude_dirs for part in md_path.parts):
                    continue

                # Check modification time
                if since:
                    mtime = datetime.fromtimestamp(md_path.stat().st_mtime, tz=timezone.utc)
                    if mtime < since:
                        continue

                try:
                    post = frontmatter.load(str(md_path))
                    content = post.content
                    metadata = dict(post.metadata)

                    # Extract wikilinks
                    wikilinks = WIKILINK_RE.findall(content)

                    # Extract tags from content and frontmatter
                    content_tags = TAG_RE.findall(content)
                    fm_tags = metadata.get("tags", [])
                    if isinstance(fm_tags, str):
                        fm_tags = [t.strip() for t in fm_tags.split(",")]
                    all_tags = list(set(content_tags + fm_tags))

                    # Determine title from frontmatter or filename
                    title = metadata.get("title", md_path.stem)

                    items.append({
                        "path": str(md_path),
                        "relative_path": str(md_path.relative_to(self._root)),
                        "title": title,
                        "content": content,
                        "frontmatter": metadata,
                        "wikilinks": wikilinks,
                        "tags": all_tags,
                        "modified": datetime.fromtimestamp(
                            md_path.stat().st_mtime, tz=timezone.utc
                        ).isoformat(),
                    })

                except Exception as e:
                    logger.warning("Failed to parse %s: %s", md_path, e)

        logger.info("Extracted %d markdown file(s)", len(items))
        return items

    def transform(self, raw_items: list[dict]) -> list[Capture]:
        """Transform markdown files into Capture objects."""
        captures = []
        for item in raw_items:
            title = item["title"]
            content = item["content"]
            wikilinks = item.get("wikilinks", [])
            tags = item.get("tags", [])
            frontmatter_data = item.get("frontmatter", {})

            # Build rich content for the capture
            content_parts = [f"Note: {title}"]

            # Include frontmatter context
            if frontmatter_data.get("date"):
                content_parts.append(f"Date: {frontmatter_data['date']}")
            if frontmatter_data.get("category"):
                content_parts.append(f"Category: {frontmatter_data['category']}")
            if frontmatter_data.get("type"):
                content_parts.append(f"Type: {frontmatter_data['type']}")

            if tags:
                content_parts.append(f"Tags: {', '.join(tags)}")
            if wikilinks:
                content_parts.append(f"Links to: {', '.join(wikilinks)}")

            content_parts.append(f"\n{content}")

            raw_content = "\n".join(content_parts)
            content_hash = hashlib.sha256(raw_content.encode()).hexdigest()

            capture = Capture(
                id=uuid4(),
                modality="text",
                raw_content=raw_content,
                processed_content="",
                content_hash=content_hash,
                language="en",
                metadata={
                    "source": "markdown_connector",
                    "connector_name": self.name,
                    "file_path": item["path"],
                    "relative_path": item.get("relative_path", ""),
                    "title": title,
                    "wikilinks": wikilinks,
                    "tags": tags,
                    "frontmatter": frontmatter_data,
                    "modified": item.get("modified", ""),
                },
                created_at=datetime.now(timezone.utc),
            )
            captures.append(capture)

        return captures
