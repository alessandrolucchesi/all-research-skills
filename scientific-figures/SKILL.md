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

## Two layout engines

`meta.layout` picks one, and the choice is not cosmetic.

**flow** ranks entities topologically and puts rank N in column N. Right for algorithms, study designs and reporting diagrams, where the reader follows a procedure and there is no anatomy to show. The published exemplars confirm it: a clinical algorithm is boxes and arrows, monochrome, and should stay that way.

**anatomical** places an entity inside whatever contains it. Position carries location, arcs carry causality, and rank only orders siblings within one region. This is the engine for mechanisms and pathways, and it exists because the flow engine makes position encode what the arrows already encode, which leaves nothing to say where the reader is: a glyph whose only reason to be in column three is that it is third in a chain has nothing to draw around it, so it gets a box.

Either engine can be partitioned. `meta.phases` divides the canvas into bands along one axis, each entity declaring which phase it occupies, and each band is laid out by the engines above, so one phase can hold a containment scene and the next a flow. Three of the four published exemplars studied are built this way: before and after treatment, first line and relapse, control and disease. The reader takes position along the axis as meaning, which is why a phase is a band of the canvas and not a colour or a note.

A partition has already spent the horizontal axis, so content inside a band reads downwards unless `meta.orientation` says otherwise; laid out sideways, three bands of four ranks put the type under the legibility floor. Name the axis in `meta.phase_axis` when it is ordered and a single arrow is drawn under the bands; omit it for an unordered partition such as side-by-side conditions, where an arrow would assert a progression the figure does not claim. A structure and its contents occupy the same phase, and something that persists across phases is drawn once in each with a relation between the two, which is what the validator enforces: the same glyph cannot straddle two phases, because its position would then mean nothing.

A container is simply an entity with contents (`contains`, or children declaring `inside`), so a macrophage can hold a kinase and still be drawn as a macrophage. Three slots, deliberately not named after any anatomy so the same construct serves a cell, a vessel, a reactor or a catchment: `interior` by default, `boundary` for anything straddling the edge, and nested containers for the rest. The ontology's scale ladder validates containment, a container must stand higher than its contents, and sets default sizes so an organ is not drawn at the size of a metabolite.

## Depict, do not box

In an anatomical figure a glyph is a drawing unless there is nothing to draw it with. Counting the Frontiers inflammasome figure, five of about forty entities sit in a box and the rest are drawings with a label beside them, and that ratio is most of the distance between a diagram and a figure. So in `anatomical` layout every class attempts resolution, not only the pictogram classes, and a resolved entity loses its box: the drawing is the glyph, the label sits under it.

`process`, `step`, `state` and `measure` keep their geometric glyphs, because for those the shape carries the meaning and a picture would not. An entity may also be forced back with `depiction: geometric`, and one that resolves nothing stays a labelled box, which is the right answer for something like a kinase that has no standard depiction.

Resolution reaches these entities through head-noun generalisation: "Fc receptor" is a kind of receptor, so an asset whose name contains the query's head noun is a legitimate generalisation and the label specialises it. The same rule still refuses a basophil for a neutrophil, whose head noun is the whole word. String containment is weighted by coverage, after "autoantibody" once resolved to a drawing of a human body on the strength of the letters in "body".

Two entities may share a drawing when both are generic substitutes, because a generic receptor on two different cells is how published figures draw it and the label and container carry the identity. An exact match stays exclusive: there the drawing itself makes the claim.

## Where anatomy comes from

Not from hand-drawn templates: that would tie the tool to whichever field drew them. Container geometry is ours and neutral, four shapes. Anatomical identity comes from the open libraries as an `anchor`, a silhouette drawn faint behind the contents, resolved by term through the same licence and vector gates as any other asset. A container with contents and no stated anchor asks for one under its own label. This is where the generality lives: a lung for a haematologist, a leaf for a botanist, a fermenter for a bioprocess engineer, with no code change.

A container is drawn, not outlined. When its asset is a frame, a library shape whose convex hull encloses an empty middle, it is drawn at full strength and the contents go in that middle: the libraries ship real empty cells, whose membrane is a ring of phospholipid dots, and the measurement finds them with no curated list. When the asset is a solid mark with a usable inscribed region, the silhouette is traced and that outline is stroked at full strength with a pale interior, so the contents sit in the lumen of a drawn cell. Only where neither applies does the neutral geometry carry the anchor behind.

