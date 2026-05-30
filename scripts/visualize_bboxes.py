#!/usr/bin/env python3
"""Visualize VLM-detected bounding boxes on original screenshots.

Reads an AnalysisResult JSON and the corresponding original image,
draws colored bbox rectangles with index numbers, and outputs:
  - {image_name}_annotated.png  —  annotated image with overlay
  - {image_name}_elements.txt   —  text mapping of index → element details

Usage:
    python scripts/visualize_bboxes.py \
        docs/spike-results/round-1/vscode_analysis.json \
        docs/spike-screenshots/vscode.png \
        -o docs/spike-results/round-1/
"""

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


# ── Color palette by element type ────────────────────────────────────────────

TYPE_COLORS = {
    "button":    "#4CAF50",  # green
    "input":     "#2196F3",  # blue
    "checkbox":  "#FF9800",  # orange
    "radio":     "#FF9800",  # orange
    "tab":       "#9C27B0",  # purple
    "menuitem":  "#00BCD4",  # cyan
    "link":      "#3F51B5",  # indigo
    "window":    "#F44336",  # red
    "dialog":    "#F44336",  # red
    "sidebar":   "#607D8B",  # blue-grey
    "toolbar":   "#795548",  # brown
    "panel":     "#009688",  # teal
    "list":      "#8BC34A",  # light-green
    "table":     "#8BC34A",  # light-green
    "form":      "#E91E63",  # pink
    "text":      "#9E9E9E",  # grey
    "unknown":   "#757575",  # dark grey
}

DEFAULT_COLOR = "#757575"


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert hex color string to RGB tuple."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def load_font(size: int = 14) -> ImageFont.FreeTypeFont:
    """Load a reasonable font, falling back to default."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in font_paths:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def draw_bboxes(
    image_path: str,
    analysis_json_path: str,
    output_dir: str,
) -> tuple[str, str]:
    """Draw bbox overlays and generate text mapping file.

    Args:
        image_path: Path to original screenshot PNG.
        analysis_json_path: Path to AnalysisResult JSON.
        output_dir: Directory for output files.

    Returns:
        Tuple of (annotated_image_path, elements_text_path).
    """
    image_path = Path(image_path)
    analysis_json_path = Path(analysis_json_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    if not analysis_json_path.exists():
        raise FileNotFoundError(f"Analysis JSON not found: {analysis_json_path}")

    image = Image.open(image_path).convert("RGBA")
    with open(analysis_json_path, "r", encoding="utf-8") as f:
        analysis = json.load(f)

    elements = analysis.get("elements", [])
    if not elements:
        print(f"[WARN] No elements found in {analysis_json_path}")

    # Prepare drawing
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = load_font(14)
    small_font = load_font(11)

    text_lines = []

    for i, elem in enumerate(elements):
        idx = i + 1  # 1-based index
        bbox = elem.get("bbox", [0, 0, 0, 0])

        if len(bbox) != 4:
            continue

        x1, y1, x2, y2 = [int(v) for v in bbox]

        # Skip zero-size or invalid bboxes
        if x1 >= x2 or y1 >= y2:
            continue

        elem_type = elem.get("type", "unknown")
        color_hex = TYPE_COLORS.get(elem_type, DEFAULT_COLOR)
        color_rgb = hex_to_rgb(color_hex)

        # Draw rectangle
        draw.rectangle([x1, y1, x2, y2], outline=color_rgb, width=2)

        # Draw filled label background at top-left corner
        label = str(idx)
        # Estimate text size
        bbox_text = draw.textbbox((0, 0), label, font=font)
        text_w = bbox_text[2] - bbox_text[0] + 6
        text_h = bbox_text[3] - bbox_text[1] + 4
        label_x = max(0, x1)
        label_y = max(0, y1 - text_h)
        draw.rectangle(
            [label_x, label_y, label_x + text_w, label_y + text_h],
            fill=color_rgb,
        )
        draw.text(
            (label_x + 3, label_y + 2),
            label,
            fill=(255, 255, 255, 255),
            font=font,
        )

        # Build text mapping line
        text_value = elem.get("text")
        confidence = elem.get("confidence")
        line = f"[{idx}] type={elem_type}"
        if text_value:
            line += f' text="{text_value}"'
        line += f" bbox=[{x1},{y1},{x2},{y2}]"
        if confidence is not None:
            line += f" confidence={confidence:.2f}"
        text_lines.append(line)

    # Composite overlay onto original
    result = Image.alpha_composite(image, overlay)

    # Save annotated image
    stem = image_path.stem
    annotated_path = output_dir / f"{stem}_annotated.png"
    result.save(annotated_path, "PNG")
    print(f"[OK] Annotated image: {annotated_path}")

    # Save text mapping
    txt_path = output_dir / f"{stem}_elements.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"# Elements for {image_path.name}\n")
        f.write(f"# Total: {len(text_lines)}\n\n")
        for line in text_lines:
            f.write(line + "\n")
    print(f"[OK] Element mapping: {txt_path} ({len(text_lines)} elements)")

    return str(annotated_path), str(txt_path)


def main():
    parser = argparse.ArgumentParser(
        description="Visualize VLM bbox results on original screenshots"
    )
    parser.add_argument(
        "analysis_json",
        help="Path to AnalysisResult JSON from spike_arch_c.py",
    )
    parser.add_argument(
        "image",
        help="Path to original screenshot PNG",
    )
    parser.add_argument(
        "-o", "--output-dir", default=".",
        help="Output directory (default: current dir)",
    )
    args = parser.parse_args()

    try:
        draw_bboxes(args.image, args.analysis_json, args.output_dir)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
