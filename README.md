# all-research-skills

Skills for research work, each self-contained in its own folder with a `SKILL.md`
entry point.

## scientific-figures

A compiler for publication-grade schematic figures: mechanisms of action,
pathways, clinical algorithms, study designs and graphical abstracts. Figures are
written as a declarative specification and compiled to deterministic vector
output, so nothing passes through a generative image model and every figure is
reproducible from source.

Every relation carries a mandatory evidence level, rendered through a dedicated
visual channel, so a proposed mechanism cannot be drawn as a demonstrated one.
Every pictorial asset resolves against a registry of open-licensed libraries
under a licence gate enforced at compile time.

![Figure compiled from a specification](scientific-figures/examples/moa-example.png)

See [`scientific-figures/`](scientific-figures/).

## Licensing

Code and reference text: MIT, see `LICENSE`. Figures and plates are CC BY 4.0;
see `scientific-figures/LICENSING.md` for the split. No third-party assets are
redistributed here: the registry holds metadata only.