The traced outline is the derivative that stops a container being wallpaper. A library cell is a solid dark drawing; to put a label on it you have to fade it, and a faded drawing reads as decoration behind the diagram rather than as the structure the diagram is about. Taking the outline and discarding the fill is a transformation the licence gate permits and the store records, and it is what published figures do.

Two consequences follow for the text. A drawn container is named under its shape, not across it. A boundary entity is a drawing with its name above the membrane, because a receptor captioned inside the cell puts its text on the body it is supposed to sit on; the names are spread apart where two receptors are close, and the container reserves the band above itself so the row of names cannot collide with what is overhead. Where an interior label will not fit without growing or deforming the drawing, the label moves out with a leader rather than the drawing changing shape, in three steps: full, qualifier dropped, name outside.

A boundary entity sits on the silhouette, not on the bounding box. The outline is sampled under the glyph, because on an amoeboid cell the membrane is nowhere near the top of its box and a receptor placed there floats above the cell it belongs to. Its glyph keeps the asset's own proportion: a membrane receptor is a wide shallow strip and a square box renders it as a smudge.

Putting contents inside a drawing means growing it until its empty middle can hold them, at a cost of one over the measured fraction: a shape measuring thirty per cent costs more than three times in each direction, and nested containers multiply those factors. Past a cap of 1.7 the drawing goes behind instead, which costs nothing. Without that cap one figure grew until its type was unreadable.

The first design had the silhouette *be* the container, contents inside its outline. Measured across seven shapes from three libraries, the largest rectangle fitting inside the inked area was 13 percent of the bounding box for a kidney, 19 for a liver, 23 for a stomach, 27 for a vessel, 38 for a macrophage, 41 for a lung and 50 for a megakaryocyte. Library shapes are lobed, thin or irregular, so that plan fails six times out of seven. Frame mode survives but is taken only when the measurement clears the threshold, per asset and automatically; otherwise the silhouette goes behind. The measurement is not wasted either way: its aspect and position tell the container what proportion to take and where inside the anchor the contents belong.

An anchor is background. No relation may reach it, it carries no label of its own, and below a minimum rendered size it is dropped for a labelled geometric region, because a silhouette a few millimetres wide is mush.

## The derivative store

Geometry costs one rasterisation per asset and is then cached under `SCIFIG_HOME` (default `~/.scientific-figures`), never inside the repository. Composed and transformed assets live there too, so the library grows with use.

Every entry carries the licence and provenance of every source that went into it. A derivative of a CC BY asset inherits the attribution obligation, and the chain has to survive composition: a cell composed from two Servier icons credits both, and a third figure reusing that cell credits them still. This is the part a human forgets and a store does not.

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

Containers are part of that test. An arc crosses the membrane of the structure it starts in, which is what a mechanism arc does, but a third cell on the way past is an obstacle: drawing through it says the signal went through that cell, a claim the specification never made. Every container that holds neither endpoint is therefore an obstacle, and the lane is confined to the innermost structure holding both ends, so a loop inside the cytoplasm stays in the cytoplasm instead of dropping below the figure. Where both lanes are walled in, the router looks for a vertical corridor, including the channel just past whatever stands in the way, since the structure in between frequently fills the whole gap; the dog-leg is tested end to end, not just its middle run. Only when no clear route exists does the arc fall back to a direct curve.

A relation label steps around the glyphs and around every label already set. Across its run first, then along it, because an annotation may slide to a clear stretch of its own arc, which is what a drafter does; where a dense rank leaves no gap at the height of the arc it lifts clear of the whole row, since a label printed over a glyph is worse than one set above it. Inside a partition a label belongs to its own band and wraps rather than spilling across the rule, where it would read as the next phase's text.

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
- `render/layout_spatial.py` — containment layout: slots, scale ladder, anatomical placement
- `render/derive.py` — derived geometry, frame-or-anchor measurement, the derivative store
- `render/style.py` — the colour budget under each purpose
- `render/asset_resolver.py` — pictogram resolution, licence gate, vector gate
- `render/figure_export.py` — SVG, PNG and PPTX output
- `examples/moa-example.yaml` — worked specification
- `examples/pictogram-example.yaml` — resolved pictograms, generic substitution, lane routing
- `examples/algorithm-example.yaml` — vertical clinical algorithm, PPTX output
- `examples/anatomical-example.yaml` — containment, boundary slots, resolved anchors
- `examples/phased-example.yaml` — a partition along an axis, three bands, a cross-phase relation
- `examples/methylxanthine-example.yaml` — a worked figure outside haematology, with its abstract
