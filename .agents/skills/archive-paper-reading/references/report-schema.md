# Report payload schema

Create one UTF-8 JSON object. `title`, `summary`, `sections`, and rich visuals are required.

## Top-level fields

| Field | Type | Purpose |
|---|---|---|
| `title` | string | Report title |
| `summary` | string | One-sentence conclusion |
| `slug` | string | Optional filename hint |
| `language` | string | HTML language; default `zh-CN` |
| `analysis_kind` | string | Method analysis, comparison, reproduction notes, etc. |
| `visual_policy` | string | `standard` (default, at least 2 rich visuals) or `compact` (at least 1) |
| `paper` | object | `title`, `url`, `authors`, `venue`, `year`, `identifiers` |
| `tags` | string[] | Search labels |
| `key_points` | string[] | Three to six takeaways |
| `pipeline` | object[] | Lightweight HTML flow nodes; helpful but not a rich visual |
| `metrics` | object[] | Metric cards; helpful but not a rich visual |
| `sections` | object[] | Main analysis sections |
| `limitations` | string[] | Limitations and unresolved questions |
| `evidence_boundaries` | string[] | Facts vs inference and missing ablations |
| `references` | object[] | `label`, `url`, optional `note` |
| `source_note` | string | Version/data note |

For a multi-paper report, the skill-level quality gate requires at least three rich visuals even though the generator's `standard` policy validates a minimum of two.

## Section fields

Each section supports:

- `heading`: required string
- `lede`: highlighted introduction
- `paragraphs`: string array
- `bullets`: string array
- `callout`: `{title, text, tone}` where tone is `info`, `good`, or `warn`
- `tables`: array of `{caption, headers, rows}`
- `figures`: full-width figure array using the figure fields below
- `image_groups`: comparison/gallery arrays using the group fields below

Inline text supports `**bold**`, `*italic*`, `` `code` ``, and `[label](https://...)`.

## Figure fields

```json
{
  "src": "/tmp/paper-figures/figure-2.png",
  "alt": "Overview of the two-stage architecture",
  "caption": "Figure 2. The generator produces multi-view latents consumed by the reconstructor.",
  "source_url": "https://arxiv.org/html/0000.00000#S3.F2",
  "role": "architecture",
  "source_kind": "paper"
}
```

- `src`: local path preferred; HTTP(S) is allowed as a fallback
- `role`: `architecture`, `qualitative`, `quantitative`, `ablation`, `failure`, `concept`, or `other`
- `source_kind`: `paper`, `project`, `screenshot`, `redrawn`, or `chart`
- `caption` and `source_url` are required for paper/project/screenshot images
- Label generated visuals as `redrawn` or `chart` and cite their source sections/tables in the caption

## Image group fields

Use image groups for side-by-side qualitative comparisons or several related panels:

```json
{
  "title": "Qualitative comparison",
  "caption": "Same input and camera path across methods.",
  "columns": 2,
  "images": [
    {"src": "/tmp/baseline.png", "alt": "Baseline", "caption": "Baseline", "role": "qualitative", "source_kind": "paper", "source_url": "https://..."},
    {"src": "/tmp/ours.png", "alt": "Ours", "caption": "Ours", "role": "qualitative", "source_kind": "paper", "source_url": "https://..."}
  ]
}
```

An image group counts as one rich visual regardless of how many panels it contains.

## Minimal example

```json
{
  "title": "How the method connects generation and reconstruction",
  "summary": "A stable video latent is the shared interface.",
  "slug": "generation-reconstruction",
  "visual_policy": "standard",
  "paper": {"title": "Example Paper", "url": "https://arxiv.org/abs/0000.00000"},
  "key_points": ["Generation fills unseen regions.", "Reconstruction makes the result persistent."],
  "sections": [
    {
      "heading": "Architecture",
      "paragraphs": ["Explain the evidence and consequence."],
      "figures": [
        {"src": "/tmp/figure-2.png", "alt": "Architecture", "caption": "Figure 2. System overview.", "source_url": "https://arxiv.org/html/0000.00000#S3.F2", "role": "architecture", "source_kind": "paper"},
        {"src": "/tmp/result-chart.svg", "alt": "Result comparison", "caption": "Redrawn from Table 3; higher is better.", "source_url": "https://arxiv.org/html/0000.00000#S4.T3", "role": "quantitative", "source_kind": "chart"}
      ]
    }
  ],
  "limitations": ["The modules are not optimized end-to-end."],
  "evidence_boundaries": ["The paper does not ablate a joint-training alternative."],
  "references": [{"label": "Paper", "url": "https://arxiv.org/pdf/0000.00000"}]
}
```
