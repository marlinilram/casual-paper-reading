#!/usr/bin/env python3
"""Create a self-contained visual paper-reading report and refresh its index."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import sys
import unicodedata
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = SKILL_ROOT / "assets" / "report-template.html"


def fail(message: str) -> None:
    raise ValueError(message)


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        fail(f"expected a list, got {type(value).__name__}")
    return value


def attr(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def inline(value: Any) -> str:
    """Render a deliberately small and safe inline Markdown subset."""
    text = html.escape(str(value or ""), quote=False)
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
        lambda m: f'<a href="{attr(m.group(2))}" target="_blank" rel="noreferrer">{m.group(1)}</a>',
        text,
    )
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    return text.replace("\n", "<br>")


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    if slug:
        return slug[:72].rstrip("-")
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    return f"paper-reading-{digest}"


def validate_payload(data: dict[str, Any]) -> None:
    for key in ("title", "summary"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            fail(f"'{key}' must be a non-empty string")
    sections = as_list(data.get("sections"))
    if not sections:
        fail("'sections' must contain at least one analysis section")
    for index, section in enumerate(sections, 1):
        if not isinstance(section, dict) or not str(section.get("heading", "")).strip():
            fail(f"section {index} needs a non-empty 'heading'")
    rich_visuals = 0
    for section in sections:
        rich_visuals += len(as_list(section.get("figures")))
        rich_visuals += len(as_list(section.get("image_groups")))
    policy = str(data.get("visual_policy") or "standard")
    if policy not in {"standard", "compact"}:
        fail("'visual_policy' must be 'standard' or 'compact'")
    minimum = 2 if policy == "standard" else 1
    if rich_visuals < minimum:
        fail(
            f"visual policy '{policy}' requires at least {minimum} rich visual(s) "
            "from section figures/image_groups; pipelines, metric cards, and tables do not count"
        )


def allocate_report_path(output_dir: Path, data: dict[str, Any], now: datetime) -> Path:
    base_hint = str(data.get("slug") or data.get("paper", {}).get("title") or data["title"])
    base = f"{now:%Y-%m-%d}-{slugify(base_hint)}"
    candidate = output_dir / f"{base}.html"
    suffix = 2
    while candidate.exists():
        candidate = output_dir / f"{base}-{suffix}.html"
        suffix += 1
    return candidate


def is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def copy_figure(src: str, report_path: Path, ordinal: int) -> str:
    if is_http_url(src):
        return src
    source = Path(src).expanduser().resolve()
    if not source.is_file():
        fail(f"figure does not exist: {source}")
    safe_name = f"{ordinal:02d}-{slugify(source.stem)}{source.suffix.lower()}"
    asset_dir = report_path.parent / "assets" / report_path.stem
    asset_dir.mkdir(parents=True, exist_ok=True)
    destination = asset_dir / safe_name
    shutil.copy2(source, destination)
    return destination.relative_to(report_path.parent).as_posix()


def render_hero(data: dict[str, Any]) -> str:
    paper = data.get("paper") if isinstance(data.get("paper"), dict) else {}
    kind = data.get("analysis_kind") or "Paper analysis"
    meta: list[str] = []
    paper_title = paper.get("title")
    paper_url = paper.get("url")
    if paper_title and paper_url and is_http_url(str(paper_url)):
        meta.append(f'<a href="{attr(paper_url)}" target="_blank" rel="noreferrer">{inline(paper_title)}</a>')
    elif paper_title:
        meta.append(f"<span>{inline(paper_title)}</span>")
    for key in ("authors", "venue", "year"):
        if paper.get(key):
            meta.append(f"<span>{inline(paper[key])}</span>")
    for identifier in as_list(paper.get("identifiers")):
        meta.append(f"<span>{inline(identifier)}</span>")
    return (
        '<header class="hero">'
        f'<div class="eyebrow">{inline(kind)}</div>'
        f'<h1>{inline(data["title"])}</h1>'
        f'<p class="hero-summary">{inline(data["summary"])}</p>'
        f'<div class="meta">{"".join(meta)}</div>'
        "</header>"
    )


def render_key_points(items: list[Any]) -> str:
    if not items:
        return ""
    cards = "".join(f'<div class="key">{inline(item)}</div>' for item in items)
    return f'<section class="panel" id="key-points"><h2>核心结论</h2><div class="key-grid">{cards}</div></section>'


def render_pipeline(items: list[Any]) -> str:
    if not items:
        return ""
    nodes: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not item.get("label"):
            fail("every pipeline node needs a 'label'")
        if index:
            nodes.append('<div class="arrow" aria-hidden="true">→</div>')
        detail = f'<small>{inline(item.get("detail"))}</small>' if item.get("detail") else ""
        nodes.append(f'<div class="flow-node"><strong>{inline(item["label"])}</strong>{detail}</div>')
    return f'<section class="panel" id="pipeline"><h2>方法脉络</h2><div class="flow">{"".join(nodes)}</div></section>'


def render_metrics(items: list[Any]) -> str:
    if not items:
        return ""
    cards: list[str] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("label") or item.get("value") is None:
            fail("every metric needs 'label' and 'value'")
        tone = str(item.get("tone") or "")
        tone_class = tone if tone in {"good", "warn"} else ""
        context = f'<span class="metric-context">{inline(item.get("context"))}</span>' if item.get("context") else ""
        cards.append(
            f'<div class="metric {tone_class}"><span class="metric-label">{inline(item["label"])}</span>'
            f'<span class="metric-value">{inline(item["value"])}</span>{context}</div>'
        )
    return f'<section class="panel" id="metrics"><h2>关键证据</h2><div class="metric-grid">{"".join(cards)}</div></section>'


def render_table(table: dict[str, Any]) -> str:
    headers = as_list(table.get("headers"))
    rows = as_list(table.get("rows"))
    if not headers or not rows:
        fail("each table needs non-empty 'headers' and 'rows'")
    head = "".join(f"<th>{inline(cell)}</th>" for cell in headers)
    body_rows: list[str] = []
    for row in rows:
        row_list = as_list(row)
        if len(row_list) != len(headers):
            fail("table row length must match headers")
        body_rows.append("<tr>" + "".join(f"<td>{inline(cell)}</td>" for cell in row_list) + "</tr>")
    caption = f"<caption>{inline(table.get('caption'))}</caption>" if table.get("caption") else ""
    return f'<div class="table-wrap"><table>{caption}<thead><tr>{head}</tr></thead><tbody>{"".join(body_rows)}</tbody></table></div>'


def render_figure(figure: dict[str, Any], report_path: Path, ordinal: int, card: bool = False) -> str:
    if not figure.get("src"):
        fail("each figure needs 'src'")
    if not figure.get("caption"):
        fail("each rich visual needs a useful 'caption'")
    if not figure.get("source_url") or not is_http_url(str(figure["source_url"])):
        fail("each rich visual needs an HTTP(S) 'source_url' for provenance")
    role = str(figure.get("role") or "other")
    if role not in {"architecture", "qualitative", "quantitative", "ablation", "failure", "concept", "other"}:
        fail(f"unsupported figure role: {role}")
    source_kind = str(figure.get("source_kind") or "paper")
    if source_kind not in {"paper", "project", "screenshot", "redrawn", "chart"}:
        fail(f"unsupported figure source_kind: {source_kind}")
    src = copy_figure(str(figure["src"]), report_path, ordinal)
    caption = inline(figure.get("caption") or figure.get("alt") or "Figure")
    caption += f' · <a href="{attr(figure["source_url"])}" target="_blank" rel="noreferrer">source</a>'
    badges = f'<div class="visual-badges"><span>{inline(role)}</span><span>{inline(source_kind)}</span></div>'
    figure_class = "figure-card" if card else "figure-full"
    return (
        f'<figure class="{figure_class}">{badges}'
        f'<a class="figure-link" href="{attr(src)}" target="_blank">'
        f'<img src="{attr(src)}" alt="{attr(figure.get("alt") or figure.get("caption") or "Paper figure")}" loading="lazy"></a>'
        f'<figcaption>{caption}</figcaption></figure>'
    )


def render_image_group(group: dict[str, Any], report_path: Path, ordinal: int) -> tuple[str, int]:
    images = as_list(group.get("images"))
    if len(images) < 2:
        fail("each image_group needs at least two images")
    columns = max(1, min(4, int(group.get("columns") or 2)))
    title = f'<h3>{inline(group.get("title"))}</h3>' if group.get("title") else ""
    caption = f'<p class="visual-group-caption">{inline(group.get("caption"))}</p>' if group.get("caption") else ""
    rendered: list[str] = []
    for image in images:
        if not isinstance(image, dict):
            fail("image_group images must be objects")
        rendered.append(render_figure(image, report_path, ordinal, card=True))
        ordinal += 1
    return (
        f'<div class="visual-group">{title}{caption}'
        f'<div class="visual-grid" style="--visual-columns:{columns}">{"".join(rendered)}</div></div>',
        ordinal,
    )


def render_sections(sections: list[Any], report_path: Path) -> tuple[str, list[tuple[str, str]]]:
    output: list[str] = []
    toc: list[tuple[str, str]] = []
    figure_ordinal = 1
    for index, section in enumerate(sections, 1):
        section_id = f"section-{index}"
        heading = str(section["heading"])
        toc.append((section_id, heading))
        chunks = [f'<section class="panel" id="{section_id}"><h2>{inline(heading)}</h2>']
        if section.get("lede"):
            chunks.append(f'<p class="lede">{inline(section["lede"])}</p>')
        chunks.extend(f"<p>{inline(paragraph)}</p>" for paragraph in as_list(section.get("paragraphs")))
        bullets = as_list(section.get("bullets"))
        if bullets:
            chunks.append("<ul>" + "".join(f"<li>{inline(item)}</li>" for item in bullets) + "</ul>")
        callout = section.get("callout")
        if callout:
            if not isinstance(callout, dict):
                fail("section callout must be an object")
            tone = str(callout.get("tone") or "info")
            tone_class = tone if tone in {"good", "warn"} else ""
            title = f'<h3>{inline(callout.get("title"))}</h3>' if callout.get("title") else ""
            chunks.append(f'<div class="callout {tone_class}">{title}<div>{inline(callout.get("text"))}</div></div>')
        for table in as_list(section.get("tables")):
            if not isinstance(table, dict):
                fail("section table must be an object")
            chunks.append(render_table(table))
        for figure in as_list(section.get("figures")):
            if not isinstance(figure, dict):
                fail("section figure must be an object")
            chunks.append(render_figure(figure, report_path, figure_ordinal))
            figure_ordinal += 1
        for group in as_list(section.get("image_groups")):
            if not isinstance(group, dict):
                fail("section image_group must be an object")
            rendered_group, figure_ordinal = render_image_group(group, report_path, figure_ordinal)
            chunks.append(rendered_group)
        chunks.append("</section>")
        output.append("".join(chunks))
    return "".join(output), toc


def render_list_panel(panel_id: str, heading: str, items: list[Any], tone: str = "") -> str:
    if not items:
        return ""
    tone_class = f" {tone}" if tone else ""
    body = "".join(f"<li>{inline(item)}</li>" for item in items)
    return f'<section class="panel{tone_class}" id="{panel_id}"><h2>{inline(heading)}</h2><ul>{body}</ul></section>'


def render_references(items: list[Any], source_note: str | None) -> str:
    if not items and not source_note:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("label") or not item.get("url"):
            fail("each reference needs 'label' and 'url'")
        if not is_http_url(str(item["url"])):
            fail(f"unsupported reference URL: {item['url']}")
        note = f' — {inline(item.get("note"))}' if item.get("note") else ""
        rows.append(f'<li><a href="{attr(item["url"])}" target="_blank" rel="noreferrer">{inline(item["label"])}</a>{note}</li>')
    note_html = f'<p class="lede">{inline(source_note)}</p>' if source_note else ""
    return f'<section class="panel" id="references"><h2>来源与版本</h2>{note_html}<ul class="refs">{"".join(rows)}</ul></section>'


def render_aside(data: dict[str, Any], toc: list[tuple[str, str]], created: datetime) -> str:
    tags = as_list(data.get("tags"))
    tags_html = " ".join(f'<span class="badge">{inline(tag)}</span>' for tag in tags)
    toc_html = "".join(f'<a href="#{attr(section_id)}">{inline(label)}</a>' for section_id, label in toc)
    return (
        '<div class="panel"><h3>阅读信息</h3>'
        f'<p><strong>{inline(data.get("analysis_kind") or "Paper analysis")}</strong><br>'
        f'<span class="metric-context">{created:%Y-%m-%d %H:%M %Z}</span></p>{tags_html}</div>'
        f'<div class="panel toc"><h3>目录</h3>{toc_html}</div>'
    )


class StructureChecker(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: dict[str, int] = {}
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags[tag] = self.tags.get(tag, 0) + 1
        for key, value in attrs:
            if key == "id" and value:
                self.ids.add(value)


def validate_html(document: str) -> None:
    checker = StructureChecker()
    checker.feed(document)
    for tag in ("html", "head", "body", "h1", "article"):
        if checker.tags.get(tag, 0) < 1:
            fail(f"generated HTML is missing <{tag}>")
    if "paper-reading-metadata" not in checker.ids:
        fail("generated HTML is missing archive metadata")
    visual_count = sum(checker.tags.get(tag, 0) for tag in ("table", "figure"))
    visual_count += document.count('class="flow-node"') + document.count('class="metric ')
    if visual_count < 1:
        fail("generated HTML has no visual element")


def read_metadata(report: Path) -> dict[str, Any] | None:
    text = report.read_text(encoding="utf-8")
    match = re.search(r'<script type="application/json" id="paper-reading-metadata">(.*?)</script>', text, re.S)
    if not match:
        return None
    try:
        metadata = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    metadata["file"] = report.name
    return metadata


def render_index(output_dir: Path) -> Path:
    reports: list[dict[str, Any]] = []
    for report in output_dir.glob("*.html"):
        if report.name == "index.html":
            continue
        metadata = read_metadata(report)
        if metadata:
            reports.append(metadata)
    reports.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    cards: list[str] = []
    for item in reports:
        tags = "".join(f'<span>{inline(tag)}</span>' for tag in as_list(item.get("tags")))
        paper_line = f'<div class="paper">{inline(item.get("paper_title"))}</div>' if item.get("paper_title") else ""
        cards.append(
            f'<article><div class="date">{inline(str(item.get("created_at", ""))[:10])}</div>'
            f'<h2><a href="{attr(item["file"])}">{inline(item.get("title"))}</a></h2>{paper_line}'
            f'<p>{inline(item.get("summary"))}</p><div class="tags">{tags}</div></article>'
        )
    body = "".join(cards) or '<div class="empty">No paper readings archived yet.</div>'
    document = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Casual Reading · Paper Archive</title><style>
:root{{--bg:#f3f5fb;--paper:#fff;--ink:#172033;--muted:#667085;--line:#dce2ee;--accent:#3156c8}}*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(135deg,#e5eaff,#f7f4ee 30rem);color:var(--ink);font:16px/1.65 ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}}main{{width:min(1040px,calc(100% - 32px));margin:0 auto;padding:70px 0}}header{{margin-bottom:34px}}h1{{font-size:clamp(2.4rem,6vw,5.2rem);line-height:1;letter-spacing:-.055em;margin:.2em 0}}header p{{max-width:720px;color:var(--muted);font-size:1.1rem}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px}}article,.empty{{background:var(--paper);border:1px solid var(--line);border-radius:19px;padding:23px;box-shadow:0 10px 35px rgba(32,49,83,.06)}}h2{{font-size:1.3rem;line-height:1.25;margin:.4em 0}}a{{color:var(--accent);text-decoration:none}}a:hover{{text-decoration:underline}}.date,.paper{{color:var(--muted);font-size:.82rem}}.paper{{font-weight:700}}.tags{{display:flex;flex-wrap:wrap;gap:7px;margin-top:16px}}.tags span{{background:#edf1ff;color:#344da1;border-radius:999px;padding:4px 8px;font-size:.75rem;font-weight:700}}@media(prefers-color-scheme:dark){{:root{{--bg:#101827;--paper:#192235;--ink:#e7edf8;--muted:#aab5c8;--line:#34415a;--accent:#9db1ff}}body{{background:linear-gradient(135deg,#131d3a,#101827 30rem)}}.tags span{{background:#26365f;color:#ccd6ff}}}}
</style></head><body><main><header><div>CASUAL READING</div><h1>Paper archive</h1><p>Visual notes, method breakdowns, evidence boundaries, and comparisons saved from paper-reading conversations.</p></header><section class="grid">{body}</section></main></body></html>'''
    index_path = output_dir / "index.html"
    index_path.write_text(document, encoding="utf-8")
    return index_path


def create_report(data: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    validate_payload(data)
    now = datetime.now().astimezone()
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = allocate_report_path(output_dir, data, now)

    sections_html, toc = render_sections(as_list(data.get("sections")), report_path)
    key_points = as_list(data.get("key_points"))
    pipeline = as_list(data.get("pipeline"))
    metrics = as_list(data.get("metrics"))
    limitations = as_list(data.get("limitations"))
    boundaries = as_list(data.get("evidence_boundaries"))
    references = as_list(data.get("references"))

    article = "".join(
        [
            render_key_points(key_points),
            render_pipeline(pipeline),
            render_metrics(metrics),
            sections_html,
            render_list_panel("limitations", "局限与开放问题", limitations),
            render_list_panel("evidence-boundaries", "证据与推断边界", boundaries),
            render_references(references, data.get("source_note")),
        ]
    )
    complete_toc: list[tuple[str, str]] = []
    if key_points:
        complete_toc.append(("key-points", "核心结论"))
    if pipeline:
        complete_toc.append(("pipeline", "方法脉络"))
    if metrics:
        complete_toc.append(("metrics", "关键证据"))
    complete_toc.extend(toc)
    if limitations:
        complete_toc.append(("limitations", "局限与开放问题"))
    if boundaries:
        complete_toc.append(("evidence-boundaries", "证据与推断边界"))
    if references or data.get("source_note"):
        complete_toc.append(("references", "来源与版本"))

    paper = data.get("paper") if isinstance(data.get("paper"), dict) else {}
    metadata = {
        "title": data["title"],
        "summary": data["summary"],
        "created_at": now.isoformat(timespec="seconds"),
        "paper_title": paper.get("title"),
        "paper_url": paper.get("url"),
        "analysis_kind": data.get("analysis_kind"),
        "tags": as_list(data.get("tags")),
    }
    metadata_json = json.dumps(metadata, ensure_ascii=False).replace("<", "\\u003c")
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    replacements = {
        "{{LANG}}": attr(data.get("language") or "zh-CN"),
        "{{META_TITLE}}": attr(data["title"]),
        "{{META_SUMMARY}}": attr(data["summary"]),
        "{{CREATED_AT}}": attr(metadata["created_at"]),
        "{{DOCUMENT_TITLE}}": attr(data["title"]),
        "{{HERO}}": render_hero(data),
        "{{ARTICLE}}": article,
        "{{ASIDE}}": render_aside(data, complete_toc, now),
        "{{CREATED_DISPLAY}}": now.strftime("%Y-%m-%d %H:%M %Z"),
        "{{METADATA_JSON}}": metadata_json,
    }
    document = template
    for token, value in replacements.items():
        document = document.replace(token, value)
    leftover = re.findall(r"\{\{[A-Z_]+\}\}", document)
    if leftover:
        fail(f"unresolved template tokens: {', '.join(leftover)}")
    validate_html(document)
    report_path.write_text(document, encoding="utf-8")
    index_path = render_index(output_dir)
    if report_path.name not in index_path.read_text(encoding="utf-8"):
        fail("index was generated but does not link the new report")
    return report_path, index_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="UTF-8 JSON payload")
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd(), help="workspace containing casual_reading/")
    parser.add_argument("--output-dir", type=Path, help="explicit output directory; overrides --workspace-root")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = args.input.expanduser().resolve()
    data = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        fail("top-level JSON value must be an object")
    output_dir = (args.output_dir or (args.workspace_root / "casual_reading")).expanduser().resolve()
    report, index = create_report(data, output_dir)
    print(json.dumps({"report": str(report), "index": str(index)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
