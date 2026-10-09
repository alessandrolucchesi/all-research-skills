#!/usr/bin/env python3
"""
ontology: what an entity *is*, kept separate from how it is drawn.

Two axes, because conflating them is what broke v0.2. There, `cell` meant both
"a cell" and "a pictogram goes here", so when no pictogram resolved the
semantics collapsed and the author's rational move was to relabel the cell as a
macromolecule to obtain a clean box. A class system must group, not exclude.

Axis 1, CLASS: what the thing is, organised by scale into five families. Every
class has a home for a real biological or clinical object, so `unspecified`
can mean what it should mean, an identity the author deliberately declines to
state, and nothing else.

Axis 2, DEPICTION: `geometric`, `pictogram` or `auto`. The class proposes a
default; the spec may override it. A pictogram class that resolves nothing is
drawn with the built-in generic glyph for its class, authored here and
therefore free of third-party licence terms. An entity is never reduced to an
anonymous box for want of an icon.

SUBSTITUTION RULE, generalise up, never sideways. When the exact asset is
missing, an asset for a MORE GENERAL term may stand in and the label carries
the identity: a generic cell for a megakaryocyte is honest, because the label
says which cell. A coordinate term may never stand in: a basophil for a
neutrophil is not an approximation, it is a misstatement. Lexically, the
candidate's words must be a subset of the query's words. A candidate that adds
a word is more specific, or a sibling, and is never taken automatically.
"""

from __future__ import annotations

# family, default depiction, terms that denote the generic form of the class,
# and whether colour may survive desaturation (never: colour is a channel).
ONTOLOGY = {
    # molecular ------------------------------------------------------------
    "small_molecule": dict(family="molecular", depiction="geometric"),
    "macromolecule":  dict(family="molecular", depiction="geometric"),
    "nucleic_acid":   dict(family="molecular", depiction="geometric"),
    "complex":        dict(family="molecular", depiction="geometric"),
    # cellular and structural ---------------------------------------------
    "organelle":      dict(family="cellular", depiction="pictogram",
                           generic=["organelle", "vesicle", "mitochondrion"]),
    "cell":           dict(family="cellular", depiction="pictogram",
                           generic=["cell", "cells"],
                           generic_assets=["blood-cells", "cell", "cells", "cell-nuclei"]),
    "cell_population": dict(family="cellular", depiction="pictogram",
                            generic=["cells", "colony"],
                            generic_assets=["blood-cells", "cells", "cell"]),
    "tissue":         dict(family="cellular", depiction="pictogram",
                           generic=["tissue", "epithelium"],
                           generic_assets=["tissue", "epithelium", "blood-cells"]),
    "organ":          dict(family="cellular", depiction="pictogram",
                           generic=["organ", "anatomy"], generic_assets=["organ"]),
    "organism":       dict(family="cellular", depiction="pictogram",
                           generic=["person", "patient"],
                           generic_assets=["person", "patient", "people", "adult"]),
    # process and state ----------------------------------------------------
    "process":        dict(family="process", depiction="geometric"),
    "state":          dict(family="process", depiction="geometric"),
    "measure":        dict(family="process", depiction="geometric"),
    # procedural -----------------------------------------------------------
    "step":           dict(family="procedural", depiction="geometric"),
    "intervention":   dict(family="procedural", depiction="geometric",
                           generic=["drug", "pill", "syringe", "treatment"]),
    # declared unknown -----------------------------------------------------
    "unspecified":    dict(family="unknown", depiction="geometric"),
}

PICTOGRAM_CLASSES = {k for k, v in ONTOLOGY.items() if v["depiction"] == "pictogram"}
CLASSES = tuple(ONTOLOGY)


def depiction_of(entity):
    d = entity.get("depiction", "auto")
    if d in ("geometric", "pictogram"):
        return d
    return ONTOLOGY.get(entity.get("class", "unspecified"), {}).get("depiction", "geometric")


def generic_terms(cls):
    return ONTOLOGY.get(cls, {}).get("generic", [])


def generic_assets(cls):
    """Catalogue names curated as acceptable generics for this class.

    A curated list rather than a lexical rule, because the lexical rule
    cannot tell a generic from a qualified sibling: "blood-cells" is a
    legitimate stand-in for a neutrophil, "cancerous-cell_nuclei" is not, and
    nothing in the two strings says which. Curation is auditable; a heuristic
    that silently admits the second is not.
    """
    return [g.lower() for g in ONTOLOGY.get(cls, {}).get("generic_assets", [])]


