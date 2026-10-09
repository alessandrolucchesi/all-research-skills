# scientific-figures

A skill for building publication-grade schematic figures: mechanisms of action, pathways, clinical algorithms, study designs, reporting flow diagrams and graphical abstracts.

Three design decisions distinguish it from an illustration tool.

**It is a compiler, not a generator.** Figures are written as a declarative specification (`schema/figure-spec.schema.json`) and compiled to deterministic vector output. One source produces the journal variant, the slide variant and the thumbnail. Nothing passes through a generative image model, which keeps the output inside the 2026 publisher policies on AI imagery and makes every figure reproducible from source.

**It knows the epistemic status of what it draws.** Every relation carries a mandatory `evidence` field with values established, demonstrated here, associated or hypothesised, rendered through a dedicated visual channel. A proposed mechanism cannot be drawn as a demonstrated one by accident, and the caption draft is generated from the same field.

**It enforces licensing in code.** Every pictorial asset resolves to an entry in `assets/sources.json`, drawn from open libraries (Health Icons, Bioicons, NIH BioArt, SciDraw, PhyloPic, Open Science Art, Servier Medical Art, Reactome, WikiPathways). A licence gate refuses no-derivative, share-alike and non-commercial assets for publication targets, and refuses KEGG map images outright. The attribution block is generated, not remembered.

Start at `SKILL.md`.

## Quickstart

```bash
python render/figure_render.py examples/moa-example.yaml -o figure.svg --caption caption.md
python render/figure_render.py examples/moa-example.yaml --check      # validate only
```

Python 3.9 or later. PyYAML is needed only for YAML specs; JSON specs run on the standard library alone.

![Figure compiled from examples/moa-example.yaml](examples/moa-example.png)

The figure above is compiled entirely from `examples/moa-example.yaml`, with no manual adjustment of the geometry. The dotted arc with the unfilled head is a proposed feedback; the solid blue arcs are what the work claims to show; everything grey is cited background.

## Status and limitations

Version 0.2, after the first production use. The renderer covers band B (mechanism of action, pathways, study designs, clinical algorithms). Band A, the standard-conformant reporting diagrams with their arithmetic validator, and band C, the journal-dimensioned canvas, are specified in `references/01-figure-taxonomy.md` but not yet implemented; the validator refuses a band A figure rather than improvising one.

New in 0.2: pictogram resolution against Bioicons and Health Icons, with a vector gate alongside the licence gate and exact-match-only auto-acceptance; one text-metrics function for every glyph; a `step` class distinct from the SBGN `process`; arcs diverted into a clear lane by geometric intersection rather than by rank distance; desaturation of canonical pictograms applied to colour values; a refusal message that names the binding constraint.

Known limits: output is SVG only, so a figure that co-authors must revise still leaves the pipeline; there are no panels, which makes "split the figure" advice the tool cannot execute; NIH BioArt, SciDraw, Open Science Art and PhyloPic have no machine index wired and are resolved by hand through `asset:`; relation labels are placed without collision avoidance except on lane-routed arcs; the lexicon has no glyph class for a measured physiological quantity, which currently falls back to `unspecified`.

## Citing

`CITATION.cff` carries the metadata. Please cite the version you used.

## Layout

```
SKILL.md                              entry point, hard rules, workflow
render/figure_render.py               spec to SVG compiler (band B)
references/01-figure-taxonomy.md      figure classes, normative bands, invariants
references/02-visual-lexicon.md       normative glyph vocabulary
references/03-journal-and-policy.md   target specifications, AI policy, accessibility
schema/figure-spec.schema.json        intermediate representation
assets/sources.json                   open asset registry and licence gate
assets/figure-lexicon-v0.1.svg        rendered reference plate
render/asset_resolver.py              pictogram resolution, licence and vector gates
examples/moa-example.yaml             worked specification
examples/pictogram-example.yaml       resolved pictograms and lane routing
examples/moa-example.journal.svg      its compiled output
CITATION.cff                          citation metadata
LICENSE / LICENSING.md                MIT for code, CC BY 4.0 for the plates
```
