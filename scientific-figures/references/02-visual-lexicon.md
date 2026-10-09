# Visual lexicon v0.1

Rendered reference: `../assets/figure-lexicon-v0.1.svg`.

## Governing principle

Every relation in a figure carries three independent semantic dimensions. Each dimension is assigned one visual channel and no channel encodes anything else.

| Dimension | Question | Channel |
|---|---|---|
| Relation type | what does the arc do | terminal glyph |
| Evidence level | how well established is it | stroke pattern |
| Narrative role | background or contribution | colour weight |

Keeping the channels separate is what allows an expert reader to parse a new figure without consulting the legend, because the vocabulary is the one already learned from SBGN and the pathway literature.

## A. Relation type (terminal glyph)

| Type | Glyph | Note |
|---|---|---|
| `production` | filled triangular head | A becomes B |
| `stimulation` | open V head | non-catalytic positive influence |
| `catalysis` | open circle terminal | enzymatic action on a process |
| `inhibition` | perpendicular bar | never an arrow carrying a minus sign |
| `transport` | thin stroke, open head, crossing a compartment boundary | translocation, secretion, uptake |
| `binding` | no terminal glyph, the line enters the complex container | complex formation |
| `flow` | orthogonal polyline, sharp corners, filled head | procedural step |

The open circle for catalysis and the bar for inhibition are non-negotiable: readers decode them automatically and any local variant costs a second per arc.

The curve against orthogonal polyline distinction is a house addition, not a standard. Biological relations are drawn as Bézier curves, procedural steps in algorithms and study designs as orthogonal polylines with sharp corners. The reader separates the causal register from the procedural register instantly. Declare it in the legend the first time it appears for an audience that does not know it.

## B. Evidence level (stroke pattern)

| Value | Stroke | Meaning |
|---|---|---|
| `established` | solid | known from the literature, cited |
| `demonstrated_here` | solid | shown by this work |
| `associated` | long dash | association shown, causality not |
| `hypothesized` | dotted, unfilled head | inferred or proposed, untested |

This is the safeguard that lets a model be published without being overstated.

## C. Narrative role (colour weight)

| Value | Treatment |
|---|---|
| `canonical` | neutral grey, reduced stroke weight |
| `contribution` | single accent colour, increased weight |

One accent colour per figure. Use the blue and orange pair rather than red and green, for deuteranopia safety. The contrast between `canonical` and `contribution` is the element that most reliably signals authorship competence to an expert reader, and the one most often omitted.

## D. Entity glyphs

| Class | Glyph |
|---|---|
| `macromolecule` | rounded rectangle |
| `nucleic_acid` | rectangle, lower corners rounded only |
| `small_molecule` | stadium |
| `complex` | container enclosing its components rather than naming them |
| `unspecified` | dashed outline |
| `state_variable` | small circle on the entity border, labelled (P, Ub, Ac) |
| `step` | labelled rectangle, sized from its text: a step in an algorithm or study design |
| `state` | tag, clipped at the leading corner: a clinical state or phenotype |
| `measure` | rectangle carrying a short scale on its lower edge: a measured quantity |
| `intervention` | lozenge with a central divider: a drug, device or procedure |
| `organelle`, `cell`, `cell_population`, `tissue`, `organ`, `organism` | resolved pictogram, or this project's generic glyph for the class |
| `process` | the SBGN square carried on an arc, label beside it, never inside |
| `cell`, `tissue`, `organ`, `subject` | pictogram from the asset registry |

**Iconography rule.** Pictograms are admitted only for classes where identity is itself the information: cell type, tissue, organ, clinical subject. Molecular entities stay geometric. An icon must do work a label could not do; otherwise it is noise competing for attention with the message.

**When no pictogram resolves.** Draw a plain solid outline and warn, naming the search terms tried. Never the dashed outline: dashed means `unspecified`, that is, an identity the author could not state, and overloading it to mean "the resolver found nothing" pushes the author to misclassify a cell as a macromolecule just to obtain a clean box. A limitation routed around by corrupting the semantics is worse than one that fails loudly.

**Imported pictograms are desaturated** unless the entity is the contribution. Colour encodes narrative role, and a library icon arrives with a palette of its own that would spend that channel. The desaturation is applied to the colour values, not through an SVG filter, because filters are dropped by some rasterisers and some PDF and EPS conversions.

**Human figures.** A content analysis of a published medical graphical abstract gallery documented racial, gender and body-size bias. Icon libraries inherit their authors' defaults and an automated generator amplifies them silently. Human pictogram attributes are an explicit field in the spec, never left to the first search hit.

## E. Compartments

| Type | Boundary | Use |
|---|---|---|
| `physical` | solid, faint tint fill | cytoplasm, nucleus, mitochondrion, vessel lumen |
| `conceptual` | dashed, no fill | microenvironment, circulation, time window |

Hierarchy is expressed by nesting, never by colour. Labels sit top left, not centred, so they do not compete with the contents.

## Typography and scale

One sans family (Helvetica or Arial, for Cell Press compatibility), two weights, three sizes at most: node labels, arc labels, compartment titles. Nothing below 6 pt at final size; 12 pt minimum inside a graphical abstract. Design at final size, never scale afterwards.

## Legend

Mandatory whenever more than four lexicon elements appear. Generated automatically from the subset actually used, never from a fixed template.

## Derived output

Because `evidence` and `source` are mandatory fields, the caption draft is generated from the specification: what is new, what is cited, with the matching references, and the attribution block for every asset used. No commercial tool does this, because none of them knows the epistemic status of what it draws.