def is_generalisation(candidate_words, query_words):
    """True when the candidate denotes something more general than the query.

    Subset means the candidate drops qualifiers: "cell" against "mast cell".
    A candidate that adds a word is more specific or a sibling: "basophil
    granulocyte" against "granulocyte". Only the first may be substituted
    without a human in the loop.
    """
    cw, qw = set(candidate_words), set(query_words)
    return bool(cw) and cw.issubset(qw)


# --------------------------------------------------------------------------
# Built-in generic glyphs. Our own artwork, so no third-party terms apply and
# a figure is never blocked by the absence of an icon.
# --------------------------------------------------------------------------

def generic_glyph(cls, x, y, w, h, colour, sw):
    """Return SVG for the class's generic pictogram, fitted into the box."""
    cx, cy = x + w / 2.0, y + h / 2.0
    s = min(w, h) / 2.0
    g = []
    a = f'fill="none" stroke="{colour}" stroke-width="{sw:.1f}" stroke-linejoin="round"'
    af = f'fill="#f4f6f8" stroke="{colour}" stroke-width="{sw:.1f}" stroke-linejoin="round"'

    if cls == "cell":
        g.append(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{s*1.15:.1f}" ry="{s*0.88:.1f}" {af}/>')
        g.append(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{s*0.42:.1f}" ry="{s*0.34:.1f}" {a}/>')
    elif cls == "cell_population":
        for dx, dy, r in ((-0.62, 0.18, 0.62), (0.62, 0.18, 0.62), (0.0, -0.28, 0.72)):
            g.append(f'<ellipse cx="{cx + dx*s:.1f}" cy="{cy + dy*s:.1f}" '
                     f'rx="{s*r:.1f}" ry="{s*r*0.78:.1f}" {af}/>')
    elif cls == "organelle":
        g.append(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{s*1.15:.1f}" ry="{s*0.62:.1f}" {af}/>')
        for k in (-0.5, 0.0, 0.5):
            g.append(f'<path d="M{cx + k*s - s*0.18:.1f},{cy - s*0.4:.1f} '
                     f'Q{cx + k*s + s*0.18:.1f},{cy:.1f} {cx + k*s - s*0.18:.1f},{cy + s*0.4:.1f}" {a}/>')
    elif cls == "tissue":
        r = s * 0.52
        for i, dx in enumerate((-1.1, 0.0, 1.1)):
            for dy in (-0.42, 0.42):
                g.append(f'<rect x="{cx + dx*r*1.9 - r:.1f}" y="{cy + dy*r*1.6 - r*0.72:.1f}" '
                         f'width="{r*2:.1f}" height="{r*1.44:.1f}" rx="{r*0.45:.1f}" {af}/>')
    elif cls == "organ":
        g.append(f'<path d="M{cx - s*0.95:.1f},{cy - s*0.2:.1f} '
                 f'C{cx - s*1.1:.1f},{cy - s*1.05:.1f} {cx + s*0.25:.1f},{cy - s*1.15:.1f} '
                 f'{cx + s*0.5:.1f},{cy - s*0.5:.1f} '
                 f'C{cx + s*1.2:.1f},{cy - s*0.1:.1f} {cx + s*0.75:.1f},{cy + s*0.95:.1f} '
                 f'{cx - s*0.1:.1f},{cy + s*0.8:.1f} '
                 f'C{cx - s*0.8:.1f},{cy + s*0.68:.1f} {cx - s*0.85:.1f},{cy + s*0.25:.1f} '
                 f'{cx - s*0.95:.1f},{cy - s*0.2:.1f} Z" {af}/>')
    elif cls == "organism":
        g.append(f'<circle cx="{cx:.1f}" cy="{cy - s*0.62:.1f}" r="{s*0.33:.1f}" {af}/>')
        g.append(f'<path d="M{cx - s*0.62:.1f},{cy + s*0.92:.1f} '
                 f'C{cx - s*0.58:.1f},{cy - s*0.18:.1f} {cx + s*0.58:.1f},{cy - s*0.18:.1f} '
                 f'{cx + s*0.62:.1f},{cy + s*0.92:.1f} Z" {af}/>')
    elif cls == "intervention":
        g.append(f'<rect x="{cx - s*1.1:.1f}" y="{cy - s*0.46:.1f}" width="{s*2.2:.1f}" '
                 f'height="{s*0.92:.1f}" rx="{s*0.46:.1f}" {af}/>')
        g.append(f'<path d="M{cx:.1f},{cy - s*0.46:.1f} L{cx:.1f},{cy + s*0.46:.1f}" {a}/>')
    else:
        g.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="8" {af}/>')
    return "".join(g)
