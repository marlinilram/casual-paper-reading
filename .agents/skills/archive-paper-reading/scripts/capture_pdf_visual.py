#!/usr/bin/env python3
"""Render full PDF pages or pixel-coordinate crops as PNG visual evidence."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def parse_crop(value: str) -> tuple[int, int, int, int, int]:
    try:
        page_text, box_text = value.split(":", 1)
        x, y, width, height = (int(item) for item in box_text.split(","))
        page = int(page_text)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError("crop must be page:x,y,width,height") from exc
    if min(page, width, height) < 1 or min(x, y) < 0:
        raise argparse.ArgumentTypeError("page/width/height must be positive; x/y must be non-negative")
    return page, x, y, width, height


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--page", action="append", type=int, default=[])
    parser.add_argument("--crop", action="append", type=parse_crop, default=[])
    parser.add_argument("--dpi", type=int, default=160)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--source-url")
    return parser.parse_args()


def render(pdf: Path, output_prefix: Path, page: int, dpi: int, crop: tuple[int, int, int, int] | None) -> Path:
    command = [
        "pdftoppm",
        "-f",
        str(page),
        "-l",
        str(page),
        "-r",
        str(dpi),
        "-png",
        "-singlefile",
    ]
    if crop:
        x, y, width, height = crop
        command += ["-x", str(x), "-y", str(y), "-W", str(width), "-H", str(height)]
    command += [str(pdf), str(output_prefix)]
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    result = output_prefix.with_suffix(".png")
    if not result.is_file() or result.stat().st_size == 0:
        raise RuntimeError(f"pdftoppm did not create {result}")
    return result


def main() -> int:
    args = parse_args()
    if not args.page and not args.crop:
        raise ValueError("provide at least one --page or --crop")
    if shutil.which("pdftoppm") is None:
        raise RuntimeError("pdftoppm is required but unavailable")
    pdf = args.pdf.expanduser().resolve()
    if not pdf.is_file():
        raise FileNotFoundError(pdf)
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    images = []
    for page in args.page:
        prefix = output_dir / f"page-{page:03d}"
        result = render(pdf, prefix, page, args.dpi, None)
        source_url = f"{args.source_url}#page={page}" if args.source_url else pdf.as_uri()
        images.append(
            {
                "src": str(result),
                "alt": f"PDF page {page}",
                "caption": f"Screenshot of PDF page {page}.",
                "source_url": source_url,
                "role": "other",
                "source_kind": "screenshot",
            }
        )
    for index, (page, x, y, width, height) in enumerate(args.crop, 1):
        prefix = output_dir / f"page-{page:03d}-crop-{index:02d}"
        result = render(pdf, prefix, page, args.dpi, (x, y, width, height))
        source_url = f"{args.source_url}#page={page}" if args.source_url else pdf.as_uri()
        images.append(
            {
                "src": str(result),
                "alt": f"Crop from PDF page {page}",
                "caption": f"Screenshot crop from PDF page {page}.",
                "source_url": source_url,
                "role": "other",
                "source_kind": "screenshot",
            }
        )
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps({"figures": images}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(manifest_path), "figures": images}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
