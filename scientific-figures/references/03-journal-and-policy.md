# Target specifications, policy and accessibility

Publisher requirements change. Treat the figures below as defaults and verify the target journal's current author instructions before final export.

## Technical targets

| Target | Dimensions | Resolution | Type | Format |
|---|---|---|---|---|
| Cell Press graphical abstract | 5.5 in square (about 1200 x 1200 px) | 300 dpi | Arial 12 to 16 pt | TIFF, PDF, JPG |
| Cell Press figure | 85 mm single column, 178 mm double | 300 dpi raster, 1000 dpi line art | sans, legible at final size | EPS, PDF |
| Elsevier graphical abstract | landscape, 1328 x 531 px minimum | 300 dpi | no "graphical abstract" heading inside the image | per journal |

Cell Press additionally requires a graphical abstract for most of its titles (a named set including Cell Systems, Current Biology, Patterns, Neuron and Newton treat it as optional), requires a single panel, forbids data items of any kind, and asks that the biological context be indicated: subcellular location, tissue or cell type, species. Elsevier support for graphical abstracts is per journal: required, encouraged or unused.

## Evidence on impact, for calibration

Strong for dissemination, inconsistent for citation. A triple crossover trial on a nephrology journal's social account found visual abstract posts drew more than twice the views of citation-only posts and about five times the engagement. Retrospective cohorts disagree on citations: positive in gastroenterology and hepatology after adjustment, null in sport science, negative in general medical journals.

Design implication: the figure's primary audience is the handling editor and the reviewer, not the social timeline. A figure that proves the authors know what their own claim is will also travel; the reverse does not hold.

## Generative AI policy

As of 2026 the landscape has tightened and is not uniform.

- **Nature and Springer Nature**: AI-generated images and figures are not permitted, except where the AI generation is itself the object of the research.
- **Elsevier**: policy updated September 2025 requires a dedicated disclosure section before the references and explicitly prohibits AI image generation.
- **Cell Press**: AI-assisted features inside dedicated scientific illustration tools are permitted; general-purpose generative image models are not. AI-generated figures must be clearly labelled.
- **Science/AAAS, IEEE, ACS, PLOS, MDPI**: disclosure required, naming the tool and describing its role; restrictions vary.

Position of this skill: output is deterministic vector drawing compiled from a declared specification and licence-checked open assets, reviewable line by line and reproducible from source. That is a technical drawing, not a generated image, and it does not depend on a generative image model at any stage. Assistance remains assistance: when the user asks, emit a disclosure naming the tool, its version, the purpose and the location, in the form the target publisher requires. Verify the specific journal's policy page, not only the publisher umbrella page.

## Accessibility

- Colour encodes one variable only. Never two overlaid.
- Blue and orange in preference to red and green. Red-green deficiency affects roughly eight percent of men of northern European descent.
- No rainbow or jet scales: they introduce perceptual boundaries that do not exist in the content.
- The figure must survive conversion to greyscale, because redistribution and print still happen.
- Shape and stroke pattern carry the semantics; colour only reinforces. A figure whose meaning collapses in monochrome is built on the wrong channel.

## Licence targets

The three values accepted by `meta.target` in the specification map to the gates defined in `../assets/sources.json`: `oa_cc_by` for open access articles under CC BY, `subscription` for subscription and hybrid venues, `internal` for slides, teaching, grants and reports.

Why non-derivative and share-alike assets are refused outright for publication: placing an asset into a composite figure, recolouring or cropping it produces a derivative work, so ND can never be used in a figure; SA propagates to the whole composite, conflicting with the publishing agreement; NC is incompatible with the CC BY licence an open access journal applies to the entire article.
