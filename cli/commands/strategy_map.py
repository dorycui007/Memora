"""Campus map — real OpenStreetMap tiles with labeled markers in the terminal."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from cli.rendering import C, prompt, term_width
from cli.strategy.data import (
    LOCATIONS,
    PEOPLE_LOCATIONS,
    PHASE_LOCATION_RELEVANCE,
)
from cli.strategy.phase_engine import current_phase


# UTM campus center
_UTM_LAT = 43.5495
_UTM_LNG = -79.6635


def run_strategy_map():
    """Entry point — campus map with zoom controls."""
    A, D, R = C.ACCENT, C.DIM, C.RESET

    try:
        from staticmap import StaticMap  # noqa: F401
    except ImportError:
        print(f"\n  {C.SIGNAL}staticmap not installed.{R}")
        print(f"  {C.BASE}pip install staticmap{R}")
        prompt("[enter] back")
        return

    if not shutil.which("chafa"):
        print(f"\n  {C.SIGNAL}chafa not installed.{R}")
        print(f"  {C.BASE}brew install chafa{R}")
        prompt("[enter] back")
        return

    zoom = 16
    while True:
        print("\033[2J\033[H", end="", flush=True)
        _render_map(zoom)
        print(f"  {A}[+]{R} zoom in  {A}[-]{R} zoom out  {A}[q]{R} back  {D}zoom={zoom}{R}")
        choice = prompt("map> ")
        if choice in ("q", "b", "back", ""):
            return
        elif choice in ("+", "=", "i"):
            zoom = min(zoom + 1, 18)
        elif choice in ("-", "_", "o"):
            zoom = max(zoom - 1, 14)


def _render_map(zoom: int):
    """Render OSM map with labeled markers burned into the image."""
    from staticmap import StaticMap, CircleMarker
    from PIL import ImageDraw, ImageFont

    tw = term_width()
    th = shutil.get_terminal_size((80, 40)).lines
    # Leave 3 lines for controls + prompt
    map_rows = max(10, th - 3)

    # Higher res image for better label clarity
    img_w = max(1000, tw * 8)
    img_h = int(img_w * 0.55)

    m = StaticMap(
        img_w, img_h,
        url_template="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    )

    type_rgb = {
        "governance": (35, 180, 100),
        "academic": (0, 180, 255),
        "startup": (180, 100, 255),
        "event": (255, 150, 50),
        "social": (245, 140, 160),
    }

    # Scale marker size with zoom
    dot_r = max(6, 4 + (zoom - 14) * 2)

    # Add location markers (so staticmap includes them in bounds)
    for loc_id, loc in LOCATIONS.items():
        color = type_rgb.get(loc["type"], (150, 150, 150))
        m.add_marker(CircleMarker((loc["lng"], loc["lat"]), color, dot_r))

    # Add people markers
    for pid, person in PEOPLE_LOCATIONS.items():
        m.add_marker(CircleMarker((person["lng"], person["lat"]), (200, 140, 255), max(4, dot_r - 2)))

    # Render base map
    image = m.render(zoom=zoom, center=[_UTM_LNG, _UTM_LAT])
    draw = ImageDraw.Draw(image)

    # Try to load a readable font, fall back to default
    font_size = max(12, 10 + (zoom - 14) * 2)
    font_sm = max(10, font_size - 3)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/SFNSMono.ttf", font_size)
        font_small = ImageFont.truetype("/System/Library/Fonts/SFNSMono.ttf", font_sm)
    except (OSError, IOError):
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", font_size)
            font_small = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", font_sm)
        except (OSError, IOError):
            font = ImageFont.load_default()
            font_small = font

    # Convert lat/lng to pixel coords on the rendered image
    def latlng_to_px(lat: float, lng: float) -> tuple[int, int]:
        """Convert lat/lng to pixel position on the rendered image."""
        import math
        # Web Mercator projection
        n = 2 ** zoom
        x_tile = (lng + 180.0) / 360.0 * n
        y_tile = (1.0 - math.log(math.tan(math.radians(lat)) + 1.0 / math.cos(math.radians(lat))) / math.pi) / 2.0 * n

        # Center tile coords
        cx_tile = (_UTM_LNG + 180.0) / 360.0 * n
        cy_tile = (1.0 - math.log(math.tan(math.radians(_UTM_LAT)) + 1.0 / math.cos(math.radians(_UTM_LAT))) / math.pi) / 2.0 * n

        # Pixel offset from center
        px = int((x_tile - cx_tile) * 256 + img_w / 2)
        py = int((y_tile - cy_tile) * 256 + img_h / 2)
        return px, py

    # Draw labels for locations
    for loc_id, loc in LOCATIONS.items():
        px, py = latlng_to_px(loc["lat"], loc["lng"])
        color = type_rgb.get(loc["type"], (180, 180, 180))
        name = loc["name"]

        # Background box for readability
        bbox = draw.textbbox((0, 0), name, font=font)
        tw_text = bbox[2] - bbox[0]
        th_text = bbox[3] - bbox[1]
        label_x = px + dot_r + 4
        label_y = py - th_text // 2

        # Draw background rect
        padding = 3
        draw.rectangle(
            [label_x - padding, label_y - padding, label_x + tw_text + padding, label_y + th_text + padding],
            fill=(20, 25, 30, 200),
        )
        # Draw text
        draw.text((label_x, label_y), name, fill=color, font=font)

    # Draw labels for people
    for pid, person in PEOPLE_LOCATIONS.items():
        px, py = latlng_to_px(person["lat"], person["lng"])
        initials = person["initials"]
        name = person["name"]
        label = f"@{initials} {name}"

        bbox = draw.textbbox((0, 0), label, font=font_small)
        tw_text = bbox[2] - bbox[0]
        th_text = bbox[3] - bbox[1]
        label_x = px + dot_r + 2
        label_y = py + dot_r + 2

        draw.rectangle(
            [label_x - 2, label_y - 2, label_x + tw_text + 2, label_y + th_text + 2],
            fill=(20, 25, 30, 200),
        )
        draw.text((label_x, label_y), label, fill=(200, 160, 255), font=font_small)

    # Draw phase actions in a panel on the image
    cp = current_phase()
    relevance = PHASE_LOCATION_RELEVANCE.get(cp["id"], {})
    if relevance:
        panel_lines = [f"PHASE: {cp['name'].upper()}"]
        for loc_id, action in relevance.items():
            loc_name = LOCATIONS.get(loc_id, {}).get("name", loc_id)
            panel_lines.append(f"  {loc_name}: {action}")

        # Draw panel in bottom-left
        line_h = font_sm + 4
        panel_h = len(panel_lines) * line_h + 12
        panel_w = 420
        panel_x = 10
        panel_y = img_h - panel_h - 10

        # Semi-transparent background
        overlay = image.copy()
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle(
            [panel_x, panel_y, panel_x + panel_w, panel_y + panel_h],
            fill=(15, 20, 25),
        )
        image = image.copy()
        from PIL import Image
        image = Image.blend(image, overlay, 0.85)
        draw = ImageDraw.Draw(image)

        # Border
        draw.rectangle(
            [panel_x, panel_y, panel_x + panel_w, panel_y + panel_h],
            outline=(0, 180, 255, 120),
            width=1,
        )

        # Text
        for i, line in enumerate(panel_lines):
            color = (0, 210, 255) if i == 0 else (180, 190, 200)
            f = font if i == 0 else font_small
            draw.text((panel_x + 8, panel_y + 6 + i * line_h), line, fill=color, font=f)

    # Legend in top-right
    legend_items = [
        ("● Governance", (35, 180, 100)),
        ("● Academic", (0, 180, 255)),
        ("● Startup", (180, 100, 255)),
        ("● Event", (255, 150, 50)),
        ("● Social", (245, 140, 160)),
        ("● People", (200, 140, 255)),
    ]
    leg_line_h = font_sm + 4
    leg_h = len(legend_items) * leg_line_h + 10
    leg_w = 130
    leg_x = img_w - leg_w - 10
    leg_y = 10
    draw.rectangle([leg_x, leg_y, leg_x + leg_w, leg_y + leg_h], fill=(15, 20, 25), outline=(60, 70, 80))
    for i, (label, color) in enumerate(legend_items):
        draw.text((leg_x + 8, leg_y + 5 + i * leg_line_h), label, fill=color, font=font_small)

    # Save and render with chafa
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = f.name
    try:
        image.save(tmp_path)
        subprocess.run(
            ["chafa", "--size", f"{tw}x{map_rows}", "--animate=off", tmp_path],
            check=False,
        )
    finally:
        os.unlink(tmp_path)
