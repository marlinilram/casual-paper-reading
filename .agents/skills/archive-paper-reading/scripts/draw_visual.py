#!/usr/bin/env python3
"""Draw a self-contained SVG framework diagram or grouped bar chart from JSON."""

from __future__ import annotations

import argparse
import html
import json
import math
import sys
import textwrap
from pathlib import Path
from typing import Any


COLORS = ["#3156c8", "#7449d8", "#087f5b", "#d97706", "#d14343", "#187b9d"]
TONE_COLORS = {
    "blue": ("#e8efff", "#3156c8"),
    "purple": ("#f0eaff", "#7449d8"),
    "green": ("#e4f7ef", "#087f5b"),
    "orange": ("#fff1df", "#b45309"),
    "red": ("#ffe7e7", "#b73535"),
    "gray": ("#eef1f5", "#526174"),
}


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def text_lines(text: str, width: int, maximum: int = 3) -> list[str]:
    lines = textwrap.wrap(str(text), width=width, break_long_words=False, replace_whitespace=True)
    if len(lines) > maximum:
        lines = lines[:maximum]
        lines[-1] = lines[-1].rstrip("…") + "…"
    return lines or [""]


def svg_text(lines: list[str], x: float, y: float, size: int, color: str, weight: int = 400, gap: int = 20) -> str:
    parts = [f'<text x="{x}" y="{y}" text-anchor="middle" font-size="{size}" font-weight="{weight}" fill="{color}">']
    for index, line in enumerate(lines):
        dy = 0 if index == 0 else gap
        parts.append(f'<tspan x="{x}" dy="{dy}">{esc(line)}</tspan>')
    parts.append("</text>")
    return "".join(parts)


