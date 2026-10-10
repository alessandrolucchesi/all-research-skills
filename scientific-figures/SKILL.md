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

## Purpose decides what colour is for

`meta.purpose` is the first thing to settle, because it assigns the colour budget.

`primary_research` (the default) keeps the original rule: colour encodes narrative role, neutral grey for cited background and one accent for the contribution of this work. A figure that claims something needs that channel, and it is what keeps a hypothesis from being drawn as a finding.

`explanatory` is for a figure that claims no novelty, the ordinary review mechanism figure. There colour is freed for entity identity, assigned from a fixed deuteranopia-safe palette, with entities sharing an `identity` key sharing a hue. This is what published mechanism figures do, and applying the role rule to such a figure spends the whole colour budget on a channel it does not use, which is why review output otherwise reads as a wireframe.

Under both purposes: one variable per channel, evidence always on stroke pattern (a proposed link is dotted in a review figure too, the honesty channel is never the one traded away), arcs stay neutral so the reader does not hunt for a meaning in a tinted arc, and the greyscale and deuteranopia checks still apply.

## Composition devices

`qualifier` on an entity is set smaller and lighter beneath the name: components, units, a defining detail. It is how a published figure separates the thing from its parts, and it shortens the primary label, which relieves the width constraint.

`prominence`, three levels, is a weight channel: stroke, glyph and type size, defaulting from the ontology family so an organ is not drawn at the size of a metabolite. It is not colour, so the colour rule is untouched.

Labels wrap rather than stretch their column. A published algorithm box carries far more than three words.

A pictorial entity is always one bounded container with the art inside it and the label beneath, whether the art is a resolved pictogram or the class's generic glyph. An icon left loose above a bare caption reads as decoration standing beside the diagram rather than as the entity.

## Entity ontology

Two axes, kept apart. Conflating them is what broke v0.2: `cell` meant both "a cell" and "a pictogram goes here", so an entity with no icon lost its semantics and the author's rational move was to relabel it a macromolecule to obtain a clean box.

**Class**, what the thing is, by scale. Molecular: `small_molecule`, `macromolecule`, `nucleic_acid`, `complex`. Cellular and structural: `organelle`, `cell`, `cell_population`, `tissue`, `organ`, `organism`. Process and state: `process`, `state`, `measure`. Procedural: `step`, `intervention`. And `unspecified`, which means an identity the author declines to state and nothing else. Reach for it rarely: a clone is a `cell_population`, a resistance or a pressure is a `measure`, a confirmed diagnosis is a `state`, a drug or a device is an `intervention`.

**Depiction**, how it is drawn: `auto`, `geometric` or `pictogram`. The class proposes, the spec disposes.

**Substitution rule: generalise up, never sideways.** When the exact asset is missing, an asset for a more general term may stand in and the label carries the identity: a generic cell for a megakaryocyte is honest, because the label says which cell. A coordinate term never may: a basophil for a neutrophil is a misstatement, not an approximation. Each class carries a short curated list of acceptable generic assets, because no lexical rule can tell a generic from a qualified sibling ("blood-cells" is a legitimate stand-in for a neutrophil, "cancerous-cell_nuclei" is not, and nothing in the two strings says which).

**Adaptation is allowed and recorded.** Every licence the gate admits permits derivatives, which is what makes recolouring, scaling, mirroring, cropping, composition and generic substitution legitimate. Each is written to `provenance.assets[].adaptations` and surfaces in the credit line as "Adapted from ... Changes: ...", which CC BY requires anyway. Classes with no library match fall back to a built-in generic glyph drawn by this project, so no entity is ever reduced to an anonymous box for want of an icon.

## Output

The format follows the kind of figure, not a preference. Diagrams and flows, the figures co-authors revise, export to **PPTX with native shapes and connectors**, because revision is where a figure lives and nobody revises an SVG. Pictographic representations export to **SVG plus PNG**, where the artwork is the content and editability buys nothing. Both come from the same layout, so they cannot drift.

```
python render/figure_export.py spec.yaml --resolve-assets
python render/figure_export.py spec.yaml --formats svg,png,pptx
```

