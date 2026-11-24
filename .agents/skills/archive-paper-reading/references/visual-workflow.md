# Visual evidence workflow

## Selection order

1. **Paper-native figures:** system overview, architecture, key qualitative comparison, ablation, failure cases, or the most important result plot.
2. **Project-page media:** use when higher-resolution or animated comparisons explain behavior better; preserve the project URL.
3. **PDF screenshot/crop:** use when HTML assets are missing or a table/figure is embedded in the PDF.
4. **Redrawn SVG:** use for synthesis, decision logic, or when originals are inaccessible. State that it is redrawn and cite the source sections/tables.

Do not treat metric cards, plain HTML pipelines, or numeric tables as sufficient rich visuals.

## Collect from HTML

```bash
python3 <skill-dir>/scripts/collect_html_figures.py \
  --url https://arxiv.org/html/0000.00000 \
  --output-dir <temporary-dir>/figures \
  --max 8
```

The command writes `manifest.json` and prints it. It ranks likely overview, architecture, method, comparison, qualitative, ablation, result, and failure figures. Review the candidates; do not include them blindly. Use `--include 2,5` to request exact figure numbers when known.

## Capture or crop PDF pages

Find likely pages first:

```bash
pdftotext -layout paper.pdf - | rg -n "Figure|Table|Overview|Architecture|Comparison"
```

Then render a full page or crop in rendered-pixel coordinates:

```bash
python3 <skill-dir>/scripts/capture_pdf_visual.py \
  --pdf paper.pdf --page 3 --page 7 \
  --output-dir <temporary-dir>/pdf-pages \
  --source-url https://arxiv.org/pdf/0000.00000

python3 <skill-dir>/scripts/capture_pdf_visual.py \
  --pdf paper.pdf --crop '3:120,260,1500,880' \
  --output-dir <temporary-dir>/pdf-crops \
  --source-url https://arxiv.org/pdf/0000.00000
```

`--crop` format is `page:x,y,width,height` at the selected DPI (default 160). Check the crop with an image viewer before including it.

The script requires `pdftoppm`. If it is unavailable, do not install system packages without authorization; prefer arXiv HTML/project-page assets or use an already available browser screenshot facility, then pass the saved image to the report payload.

## Draw a framework diagram or chart

Create a JSON spec, then run:

```bash
python3 <skill-dir>/scripts/draw_visual.py \
  --input visual.json --output visual.svg
```

Supported types:

- `flow`: nodes with explicit `column`/`row`, plus directed edges
- `bar`: grouped bar chart with categories and series

Use a generated SVG as a normal report figure with `source_kind: redrawn` or `chart`. Its caption must name the sections/tables used as evidence.

## Provenance and integrity

- Preserve paper figure numbers and captions when possible.
- Link to the exact HTML anchor or PDF URL/page.
- Never alter a paper figure in a way that changes its scientific meaning.
- Label crops as screenshots and original diagrams/charts as redrawn/transcribed.
- If a qualitative comparison is split into panels, keep method labels visible or add truthful labels in the HTML image group.
- Mention when a visual is schematic rather than a measured result.
