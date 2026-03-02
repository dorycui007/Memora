"""ANSI colors, box drawing, sparklines, and terminal rendering helpers.

Palantir Gotham-inspired design system with 256-color palette.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import sys
import textwrap
import time
from datetime import datetime, timezone, timedelta

EST = timezone(timedelta(hours=-5))


class C:
    """ANSI color codes — Palantir-inspired 256-color palette."""
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM_ATTR = "\033[2m"
    ITALIC  = "\033[3m"
    UNDER   = "\033[4m"

    # Legacy standard colors (kept for backward compat in subcommands)
    BLACK   = "\033[30m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"

    BG_BLACK   = "\033[40m"
    BG_RED     = "\033[41m"
    BG_GREEN   = "\033[42m"
    BG_YELLOW  = "\033[43m"
    BG_BLUE    = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN    = "\033[46m"
    BG_WHITE   = "\033[47m"

    # Legacy 256-color extras
    ORANGE  = "\033[38;5;208m"
    PINK    = "\033[38;5;213m"
    TEAL    = "\033[38;5;30m"
    GRAY    = "\033[38;5;245m"
    LGRAY   = "\033[38;5;250m"

    # ── Palantir Primary Palette ──────────────────────────────────
    BASE    = "\033[38;5;253m"   # #DADADA  Light silver text
    FRAME   = "\033[38;5;240m"   # #585858  Dim borders, dividers
    ACCENT  = "\033[38;5;39m"    # #00AFFF  Primary cyan — active UI
    SIGNAL  = "\033[38;5;214m"   # #FFAF00  Amber gold — alerts, counts
    CONFIRM = "\033[38;5;84m"    # #5FD700  Green — healthy, approved

    # ── Semantic Accents ──────────────────────────────────────────
    DANGER  = "\033[38;5;196m"   # #FF0000  Critical alerts
    WARM    = "\033[38;5;215m"   # #FFAF5F  Pending, in-progress
    INTEL   = "\033[38;5;183m"   # #D7AFFF  Soft violet — AI outputs
    DIM     = "\033[38;5;243m"   # #767676  Descriptions, metadata
    GHOST   = "\033[38;5;236m"   # #303030  Subtle backgrounds


def term_width() -> int:
    return shutil.get_terminal_size((80, 24)).columns


# ── Health color helper ───────────────────────────────────────────

def health_color(score: float) -> str:
    """Return ANSI color code based on health score."""
    if score >= 0.75:
        return C.CONFIRM
    elif score >= 0.50:
        return C.SIGNAL
    else:
        return C.DANGER


def health_bar(score: float, width: int = 20) -> str:
    """Render a health bar with dynamic color."""
    color = health_color(score)
    filled = int(score * width)
    empty = width - filled
    return f"{color}{'█' * filled}{C.GHOST}{'░' * empty}{C.RESET}"


def momentum_arrow(score: float, prev_score: float | None = None) -> str:
    """Return colored momentum indicator."""
    if prev_score is None:
        return f"{C.DIM}─{C.RESET}"
    diff = score - prev_score
    if diff > 0.02:
        return f"{C.CONFIRM}▲{C.RESET}"
    elif diff < -0.02:
        color = C.DANGER if score < 0.50 else C.SIGNAL
        return f"{color}▼{C.RESET}"
    return f"{C.DIM}─{C.RESET}"


# ── Network abbreviations ────────────────────────────────────────

NETWORK_ABBREV = {
    "ACADEMIC": "ACAD",
    "PROFESSIONAL": "PROF",
    "FINANCIAL": "FINC",
    "HEALTH": "HLTH",
    "PERSONAL_GROWTH": "GROW",
    "SOCIAL": "SOCL",
    "VENTURES": "VNTR",
}

NETWORK_ABBREV_SHORT = {
    "ACADEMIC": "A",
    "PROFESSIONAL": "P",
    "FINANCIAL": "F",
    "HEALTH": "H",
    "PERSONAL_GROWTH": "G",
    "SOCIAL": "S",
    "VENTURES": "V",
}


# ── Boot Sequence ─────────────────────────────────────────────────

MEMORA_LOGO = f"""\
{C.ACCENT}{C.BOLD}  ███╗   ███╗ ███████╗ ███╗   ███╗  ██████╗  ██████╗   █████╗
  ████╗ ████║ ██╔════╝ ████╗ ████║ ██╔═══██╗ ██╔══██╗ ██╔══██╗
  ██╔████╔██║ █████╗   ██╔████╔██║ ██║   ██║ ██████╔╝ ███████║
  ██║╚██╔╝██║ ██╔══╝   ██║╚██╔╝██║ ██║   ██║ ██╔══██╗ ██╔══██║
  ██║ ╚═╝ ██║ ███████╗ ██║ ╚═╝ ██║ ╚██████╔╝ ██║  ██║ ██║  ██║
  ╚═╝     ╚═╝ ╚══════╝ ╚═╝     ╚═╝  ╚═════╝  ╚═╝  ╚═╝ ╚═╝  ╚═╝{C.RESET}"""


def boot_sequence(subsystem_status: dict[str, str] | None = None):
    """Staged boot reveal with subsystem telemetry."""
    delay = 0.08

    # Top bar
    bar = "▄" * 64
    print(f"\n {C.ACCENT}{bar}{C.RESET}")
    time.sleep(delay)

    # Logo
    print(MEMORA_LOGO)
    time.sleep(delay)

    # Tagline
    print(f"\n  {C.DIM}P E R S O N A L   I N T E L L I G E N C E   P L A T F O R M{C.RESET}")
    time.sleep(delay)

    # Bottom bar
    bar_bottom = "▀" * 64
    print(f"\n {C.ACCENT}{bar_bottom}{C.RESET}")
    time.sleep(delay)

    # Subsystem init
    if subsystem_status is None:
        subsystem_status = {}

    subsystems = [
        ("Graph engine", subsystem_status.get("graph", "ONLINE")),
        ("Vector store", subsystem_status.get("vector", "ONLINE")),
        ("Embedding engine", subsystem_status.get("embedding", "STANDBY")),
        ("AI council", subsystem_status.get("council", "ONLINE")),
        ("Scheduler", subsystem_status.get("scheduler", "ONLINE")),
    ]

    print(f"\n  {C.BASE}⣿ Initializing subsystems...{C.RESET}")
    time.sleep(delay)

    for i, (name, status) in enumerate(subsystems):
        connector = "└──" if i == len(subsystems) - 1 else "├──"
        dots = "·" * (40 - len(name))
        if status == "ONLINE":
            status_color = C.CONFIRM
        elif status == "STANDBY":
            status_color = C.SIGNAL
        else:
            status_color = C.DANGER

        print(f"  {C.FRAME}{connector}{C.RESET} {C.BASE}{name}{C.RESET} {C.DIM}{dots}{C.RESET} {status_color}{status}{C.RESET}")
        time.sleep(delay)

    print(f"\n  {C.CONFIRM}⣿ Session ready.{C.RESET}\n")


# ── Command Deck (Main Menu) ─────────────────────────────────────

def _format_count(n: int) -> str:
    """Format number with commas."""
    if n >= 1000:
        return f"{n:,}"
    return str(n)


def _session_id() -> str:
    """Generate a pseudo-random session ID from timestamp."""
    h = hashlib.md5(str(time.time()).encode()).hexdigest()[:3]
    return f"0x{h}"


def _operator_id() -> str:
    """Generate a pseudo-random operator identity hash."""
    h = hashlib.md5(str(id(C)).encode()).hexdigest()[:4]
    return f"#{h}"


def command_deck(
    operator_name: str = "",
    node_count: int = 0,
    edge_count: int = 0,
    density: float = 0.0,
    network_health: dict[str, float] | None = None,
    pending_proposals: int = 0,
    alert_count: int = 0,
    pending_count: int = 0,
):
    """Render the main command deck menu — flat, dense, ~18 lines."""
    A = C.ACCENT
    B = C.BASE
    D = C.DIM
    S = C.SIGNAL
    G = C.GHOST
    R = C.RESET

    w = term_width()
    is_wide = w >= 80

    now = datetime.now(EST)
    date_str = now.strftime("%d %b %Y").upper()
    time_str = now.strftime("%I:%M %p EST")

    # Header
    header_right = f"{D}{date_str} {A}◆{R} {D}{time_str}{R}"
    header_right_vis = len(date_str) + 3 + len(time_str)
    header_left = f"{A}{C.BOLD}M E M O R A{R}"
    header_left_vis = 11
    content_w = min(w - 4, 76)
    gap = content_w - header_left_vis - header_right_vis
    if gap < 1:
        gap = 1
    print(f"\n  {header_left}{' ' * gap}{header_right}")

    # Dashed separator
    dashes = "─ " * (content_w // 2)
    print(f"  {G}{dashes[:content_w]}{R}")

    # Operator + stats line
    op_name = operator_name or "Unknown"
    nodes_str = _format_count(node_count)
    edges_str = _format_count(edge_count)
    print(f"  {D}Operator{R}  {B}{C.BOLD}{op_name}{R}"
          f"{'  ' * 3}{D}Nodes{R} {B}{C.BOLD}{nodes_str}{R}"
          f"  {D}Edges{R} {B}{C.BOLD}{edges_str}{R}")

    # Proposals label
    proposals_extra = f" {S}{C.BOLD}({pending_proposals}){R}" if pending_proposals > 0 else ""

    # Command groups — flat layout
    groups = [
        ("INGEST", [("c", "Capture"), ("p", "Profile"), ("r", f"Proposals{proposals_extra}")]),
        ("QUERY", [("d", "Dossier"), ("i", "Investigate"), ("w", "Browse")]),
        ("INTEL", [("b", "Briefing"), ("k", "Critique"), ("u", "Council")]),
        ("ANALYSIS", [("t", "Timeline"), ("o", "Outcomes"), ("a", "Patterns"), ("g", "Stats")]),
        ("NETWORK", [("n", "Networks"), ("e", "People"), ("j", "Actions")]),
        ("SYSTEM", [("0", "Settings"), ("x", "Clear data"), ("q", "Quit")]),
    ]

    if is_wide:
        # 3-column layout
        col_w = content_w // 3
        rows = [(groups[0], groups[1], groups[2]),
                (groups[3], groups[4], groups[5])]
        for row in rows:
            print()
            # Group headers
            parts = []
            for name, _ in row:
                parts.append(f"{A}{C.BOLD}{name}{R}")
            _print_columns(parts, col_w)
            # Command items — find max items in row
            max_items = max(len(items) for _, items in row)
            for i in range(max_items):
                parts = []
                for _, items in row:
                    if i < len(items):
                        key, label = items[i]
                        parts.append(f"{A}{C.BOLD}[{key}]{R} {B}{label}{R}")
                    else:
                        parts.append("")
                _print_columns(parts, col_w)
    else:
        # 2-column layout
        rows = [(groups[0], groups[1]),
                (groups[2], groups[3]),
                (groups[4], groups[5])]
        col_w = content_w // 2
        for row in rows:
            print()
            parts = []
            for name, _ in row:
                parts.append(f"{A}{C.BOLD}{name}{R}")
            _print_columns(parts, col_w)
            max_items = max(len(items) for _, items in row)
            for i in range(max_items):
                parts = []
                for _, items in row:
                    if i < len(items):
                        key, label = items[i]
                        parts.append(f"{A}{C.BOLD}[{key}]{R} {B}{label}{R}")
                    else:
                        parts.append("")
                _print_columns(parts, col_w)

    # Telemetry — single inline line
    print()
    if network_health:
        parts = []
        for net_name in ["ACADEMIC", "PROFESSIONAL", "FINANCIAL", "HEALTH",
                         "PERSONAL_GROWTH", "SOCIAL", "VENTURES"]:
            score = network_health.get(net_name, 0.0)
            abbr = NETWORK_ABBREV_SHORT.get(net_name, "?")
            color = health_color(score)
            parts.append(f"{color}◉{R} {B}{abbr}:{score:.2f}{R}")
        telem = "  ".join(parts)
        extras = ""
        if alert_count > 0:
            extras += f"   {S}▲{alert_count}{R}"
        if pending_count > 0:
            extras += f" {A}◆{pending_count}{R}"
        print(f"  {telem}{extras}")
    else:
        print(f"  {D}No telemetry data{R}")

    # No prompt here — actual input happens via prompt() call in app.py


def _print_columns(parts: list[str], col_w: int):
    """Print ANSI-colored strings in fixed-width columns."""
    R = C.RESET
    line = "  "
    for part in parts:
        vis = _visible_len(part)
        pad = col_w - vis
        if pad < 0:
            pad = 0
        line += part + " " * pad
    print(line)


def telemetry_bar(
    network_health: dict[str, float] | None = None,
    node_count: int = 0,
    edge_count: int = 0,
    density: float = 0.0,
    alert_count: int = 0,
    pending_count: int = 0,
    frame_fn=None,
):
    """Render the telemetry section with health bars."""
    D = C.DIM
    B = C.BASE
    S = C.SIGNAL
    A = C.ACCENT
    R = C.RESET

    def out(line):
        if frame_fn:
            print(frame_fn(line))
        else:
            print(f"   {line}")

    out(f"{D}{C.BOLD}TELEMETRY{R}")

    if network_health:
        # Render in 3-column rows
        nets = ["ACADEMIC", "PROFESSIONAL", "FINANCIAL", "HEALTH",
                "PERSONAL_GROWTH", "SOCIAL", "VENTURES"]
        items = []
        for net_name in nets:
            score = network_health.get(net_name, 0.0)
            abbr = NETWORK_ABBREV.get(net_name, net_name[:4])
            color = health_color(score)
            bar = health_bar(score, 10)
            items.append(f"{color}◉{R} {B}{abbr}{R}  {bar}  {color}{score:.2f}{R}")

        # Print in rows of 3
        for i in range(0, len(items), 3):
            row = items[i:i + 3]
            out("  ".join(row))
    else:
        out(f"{D}No network health data available{R}")

    out("")

    # Stats line
    nodes_str = _format_count(node_count)
    edges_str = _format_count(edge_count)
    stats_line = (f"{D}Nodes{R}  {B}{C.BOLD}{nodes_str}{R}    "
                  f"{D}Edges{R}  {B}{C.BOLD}{edges_str}{R}    "
                  f"{D}Density{R}  {B}{C.BOLD}{density:.3f}{R}")

    if alert_count > 0:
        stats_line += f"     {S}▲ {alert_count} alerts{R}"
    if pending_count > 0:
        stats_line += f"   {A}◆ {pending_count} pending{R}"

    out(stats_line)
    out("")


# ── Subcommand Headers ────────────────────────────────────────────

def subcommand_header(
    title: str,
    symbol: str = "◇",
    color: str = C.ACCENT,
    taglines: list[str] | None = None,
    border: str = "simple",
    metadata: dict[str, str] | None = None,
):
    """Render a themed subcommand header card.

    border: 'double' for ╔═╗ style, 'simple' for underline style
    """
    R = C.RESET
    D = C.DIM
    G = C.GHOST

    spaced_title = " ".join(title.upper())

    if border == "double":
        w = max(54, len(spaced_title) + 14)
        inner = w - 4

        print(f"\n {color}╔{'═' * (w - 2)}╗{R}")
        print(f" {color}║{R}{' ' * inner}  {color}║{R}")

        title_line = f"    {color}{symbol}{R}  {color}{C.BOLD}{spaced_title}{R}"
        title_vis = 6 + len(spaced_title)
        print(f" {color}║{R}{title_line}{' ' * (inner - title_vis)}  {color}║{R}")

        # Underline
        uline = "─" * (len(spaced_title) + 2)
        print(f" {color}║{R}    {G}{uline}{R}{' ' * (inner - len(uline) - 4)}  {color}║{R}")

        # Taglines
        if taglines:
            for tag in taglines:
                tag_line = f"    {D}{tag}{R}"
                tag_vis = 4 + len(tag)
                print(f" {color}║{R}{tag_line}{' ' * (inner - tag_vis)}  {color}║{R}")

        # Metadata
        if metadata:
            for label, value in metadata.items():
                meta_line = f"    {D}{label}{R}   {C.BASE}{value}{R}"
                meta_vis = 4 + len(label) + 3 + len(value)
                print(f" {color}║{R}{meta_line}{' ' * (inner - meta_vis)}  {color}║{R}")

        print(f" {color}║{R}{' ' * inner}  {color}║{R}")
        print(f" {color}╚{'═' * (w - 2)}╝{R}")

    else:  # simple
        print(f"\n    {color}{symbol}{R}  {color}{C.BOLD}{spaced_title}{R}")
        uline = "═" * (len(spaced_title) + 4)
        print(f"    {uline}")

        if taglines:
            for tag in taglines:
                print(f"    {D}{tag}{R}")

        if metadata:
            for label, value in metadata.items():
                print(f"    {D}{label}{R}   {C.BASE}{value}{R}")
        print()


def council_header():
    """Render the compact council agent-tree header."""
    I = C.INTEL
    A = C.ACCENT
    D = C.DIM
    F = C.FRAME
    R = C.RESET

    print(f"\n    {A}{C.BOLD}C O U N C I L{R}")
    print(f"    ═════════════════")
    print(f"    {I}ARCHIVIST{R} {F}─┬─{R} {I}STRATEGIST{R} {F}─┬─{R} {I}RESEARCHER{R}")
    print(f"              {F}└──────{R} {A}{C.BOLD}▼{R} {F}──────┘{R}")
    print(f"    {D}Multi-agent deliberation · Confidence scoring · Citations{R}")
    print()


def briefing_header(operator_name: str = ""):
    """Render the daily situation report header."""
    now = datetime.now(EST)
    date_str = now.strftime("%d %b %Y").upper()
    time_str = now.strftime("%I:%M %p EST")

    subcommand_header(
        title="DAILY SITUATION REPORT",
        symbol="◈",
        color=C.ACCENT,
        taglines=[],
        border="double",
        metadata={
            "Classification": "PERSONAL // UNCLASSIFIED",
            "Prepared": f"{date_str}   {time_str}",
            "Operator": operator_name or "Unknown",
        },
    )


def timeline_header():
    """Render the timeline header with sparkline."""
    A = C.ACCENT
    F = C.FRAME
    D = C.DIM
    R = C.RESET

    print(f"\n    {C.CONFIRM}▣{R}  {A}{C.BOLD}T I M E L I N E{R}")
    print(f"    ═══════════════════")
    print()
    print(f"    {F}──{A}●{F}────────{A}●{F}──────{A}●{F}───────{A}●{F}────{A}●{F}────{A}●{F}──────{A}●{F}──── {A}▶{R}")
    print()


def networks_header():
    """Render the network health header."""
    print(f"\n    {C.CONFIRM}◉{C.RESET}  {C.ACCENT}{C.BOLD}N E T W O R K   H E A L T H{C.RESET}")
    print(f"    ═══════════════════════════")
    print()


# ── Goodbye Card ──────────────────────────────────────────────────

def goodbye_card():
    """Minimal exit card."""
    A = C.ACCENT
    B = C.BASE
    D = C.DIM
    R = C.RESET

    print(f"""
 {A}╔═══════════════════════════════════════════╗{R}
 {A}║{R}                                           {A}║{R}
 {A}║{R}   {B}Session terminated.{R}                     {A}║{R}
 {A}║{R}   {D}Knowledge persists. See you next time.{R}  {A}║{R}
 {A}║{R}                                           {A}║{R}
 {A}╚═══════════════════════════════════════════╝{R}
