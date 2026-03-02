"""Networks command — now delegates to stats (which includes network health)."""

from __future__ import annotations

from cli.commands.stats import cmd_stats


def cmd_networks(app):
    cmd_stats(app)
