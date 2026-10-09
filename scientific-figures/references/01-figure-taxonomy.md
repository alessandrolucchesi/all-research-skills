# Figure taxonomy

Figures are classified by degree of normative constraint, not by subject. The band determines how much latitude the renderer has and which validator runs. The class determines the invariant that expert readers check.

## Band A: constrained by an external standard

Conformity, not design. Zero creative latitude. Input is structured and numeric; the renderer is a parameterised template; the validator is arithmetic.

| Class | Standard | Validator |
|---|---|---|
| Participant flow, randomised trial | CONSORT 2025 (30-item checklist plus participant flow diagram; BMJ, JAMA, Lancet, PLOS Med, Nat Med, April 2025) | counts close at every level |
| Study selection flow, systematic review | PRISMA 2020 | identified = screened + excluded, at each stage |
| Participant flow, diagnostic accuracy | STARD | index test and reference standard arms reconcile |
| Formal pathway notation | SBGN (Process Description, Entity Relationship, Activity Flow) | glyph conformity |

Failure mode to prevent: totals that do not reconcile. These pass peer review and surface later as a corrigendum. The compiler refuses to draw an unbalanced diagram.

## Band B: constrained by disciplinary convention

No formal standard, strong community expectation. This is where informativeness among peers is won or lost. The house lexicon applies in full.

### Mechanism of action
Asserts a causal chain inside a declared spatial frame.
Invariant: traceability of the delta. It must be immediately obvious which link is new and which is established.
Constraints: explicit compartmentalisation, a single reading axis, no more than five principal nodes, claim level encoded on every arc.

### Pathway
Asserts a topology of relations. Two subtypes that must never be mixed without saying so:
- *Curated*: reproduces database knowledge. Illustration. Attribute the source.
- *Data-derived*: represents a result of the analysis. Evidence. Declare method and thresholds in the caption.
Invariant: the subtype is declared. Conflating them is a substantive defect, not a graphic one.

### Experimental or study design
Asserts a temporal sequence and an allocation.
Invariant: explicit oriented time axis, marked sampling points, legible per-arm numbers that agree with the text.

### Clinical algorithm
Asserts a decision procedure.
Invariant: branches at every decision node are exhaustive and mutually exclusive, no dead paths, the normative source of each threshold declared. An algorithm that leaves a branch open reads as unreliable to a clinician.

## Band C: constrained by editorial rhetoric

No standard, no strong convention. The constraints are the target journal's technical specification and the discipline of the claim level.

### Graphical abstract
Single panel, no data items, biological context indicated (subcellular location, tissue or cell type, species). Three to five semantic units maximum. Designed at final size and tested as a thumbnail, which is where it actually competes in result lists and tables of contents.

### Conceptual or model figure
Proposes a model that is not demonstrated. Rule: it must be graphically distinguishable from a demonstrated mechanism, through the evidence channel of the lexicon. This is the single point where an elegant hypothesis becomes, for a distracted reader, a fact.

## Out of scope

Data figures: Kaplan-Meier, forest, waterfall, swimmer, box plots, heatmaps of measured values. These belong to the analysis code. The reason is not practical but deontological: a data figure produced separately from the analysis can diverge from it, and no amount of design discipline corrects that. Refuse and redirect.