Decision procedures and reporting flows are laid out down the page, not across it; `meta.orientation` overrides.

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

The registry in `assets/sources.json` is the single point of truth. Health Icons (CC0, 749 entries with curated tags) first, because no attribution obligation means no composite-level bookkeeping. Bioicons second (2804 entries; the licence is carried in the directory path, not the filename), and this is where the resolver finds most clinical subjects, since the 1373 Servier icons mirrored there are genuine vector under CC-BY-3.0. The `servier-smart` entry stays last only because the direct site serves raster. NIH BioArt, SciDraw, Open Science Art and PhyloPic have no machine index wired yet and are resolved by hand through `asset:`. Reactome and WikiPathways supply topology, not pictures. BioRender stays outside the pipeline.

Two gates run on every candidate, in this order: the licence gate against `meta.target`, then a vector gate. The second is not optional. A licence-clean SVG can still wrap an embedded raster, which produces a raster island inside the drawing and fails at print resolution; the registry cannot carry the flag because it is a property of the file. The outcome is recorded as `vector: true` in provenance.

## Renderer

```
python render/figure_render.py spec.yaml -o figure.svg --caption caption.md
python render/figure_render.py spec.yaml --resolve-assets -o figure.svg
python render/figure_render.py spec.yaml --strict-assets -o figure.svg
python render/figure_render.py spec.yaml --variant slide -o slide.svg
python render/figure_render.py spec.yaml --check
python render/asset_resolver.py --search megakaryocyte --show-rejected
```

Python 3.9 or later, PyYAML only if the spec is YAML. No network, no layout engine, no model: one spec always compiles to the same drawing.

Behaviours worth knowing.

Nodes whose only role is to inhibit or catalyse are lifted out of the reading line and placed above their target, which is how such figures are drawn by hand and keeps the arrow from crossing whatever sits between them.

Arcs are diverted into a clear horizontal lane whenever the straight path would cross another glyph, tested geometrically rather than guessed from rank distance: feedback below, long forward arcs above, so the two remain distinguishable. A rank-span rule would both miss a short arc that passes over a node and divert a long one that passes over nothing.

Type size is a hard floor. The compiler tightens the gutters until body type clears 6 pt at the target width, 12 pt inside a graphical abstract, and refuses otherwise, naming the binding constraint: the number of rank columns, not the entity count. Merging two adjacent ranks keeps all the content; removing entities loses it.

Every glyph is sized from one text-metrics function. The `process` class is the SBGN square carried on an arc, with its label beside it; a labelled box in an algorithm or study design is the `step` class.

`--resolve-assets` fetches pictograms from the open registry. Only an exact match on a catalogue name or tag is accepted without confirmation, because a near match on a cell type is a misstatement rather than an approximation; weaker matches are reported as candidates to confirm with an explicit `asset:`. When nothing resolves, the entity is drawn as a plain solid outline and a warning names the terms tried. It is never drawn dashed: dashed means "unspecified" in the lexicon, and overloading it to mean "the resolver found nothing" invites the author to downgrade a cell to a macromolecule just to get a clean box, which corrupts the semantics to work around a tool limitation. Canonical pictograms are desaturated at the colour values, not with an SVG filter, so the colour channel cannot be reclaimed by an imported icon in a PDF or EPS conversion.

## Files

- `references/01-figure-taxonomy.md` — figure classes, normative bands, per-class invariants
- `references/02-visual-lexicon.md` — the normative glyph vocabulary
- `references/03-journal-and-policy.md` — target specifications, AI disclosure, accessibility
- `schema/figure-spec.schema.json` — the intermediate representation
- `assets/sources.json` — open asset registry and licence gate
- `assets/figure-lexicon-v0.1.svg` — rendered reference plate of the lexicon
- `render/ontology.py` — entity classes, depiction, substitution rule, generic glyphs
- `render/asset_resolver.py` — pictogram resolution, licence gate, vector gate
- `render/figure_export.py` — SVG, PNG and PPTX output
- `examples/moa-example.yaml` — worked specification
- `examples/pictogram-example.yaml` — resolved pictograms, generic substitution, lane routing
- `examples/algorithm-example.yaml` — vertical clinical algorithm, PPTX output
