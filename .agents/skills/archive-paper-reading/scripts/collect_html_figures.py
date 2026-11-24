#!/usr/bin/env python3
"""Collect and rank paper figures from arXiv HTML or another paper page."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import html
import json
import mimetypes
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


DEFAULT_KEYWORDS = (
    "overview,architecture,framework,pipeline,method,comparison,qualitative,"
    "ablation,result,failure,visualization,system,network"
)
USER_AGENT = "Mozilla/5.0 paper-reading-figure-collector/1.0"


class FigureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.figures: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None
        self.figure_depth = 0
        self.caption_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "figure":
            if self.current is None:
                self.current = {"id": values.get("id", ""), "caption_parts": [], "images": []}
                self.figure_depth = 1
            else:
                self.figure_depth += 1
            return
        if self.current is None:
            return
        if tag == "figcaption":
            self.caption_depth += 1
        elif tag == "img":
            src = values.get("src") or values.get("data-src")
            if src and not src.startswith("data:"):
                self.current["images"].append({"src": src, "alt": values.get("alt", "")})

    def handle_endtag(self, tag: str) -> None:
        if self.current is None:
            return
        if tag == "figcaption" and self.caption_depth:
            self.caption_depth -= 1
        elif tag == "figure":
            self.figure_depth -= 1
            if self.figure_depth == 0:
                caption = re.sub(r"\s+", " ", " ".join(self.current["caption_parts"])).strip()
                self.current["caption"] = caption
                if self.current["images"]:
                    self.figures.append(self.current)
                self.current = None

    def handle_data(self, data: str) -> None:
        if self.current is not None and self.caption_depth:
            stripped = data.strip()
            if stripped:
                self.current["caption_parts"].append(stripped)


def fetch(url: str) -> tuple[bytes, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60) as response:
        return response.read(), response.headers.get_content_type()


def fetch_image(url: str) -> tuple[bytes, str]:
    """Download with an absolute wall-clock bound when curl is available."""
    if shutil.which("curl"):
        result = subprocess.run(
            [
                "curl",
                "-L",
                "--http1.1",
                "--connect-timeout",
                "8",
                "--max-time",
                "90",
                "--fail",
                "--silent",
                "--show-error",
                "--user-agent",
                USER_AGENT,
                url,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=95,
        )
        return result.stdout, mimetypes.guess_type(urlparse(url).path)[0] or "application/octet-stream"
    return fetch(url)


def figure_number(caption: str) -> int | None:
    match = re.search(r"\b(?:figure|fig\.?)[\s\u00a0]*(\d+)", caption, re.I)
    return int(match.group(1)) if match else None


def classify_role(caption: str) -> str:
    text = caption.lower()
    if any(word in text for word in ("overview", "architecture", "framework", "pipeline", "network", "system")):
        return "architecture"
    if any(word in text for word in ("qualitative", "visual comparison", "visualization")):
        return "qualitative"
    if "ablation" in text:
        return "ablation"
    if any(word in text for word in ("failure", "limitation")):
        return "failure"
    if any(word in text for word in ("quantitative", "plot", "curve", "result")):
        return "quantitative"
    if any(word in text for word in ("method", "illustration", "diagram")):
        return "concept"
    return "other"


def score_figure(figure: dict[str, Any], keywords: list[str]) -> int:
    caption = figure.get("caption", "").lower()
    score = sum(5 for keyword in keywords if keyword and keyword in caption)
    number = figure_number(caption)
    if number is not None and number <= 3:
        score += 4 - number
    if len(caption) > 35:
        score += 1
    if len(figure.get("images", [])) > 1:
        score += 1
    return score


def suffix_for(url: str, content_type: str) -> str:
    path_suffix = Path(urlparse(url).path).suffix.lower()
    if path_suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}:
        return path_suffix
    guessed = mimetypes.guess_extension(content_type) or ".bin"
    return ".jpg" if guessed == ".jpe" else guessed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="paper HTML URL")
    source.add_argument("--html-file", type=Path, help="downloaded paper HTML")
    parser.add_argument("--base-url", help="base URL for relative images when using --html-file")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max", type=int, default=8, dest="max_figures")
    parser.add_argument("--include", help="comma-separated figure numbers, e.g. 2,5")
    parser.add_argument("--keywords", default=DEFAULT_KEYWORDS, help="comma-separated ranking keywords")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.url:
        raw, _ = fetch(args.url)
        document = raw.decode("utf-8", errors="replace")
        base_url = args.url
        page_url = args.url
    else:
        document = args.html_file.expanduser().resolve().read_text(encoding="utf-8", errors="replace")
        base_url = args.base_url or ""
        page_url = args.base_url or args.html_file.expanduser().resolve().as_uri()

    parser = FigureParser()
    parser.feed(document)
    keywords = [item.strip().lower() for item in args.keywords.split(",") if item.strip()]
    requested = {int(item) for item in args.include.split(",")} if args.include else set()
    candidates = []
    for order, figure in enumerate(parser.figures, 1):
        number = figure_number(figure.get("caption", ""))
        if requested and number not in requested:
            continue
        figure["number"] = number
        figure["role"] = classify_role(figure.get("caption", ""))
        figure["score"] = score_figure(figure, keywords)
        figure["order"] = order
        candidates.append(figure)
    if not requested:
        candidates.sort(key=lambda item: (-item["score"], item["order"]))
    candidates = candidates[: max(1, args.max_figures)]

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    download_results: dict[tuple[int, int], dict[str, str]] = {}

    def download_one(candidate_index: int, image_index: int, figure: dict[str, Any], image: dict[str, str]) -> tuple[tuple[int, int], dict[str, str]]:
        image_url = urljoin(base_url, image["src"]) if base_url else image["src"]
        if not image_url.startswith(("http://", "https://")):
            return (candidate_index, image_index), {"src": "", "url": image_url, "error": "relative image needs --base-url"}
        try:
            payload, content_type = fetch_image(image_url)
            suffix = suffix_for(image_url, content_type)
            number_label = figure.get("number") or candidate_index
            filename = f"figure-{number_label:02d}-{image_index:02d}{suffix}"
            destination = output_dir / filename
            destination.write_bytes(payload)
            result = {"src": str(destination), "url": image_url, "alt": image.get("alt", "")}
        except Exception as exc:  # keep other candidates usable
            result = {"src": "", "url": image_url, "error": str(exc)}
        return (candidate_index, image_index), result

    futures = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        for candidate_index, figure in enumerate(candidates, 1):
            for image_index, image in enumerate(figure["images"], 1):
                futures.append(executor.submit(download_one, candidate_index, image_index, figure, image))
        for future in as_completed(futures):
            key, result = future.result()
            download_results[key] = result

    manifest_figures: list[dict[str, Any]] = []
    for candidate_index, figure in enumerate(candidates, 1):
        saved_images = [
            download_results[(candidate_index, image_index)]
            for image_index, _ in enumerate(figure["images"], 1)
            if (candidate_index, image_index) in download_results
        ]
        anchor = f"#{figure['id']}" if figure.get("id") else ""
        manifest_figures.append(
            {
                "figure_number": figure.get("number"),
                "caption": html.unescape(figure.get("caption", "")),
                "role": figure["role"],
                "source_kind": "paper",
                "source_url": f"{page_url}{anchor}",
                "score": figure["score"],
                "images": saved_images,
            }
        )
    manifest = {"source": page_url, "figures": manifest_figures}
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(manifest_path), **manifest}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
