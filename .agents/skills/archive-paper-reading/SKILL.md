---
name: archive-paper-reading
description: Read, summarize, analyze, explain, compare, critique, or survey academic papers and archive every such conversation as a visual HTML report under the current workspace's casual_reading/ directory. Save paper-native framework, qualitative, comparison, and result figures when available; capture/crop PDF pages when needed; and draw sourced SVG architecture diagrams or charts when originals are unavailable. Use for any paper-related request or follow-up involving an arXiv/preprint/PDF/publication, including method breakdowns, experiment or figure analysis, literature comparisons, technical-choice reasoning, limitations, reproduction notes, and related-work research. Always create the HTML artifact in addition to answering the user.
---

# Archive Paper Reading

Treat the HTML artifact as part of the answer, not an optional afterthought. A paper-reading turn is incomplete until a new report exists under `<workspace-root>/casual_reading/` and its path is included in the final response.

## Workflow

1. Read the paper and supporting material needed for the request. Separate paper-stated facts, measured evidence, and your own inference.
2. Read [references/visual-workflow.md](references/visual-workflow.md) and collect the visual evidence before drafting. Prefer paper-native figures; use PDF screenshots/crops when the HTML/project assets are unavailable; draw a sourced SVG only as a fallback or synthesis.
3. Plan a reader-friendly report. Include:
   - a one-sentence conclusion;
   - paper metadata and source links;
   - the requested analysis rather than a generic abstract rewrite;
   - enough substantive visual evidence to meet the visual quality gate below;
   - limitations, uncertainty, and attribution boundaries when relevant.
4. Read [references/report-schema.md](references/report-schema.md), create a JSON payload in a temporary directory, and populate only fields supported by evidence.
5. Run:

   ```bash
   python3 <skill-dir>/scripts/create_report.py \
     --input <payload.json> \
     --workspace-root <workspace-root>
   ```

   Resolve `<skill-dir>` to this skill folder. Resolve `<workspace-root>` from the environment context; otherwise use the repository root, then the current working directory.
6. Verify the command exits successfully, the reported HTML file exists, and `casual_reading/index.html` links to it. Open the HTML in a browser when browser tooling is available; otherwise run the script's built-in structural validation and inspect the title, visuals, captions, and main sections.
7. Give the user the analysis and a clickable absolute link to the HTML report. Mention important evidence/interpretation boundaries in both places.

## Visual quality gate

- For a substantive single-paper analysis, include at least **two rich visuals**: normally one system/framework/method visual and one qualitative comparison, ablation, or key-result visual.
- For a multi-paper comparison, include at least **three rich visuals**: at least one visual from each paper plus one original comparison/decision diagram or transcribed chart.
- For a narrowly scoped follow-up, set `visual_policy` to `compact` and include at least one directly relevant rich visual.
- Paper-native images, PDF screenshots/crops, image comparison groups, and generated SVG diagrams/charts count as rich visuals. Metric cards, plain HTML pipelines, and numeric tables alone do **not** satisfy this gate.
- Every saved/captured figure must include its paper figure number or page, a useful caption, and a source URL. Every redrawn visual must be labeled `redrawn` or `chart` and cite the sections/tables it synthesizes.

## Report rules

- Create one new page for every paper-analysis conversation or substantive paper follow-up. Let the script add a numeric suffix if a same-day slug already exists.
- For a multi-paper comparison, create one comparison page covering the whole request. Do not create boilerplate duplicate pages unless the user asks for separate reports.
- Use the user's language for the report unless requested otherwise.
- Do not add decorative stock imagery. Select figures that explain architecture, information flow, qualitative behavior, failure cases, comparisons, or measured effects.
- Use `scripts/collect_html_figures.py` to collect candidates from arXiv HTML/project pages, `scripts/capture_pdf_visual.py` to render/crop PDF pages, and `scripts/draw_visual.py` to create SVG architecture diagrams or grouped bar charts. Read `references/visual-workflow.md` for commands and provenance rules.
- Review collected candidates and include only relevant figures. Never dump all paper figures into the report.
- Never imply a causal conclusion that the paper did not ablate. Label strong design reasoning as analysis or inference.
- Keep the page self-contained and readable without external CSS or JavaScript. Remote paper images are allowed only when a local copy cannot reasonably be obtained.
- Preserve existing reports. Do not overwrite a page unless the user explicitly requests an update.

## Completion contract

Before finishing, confirm all of the following:

- The requested paper analysis is answered.
- A new `.html` page exists inside `casual_reading/`.
- The page contains a summary, substantive analysis, sources, and the required number/types of rich visuals.
- Original figures/screenshots have captions and source URLs; redrawn diagrams/charts disclose that they are synthesized.
- `casual_reading/index.html` includes the page.
- The final response links the generated page.

If the filesystem is unavailable, state that the archive step could not be completed and why; do not silently skip it.