""")


# ── Progress Steps ────────────────────────────────────────────────

def progress_step(name: str, done: bool = False, in_progress: bool = False):
    """Render a single progress step in the boot/briefing tree."""
    F = C.FRAME
    D = C.DIM
    R = C.RESET

    dots = "·" * (40 - len(name))
    if done:
        status = f"{C.CONFIRM}✓{R}"
    elif in_progress:
        status = f"{C.SIGNAL}◌{R}"
    else:
        status = f"{D}…{R}"

    print(f"    {F}├──{R} {name} {D}{dots}{R} {status}")


def progress_step_last(name: str, done: bool = False, in_progress: bool = False):
    """Render the last progress step."""
    F = C.FRAME
    D = C.DIM
    R = C.RESET

    dots = "·" * (40 - len(name))
    if done:
        status = f"{C.CONFIRM}✓{R}"
    elif in_progress:
        status = f"{C.SIGNAL}◌{R}"
    else:
        status = f"{D}…{R}"

    print(f"    {F}└──{R} {name} {D}{dots}{R} {status}")


# ── Legacy Compat ─────────────────────────────────────────────────

BANNER = ""  # Replaced by boot_sequence()

BRAIN_ART = ""  # No longer used

NETWORK_ICONS = {
    "ACADEMIC":        f"{C.ACCENT}[A]{C.RESET}",
    "PROFESSIONAL":    f"{C.ACCENT}[P]{C.RESET}",
    "FINANCIAL":       f"{C.CONFIRM}[$]{C.RESET}",
    "HEALTH":          f"{C.DANGER}[H]{C.RESET}",
    "PERSONAL_GROWTH": f"{C.INTEL}[G]{C.RESET}",
    "SOCIAL":          f"{C.SIGNAL}[S]{C.RESET}",
    "VENTURES":        f"{C.WARM}[V]{C.RESET}",
}

NODE_ICONS = {
    "EVENT":           f"{C.SIGNAL}*{C.RESET}",
    "PERSON":          f"{C.ACCENT}@{C.RESET}",
    "COMMITMENT":      f"{C.DANGER}!{C.RESET}",
    "DECISION":        f"{C.CONFIRM}?{C.RESET}",
    "GOAL":            f"{C.INTEL}>{C.RESET}",
    "FINANCIAL_ITEM":  f"{C.CONFIRM}${C.RESET}",
    "NOTE":            f"{C.DIM}#{C.RESET}",
    "IDEA":            f"{C.WARM}~{C.RESET}",
    "PROJECT":         f"{C.ACCENT}P{C.RESET}",
    "CONCEPT":         f"{C.INTEL}C{C.RESET}",
    "REFERENCE":       f"{C.DIM}R{C.RESET}",
    "INSIGHT":         f"{C.SIGNAL}!{C.RESET}",
}

DOSSIER_CONFIG = {
    "title_search_limit": 10,
    "semantic_min_score": 0.50,
    "related_min_score": 0.70,
    "connection_min_strength": 0.55,
    "facts_limit": 20,
    "neighborhood_hops": 2,
}


def print_banner():
    """Legacy — replaced by boot_sequence()."""
    pass


# ── Profile Card System ──────────────────────────────────────────


def _get_initials(name: str) -> str:
    """Extract 2-char initials from a name."""
    parts = name.strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    elif parts:
        return parts[0][:2].upper()
    return "??"


def _render_avatar(initials: str) -> list[str]:
    """Return 6 lines of the head-and-shoulders ASCII avatar."""
    i = initials[:2].center(2)
    return [
        "┌──────────┐",
        "│   ╭──╮   │",
        f"│   │{i}│   │",
        "│   ╰┬─╯   │",
        "│  ╭─┴──╮  │",
        "│ ─┤    ├─ │",
        "└──────────┘",
    ]


def render_profile_card(
    name: str,
    fields: list[tuple[str, str]],
    confidence: float | None = None,
    decay: float | None = None,
    bio: str = "",
    summary_lines: list[str] | None = None,
    symbol: str = "◆",
):
    """Full dossier-style profile card with avatar and double border."""
    R = C.RESET
    A = C.ACCENT
    D = C.DIM
    B = C.BASE
    F = C.FRAME
    G = C.GHOST

    w = min(term_width() - 2, 72)
    inner = w - 6  # space inside ║ ... ║ with padding

    initials = _get_initials(name)
    avatar = _render_avatar(initials)
    avatar_w = 12  # visible width of avatar lines

    display_name = name.upper()

    # Build right-side info lines (beside the avatar)
    info_lines: list[str] = []
    info_lines_vis: list[int] = []

    # Name line
    nl = f"{A}{symbol}{R}  {A}{C.BOLD}{display_name}{R}"
    nl_vis = 3 + len(display_name)
    info_lines.append(nl)
    info_lines_vis.append(nl_vis)

    # Underline
    ul = f"{G}{'─' * (len(display_name) + 4)}{R}"
    ul_vis = len(display_name) + 4
    info_lines.append(ul)
    info_lines_vis.append(ul_vis)

    # Fields
    for label, value in fields:
        if not value:
            continue
        fl = f"{D}{label:<12}{R}{B}{value}{R}"
        fl_vis = 12 + _visible_len(value)
        info_lines.append(fl)
        info_lines_vis.append(fl_vis)

    # Top border
    print(f"  {A}╔{'═' * (w - 2)}╗{R}")
    print(f"  {A}║{R}{' ' * (w - 2)}{A}║{R}")

    # Avatar + info area (7 avatar lines)
    right_start = avatar_w + 3  # gap after avatar
    avail_right = inner - right_start

    for row in range(7):
        av_line = avatar[row]

        if row < len(info_lines):
            info = info_lines[row]
            info_vis = info_lines_vis[row]
            right_pad = max(0, (w - 2) - 4 - avatar_w - 3 - info_vis)
            line = f"  {A}║{R}    {F}{av_line}{R}   {info}{' ' * right_pad}{A}║{R}"
        else:
            pad = max(0, (w - 2) - 4 - avatar_w)
            line = f"  {A}║{R}    {F}{av_line}{R}{' ' * pad}{A}║{R}"
        print(line)

    print(f"  {A}║{R}{' ' * (w - 2)}{A}║{R}")

    # Confidence / Decay bars
    if confidence is not None or decay is not None:
        dots = f"{G}{'┄' * (w - 6)}{R}"
        print(f"  {A}║{R}    {dots}  {A}║{R}")

        bar_parts = []
        bar_vis = 0
        if confidence is not None:
            conf_bar = health_bar(confidence, 10)
            conf_pct = f"{confidence * 100:.0f}%"
            part = f"{D}Confidence{R}  {conf_bar} {conf_pct}"
            bar_parts.append(part)
            bar_vis += 11 + 10 + 1 + len(conf_pct)
        if decay is not None:
            decay_bar = health_bar(decay, 10)
            decay_pct = f"{decay * 100:.0f}%"
            part = f"{D}Decay{R}  {decay_bar} {decay_pct}"
            if bar_parts:
                bar_vis += 7  # gap
            bar_parts.append(part)
            bar_vis += 7 + 10 + 1 + len(decay_pct)

        bars_str = ("       " if len(bar_parts) > 1 else "").join(bar_parts)
        bar_pad = max(0, (w - 2) - 4 - bar_vis)
        print(f"  {A}║{R}    {bars_str}{' ' * bar_pad}{A}║{R}")

        dots2 = f"{G}{'┄' * (w - 6)}{R}"
        print(f"  {A}║{R}    {dots2}  {A}║{R}")
        print(f"  {A}║{R}{' ' * (w - 2)}{A}║{R}")

    # Bio
    if bio:
        import textwrap as _tw
        bio_w = w - 10
        wrapped = _tw.wrap(bio, bio_w)
        for line in wrapped:
            pad = max(0, (w - 2) - 4 - len(line))
            print(f"  {A}║{R}    {D}{line}{R}{' ' * pad}{A}║{R}")
        print(f"  {A}║{R}{' ' * (w - 2)}{A}║{R}")

    # Summary strip (bottom section)
    if summary_lines:
        print(f"  {A}╠{'═' * (w - 2)}╣{R}")
        for sl in summary_lines:
            sl_vis = _visible_len(sl)
            pad = max(0, (w - 2) - 4 - sl_vis)
            print(f"  {A}║{R}    {sl}{' ' * pad}{A}║{R}")

    # Bottom border
    print(f"  {A}╚{'═' * (w - 2)}╝{R}")


def render_search_card(
    name: str,
    subtitle: str = "",
    confidence: float | None = None,
    decay: float | None = None,
    connections: int = 0,
    snippet: str = "",
    edge_summary: list[str] | None = None,
    footer_parts: list[str] | None = None,
):
    """Compact but detailed search result card for person nodes."""
    R = C.RESET
    A = C.ACCENT
    D = C.DIM
    B = C.BASE
    F = C.FRAME
    G = C.GHOST

    w = min(term_width() - 2, 74)
    inner = w - 4  # inside │ ... │

    initials = _get_initials(name)

    # Top border with @ marker
    top = f"  {F}┌─ {A}@{R} {F}{'─' * (w - 6)}┐{R}"
    print(top)
    print(f"  {F}│{R}{' ' * inner}  {F}│{R}")

    # Mini avatar + name
    mini_av = f"{F}╭──╮{R}"
    mini_av2 = f"{F}│{B}{initials}{F}│{R}"
    mini_av3 = f"{F}╰──╯{R}"

    # Line 1: top of mini avatar
    name_upper = name.upper()
    name_str = f"{A}{C.BOLD}{name_upper}{R}"
    name_vis = len(name_upper)
    pad = max(0, inner - 6 - name_vis)
    print(f"  {F}│{R}  {mini_av}  {name_str}{' ' * pad}{F}│{R}")

    # Line 2: initials + subtitle
    if subtitle:
        sub_vis = _visible_len(subtitle)
        pad2 = max(0, inner - 6 - sub_vis)
        print(f"  {F}│{R}  {mini_av2}  {subtitle}{' ' * pad2}{F}│{R}")
    else:
        pad2 = max(0, inner - 6)
        print(f"  {F}│{R}  {mini_av2}{' ' * pad2}  {F}│{R}")

    # Line 3: bottom of mini avatar
    pad3 = max(0, inner - 4)
    print(f"  {F}│{R}  {mini_av3}{' ' * pad3}{F}│{R}")

    print(f"  {F}│{R}{' ' * inner}  {F}│{R}")

    # Confidence + Connections + Decay line
    meter_parts = []
    meter_vis = 0
    if confidence is not None:
        conf_bar = health_bar(confidence, 8)
        conf_pct = f"{confidence * 100:.0f}%"
        p = f"{D}Confidence{R} {conf_bar} {conf_pct}"
        meter_parts.append(p)
        meter_vis += 11 + 8 + 1 + len(conf_pct)

    if connections:
        p = f"{D}Connections:{R} {B}{connections}{R}"
        if meter_parts:
            meter_vis += 4
        meter_parts.append(p)
        meter_vis += 13 + len(str(connections))

    if decay is not None:
        decay_bar = health_bar(decay, 10)
        p = f"{D}Decay{R} {decay_bar}"
        if meter_parts:
            meter_vis += 4
        meter_parts.append(p)
        meter_vis += 6 + 10

    if meter_parts:
        meters = "    ".join(meter_parts)
        pad = max(0, inner - meter_vis)
        print(f"  {F}│{R}  {meters}{' ' * pad}{F}│{R}")
        print(f"  {F}│{R}{' ' * inner}  {F}│{R}")

    # Snippet
    if snippet:
        import textwrap as _tw
        snip_w = inner - 4
        wrapped = _tw.wrap(snippet, snip_w)
        for i, line in enumerate(wrapped[:3]):
            prefix = '"' if i == 0 else " "
            suffix = '"' if i == len(wrapped[:3]) - 1 else ""
            text = f"{prefix}{line}{suffix}"
            pad = max(0, inner - 2 - len(text))
            print(f"  {F}│{R}  {D}{text}{R}{' ' * pad}{F}│{R}")
        print(f"  {F}│{R}{' ' * inner}  {F}│{R}")

    # Edge summary
    if edge_summary:
        for es in edge_summary[:5]:
            es_vis = _visible_len(es)
            pad = max(0, inner - 2 - es_vis)
            print(f"  {F}│{R}  {es}{' ' * pad}{F}│{R}")
        print(f"  {F}│{R}{' ' * inner}  {F}│{R}")

    # Footer
    if footer_parts:
        footer = f"  {D}│{R}  ".join(footer_parts)
        footer_vis = _visible_len(footer)
        pad = max(0, inner - 2 - footer_vis)
        print(f"  {F}│{R}  {footer}{' ' * pad}{F}│{R}")

    # Bottom border
    print(f"  {F}└{'─' * (w - 2)}┘{R}")


def _visible_len(s: str) -> int:
    """Length of string excluding ANSI escape codes."""
    return len(re.sub(r"\033\[[^m]*m", "", s))


def box(title: str, content: str, color: str = C.ACCENT, width: int | None = None) -> str:
    """Draw a box around content."""
    w = width or min(term_width() - 4, 76)
    inner = w - 4

    lines = []
    lines.append(f"{color}{'=' * w}{C.RESET}")
    lines.append(f"{color}|{C.RESET} {C.BOLD}{title.center(inner)}{C.RESET} {color}|{C.RESET}")
    lines.append(f"{color}|{'─' * (w - 2)}|{C.RESET}")

    for raw_line in content.split("\n"):
        wrapped = textwrap.wrap(raw_line, inner) if raw_line.strip() else [""]
        for wl in wrapped:
            pad = inner - _visible_len(wl)
            lines.append(f"{color}|{C.RESET} {wl}{' ' * pad} {color}|{C.RESET}")

    lines.append(f"{color}{'=' * w}{C.RESET}")
    return "\n".join(lines)


def horizontal_bar(value: float, width: int = 30, color: str = C.CONFIRM) -> str:
    """Render a horizontal bar chart segment."""
    filled = int(value * width)
    empty = width - filled
    pct = f"{value * 100:.0f}%"
    return f"{color}{'█' * filled}{C.GHOST}{'░' * empty}{C.RESET} {pct}"


def spark_line(values: list[float], width: int = 20) -> str:
    """Tiny sparkline chart from a list of 0-1 floats."""
    sparks = " ▁▂▃▄▅▆▇█"
    if not values:
        return C.DIM + "no data" + C.RESET
    mn, mx = min(values), max(values)
    rng = mx - mn if mx != mn else 1
    chars = []
    for v in values[-width:]:
        idx = int((v - mn) / rng * 8)
        chars.append(sparks[idx])
    return C.ACCENT + "".join(chars) + C.RESET


def spinner(msg: str, duration: float = 1.5):
    """Show a quick spinner animation."""
    frames = ["   [    ]", "   [=   ]", "   [==  ]", "   [=== ]", "   [====]",
              "   [ ===]", "   [  ==]", "   [   =]", "   [    ]"]
    end_time = time.time() + duration
    i = 0
    while time.time() < end_time:
        print(f"\r{C.ACCENT}{frames[i % len(frames)]}{C.RESET} {C.DIM}{msg}{C.RESET}", end="", flush=True)
        time.sleep(0.12)
        i += 1
    print(f"\r{' ' * (len(msg) + 20)}\r", end="", flush=True)


def divider(char: str = "─", color: str = C.FRAME) -> str:
    return f"{color}{char * min(term_width() - 2, 76)}{C.RESET}"


def menu_option(key: str, label: str, desc: str = "") -> str:
    extra = f"  {C.DIM}{desc}{C.RESET}" if desc else ""
    return f"  {C.BOLD}{C.ACCENT}[{key}]{C.RESET}  {C.BASE}{label}{C.RESET}{extra}"


def prompt(msg: str = "❯ ") -> str:
    try:
        return input(f"\n{C.BOLD}{C.ACCENT}{msg}{C.RESET}").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return "q"
