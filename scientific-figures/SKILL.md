---
name: scientific-figures
description: Build publication-grade schematic figures for scientific manuscripts (mechanism of action, pathways, clinical algorithms, study designs, reporting flow diagrams, graphical abstracts) as deterministic vector output, composed from open-licensed assets under an enforced licence gate. Use when a figure, diagram, schematic or graphical abstract is needed for a paper, preprint, grant or slide deck. Do not use for data figures (Kaplan-Meier, forest, waterfall, box plots), which must come from the analysis code.
---

# Scientific figures

Compiles a declarative figure specification into journal-ready SVG. The skill is a compiler, not an image generator: the same source yields the journal variant, the slide variant and the thumbnail, and every pictorial asset resolves to a licence-checked entry in the registry.

## Hard rules

These are refusals, not preferences. Violating any of them produces a figure that is unusable, unpublishable or dishonest.

1. **No data figures.** Kaplan-Meier curves, forest plots, waterfall plots, box plots and any other representation of measured values are produced by the analysis code, never here. A data figure drawn separately from the analysis can silently diverge from it. Redirect the user to their statistical pipeline.
2. **No raster generative output.** Everything is vector, authored as SVG from the specification. Several publishers restrict or forbid AI-generated imagery; a deterministic vector drawing compiled from a declared source is a technical drawing, not a generated image. See `references/03-journal-and-policy.md`.
3. **No unregistered asset.** Every pictorial element resolves to an entry in `assets/sources.json`. No entry, no asset. Never improvise an illustration from an unknown source.
4. **No KEGG map images.** Topology from KGML may inform a redrawn figure, declared as a redraw. The map image itself is never embedded. See the registry entry.
5. **No relation without an evidence level.** Every arc carries `evidence`. The compiler refuses to render otherwise. This is the discipline that keeps a hypothesis visually distinct from a demonstrated mechanism.
6. **Band A figures must balance.** Participant flow diagrams fail compilation if the counts do not sum at every level.

## Workflow

1. **Classify.** Determine the normative band (A, B, C) and the figure class from `references/01-figure-taxonomy.md`. The band decides how much latitude the renderer has and which validator runs.
2. **Establish the claim.** Before any drawing, state in one sentence what the figure asserts, and for each relation whether it is established, demonstrated here, associated or hypothesised. If the user cannot state this, the figure is not ready to be drawn.
3. **Write the spec.** Produce a `figure-spec` document (`schema/figure-spec.schema.json`, YAML or JSON) holding entities, relations, compartments and the metadata block. Content first, layout second.
4. **Resolve assets.** For each entity that calls for a pictogram, query the registry in `resolution_order`, apply the licence gate against `meta.target`, and record source, asset id, author and licence in the provenance block. Geometric entities need no asset.
5. **Render.** Compile to SVG using the glyph vocabulary in `references/02-visual-lexicon.md`, at the dimensions required by `meta.target` (`references/03-journal-and-policy.md`).
6. **Validate.** Run the checks in the validation section below before returning anything.
7. **Emit the paratext.** Draft caption, attribution block and, where the user asks for it, the AI disclosure statement for the target publisher. These are generated from the spec, not written by hand.

## Validation checks

- Licence gate passed for every asset against the declared target.
- Every relation has `evidence` and, where not `demonstrated_here`, a `source`.
- One accent colour only; canonical background rendered in neutral grey.
- Legend present and auto-generated whenever more than four lexicon elements are used.
- No text below 6 pt at final size; 12 pt minimum inside a graphical abstract.
- Thumbnail test: render at 25 percent and confirm the main message survives.
- Band A only: arithmetic closure of all counts.
- Colour check: the figure remains readable converted to greyscale and under a deuteranopia simulation.

## Asset strategy

The registry in `assets/sources.json` is the single point of truth. In short: Health Icons (CC0) for clinical pictograms, Bioicons (per-item, JSON index, vector) for molecular and cellular iconography, NIH BioArt for anatomically demanding illustration, SciDraw for experimental setups, PhyloPic (REST API) for organism marks, Servier Medical Art last because it serves raster only, Reactome and WikiPathways for pathway topology rather than pictures. BioRender stays outside the pipeline as an optional external path with its own licensing.

Cache the Bioicons index and the PhyloPic queries locally; both are designed for programmatic access and both encode licence per item, which is what makes the gate cheap to enforce.

## Renderer

```
python render/figure_render.py spec.yaml -o figure.svg --caption caption.md
python render/figure_render.py spec.yaml --variant slide -o slide.svg
python render/figure_render.py spec.yaml --check
```

Python 3.9 or later, PyYAML only if the spec is YAML. No network, no layout engine, no model: one spec always compiles to the same drawing.

Three behaviours worth knowing. Nodes whose only role is to inhibit or catalyse are lifted out of the reading line and placed above their target, which is how such figures are drawn by hand and keeps the arrow from crossing whatever sits between them. Feedback arcs are routed along a clear lane below both nodes rather than across the figure. And type size is treated as a hard floor: the compiler tightens the gutters until the body type clears 6 pt at the target width, 12 pt inside a graphical abstract, and refuses the figure if tightening is not enough, telling the user to reduce the number of semantic units or split it. A figure that cannot be set legibly at column width is not a rendering problem, it is a content problem.

## Files

- `references/01-figure-taxonomy.md` — figure classes, normative bands, per-class invariants
- `references/02-visual-lexicon.md` — the normative glyph vocabulary
- `references/03-journal-and-policy.md` — target specifications, AI disclosure, accessibility
- `schema/figure-spec.schema.json` — the intermediate representation
- `assets/sources.json` — open asset registry and licence gate
- `assets/figure-lexicon-v0.1.svg` — rendered reference plate of the lexicon
- `examples/moa-example.yaml` — worked specification