def draw_flow(spec: dict[str, Any]) -> str:
    nodes = spec.get("nodes")
    edges = spec.get("edges", [])
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("flow visual needs non-empty nodes")
    node_w, node_h, gap_x, gap_y = 230, 126, 90, 55
    positions: dict[str, tuple[float, float]] = {}
    normalized = []
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or not node.get("id") or not node.get("label"):
            raise ValueError("each flow node needs id and label")
        column = int(node.get("column", index))
        row = int(node.get("row", 0))
        x = 55 + column * (node_w + gap_x)
        y = 125 + row * (node_h + gap_y)
        positions[str(node["id"])] = (x, y)
        normalized.append((node, x, y))
    max_column = max(int(node.get("column", index)) for index, node in enumerate(nodes))
    max_row = max(int(node.get("row", 0)) for node in nodes)
    width = 110 + (max_column + 1) * node_w + max_column * gap_x
    height = 185 + (max_row + 1) * node_h + max_row * gap_y
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(spec.get("title") or "Framework diagram")}">',
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#596a86"/></marker></defs>',
        f'<rect width="{width}" height="{height}" rx="28" fill="#f7f9fd"/>',
        svg_text(text_lines(spec.get("title", "Framework"), 62, 2), width / 2, 42, 28, "#172033", 750, 30),
    ]
    if spec.get("subtitle"):
        parts.append(svg_text(text_lines(spec["subtitle"], 90, 2), width / 2, 82, 15, "#667085", 400, 20))
    for edge in edges:
        if not isinstance(edge, dict) or edge.get("from") not in positions or edge.get("to") not in positions:
            raise ValueError("each edge needs valid from/to node ids")
        sx, sy = positions[str(edge["from"])]
        tx, ty = positions[str(edge["to"])]
        if tx > sx:
            x1, y1, x2, y2 = sx + node_w, sy + node_h / 2, tx, ty + node_h / 2
        elif ty > sy:
            x1, y1, x2, y2 = sx + node_w / 2, sy + node_h, tx + node_w / 2, ty
        else:
            x1, y1, x2, y2 = sx, sy + node_h / 2, tx + node_w, ty + node_h / 2
        mid_x = (x1 + x2) / 2
        path = f"M{x1},{y1} C{mid_x},{y1} {mid_x},{y2} {x2},{y2}"
        parts.append(f'<path d="{path}" fill="none" stroke="#596a86" stroke-width="2.5" marker-end="url(#arrow)"/>')
        if edge.get("label"):
            parts.append(svg_text(text_lines(edge["label"], 24, 1), mid_x, (y1 + y2) / 2 - 8, 12, "#526174", 650, 16))
    for node, x, y in normalized:
        fill, stroke = TONE_COLORS.get(str(node.get("tone") or "blue"), TONE_COLORS["blue"])
        parts.append(f'<rect x="{x}" y="{y}" width="{node_w}" height="{node_h}" rx="17" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
        parts.append(svg_text(text_lines(node["label"], 24, 2), x + node_w / 2, y + 42, 18, stroke, 760, 21))
        if node.get("detail"):
            parts.append(svg_text(text_lines(node["detail"], 34, 3), x + node_w / 2, y + 78, 13, "#526174", 430, 17))
    if spec.get("source"):
        parts.append(f'<text x="{width - 24}" y="{height - 18}" text-anchor="end" font-size="11" fill="#7a8799">{esc(spec["source"])}</text>')
    parts.append("</svg>")
    return "".join(parts)


def draw_bar(spec: dict[str, Any]) -> str:
    categories = spec.get("categories")
    series = spec.get("series")
    if not isinstance(categories, list) or not categories or not isinstance(series, list) or not series:
        raise ValueError("bar visual needs categories and series")
    for item in series:
        if not isinstance(item, dict) or not item.get("name") or len(item.get("values", [])) != len(categories):
            raise ValueError("each series needs name and one value per category")
    values = [float(value) for item in series for value in item["values"]]
    minimum = min(0.0, min(values))
    maximum = max(values)
    if math.isclose(maximum, minimum):
        maximum = minimum + 1.0
    width, height = 1040, 620
    left, right, top, bottom = 100, 45, 105, 115
    plot_w, plot_h = width - left - right, height - top - bottom
    group_w = plot_w / len(categories)
    bar_area = group_w * 0.72
    bar_w = bar_area / len(series)

    def y_of(value: float) -> float:
        return top + (maximum - value) / (maximum - minimum) * plot_h

    zero_y = y_of(0)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(spec.get("title") or "Bar chart")}">',
        f'<rect width="{width}" height="{height}" rx="28" fill="#f7f9fd"/>',
        svg_text(text_lines(spec.get("title", "Comparison"), 72, 2), width / 2, 42, 28, "#172033", 760, 30),
    ]
    if spec.get("subtitle"):
        parts.append(svg_text(text_lines(spec["subtitle"], 100, 2), width / 2, 77, 14, "#667085", 400, 18))
    ticks = 5
    for tick in range(ticks + 1):
        value = minimum + (maximum - minimum) * tick / ticks
        y = y_of(value)
        parts.append(f'<line x1="{left}" y1="{y}" x2="{width-right}" y2="{y}" stroke="#dce2ee" stroke-width="1"/>')
        parts.append(f'<text x="{left-12}" y="{y+5}" text-anchor="end" font-size="12" fill="#667085">{value:.2f}</text>')
    parts.append(f'<line x1="{left}" y1="{zero_y}" x2="{width-right}" y2="{zero_y}" stroke="#75839a" stroke-width="1.5"/>')
    for category_index, category in enumerate(categories):
        group_x = left + category_index * group_w + (group_w - bar_area) / 2
        center_x = left + (category_index + 0.5) * group_w
        parts.append(svg_text(text_lines(category, 15, 2), center_x, height - bottom + 28, 13, "#526174", 650, 16))
        for series_index, item in enumerate(series):
            value = float(item["values"][category_index])
            x = group_x + series_index * bar_w + 3
            y = min(y_of(value), zero_y)
            bar_h = abs(zero_y - y_of(value))
            color = item.get("color") or COLORS[series_index % len(COLORS)]
            parts.append(f'<rect x="{x}" y="{y}" width="{max(2, bar_w-6)}" height="{max(1, bar_h)}" rx="4" fill="{esc(color)}"/>')
            label_y = y - 7 if value >= 0 else y + bar_h + 16
            parts.append(f'<text x="{x + (bar_w-6)/2}" y="{label_y}" text-anchor="middle" font-size="11" font-weight="650" fill="#344054">{value:g}</text>')
    legend_x = left
    legend_y = height - 30
    for index, item in enumerate(series):
        color = item.get("color") or COLORS[index % len(COLORS)]
        parts.append(f'<rect x="{legend_x}" y="{legend_y-11}" width="14" height="14" rx="3" fill="{esc(color)}"/>')
        parts.append(f'<text x="{legend_x+20}" y="{legend_y}" font-size="12" fill="#526174">{esc(item["name"])}</text>')
        legend_x += 28 + len(str(item["name"])) * 8
    if spec.get("y_label"):
        parts.append(f'<text x="25" y="{top + plot_h/2}" text-anchor="middle" font-size="13" fill="#526174" transform="rotate(-90 25 {top + plot_h/2})">{esc(spec["y_label"])}</text>')
    if spec.get("source"):
        parts.append(f'<text x="{width-right}" y="{height-15}" text-anchor="end" font-size="11" fill="#7a8799">{esc(spec["source"])}</text>')
    parts.append("</svg>")
    return "".join(parts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spec = json.loads(args.input.expanduser().resolve().read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        raise ValueError("visual spec must be a JSON object")
    visual_type = spec.get("type")
    if visual_type == "flow":
        document = draw_flow(spec)
    elif visual_type == "bar":
        document = draw_bar(spec)
    else:
        raise ValueError("supported visual types: flow, bar")
    output = args.output.expanduser().resolve()
    if output.suffix.lower() != ".svg":
        raise ValueError("output must end in .svg")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    print(json.dumps({"output": str(output), "type": visual_type}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
