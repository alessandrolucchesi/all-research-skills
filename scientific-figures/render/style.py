#!/usr/bin/env python3
"""
style: what the colour channel is spent on, decided by the figure's purpose.

The v0.3 rule said colour encodes narrative role and nothing else: neutral grey
for cited background, one accent for the contribution of this work. That rule
is right for a figure that makes a claim, and it is the reason a hypothesis
cannot be drawn as a finding. It is wrong for a figure that makes no claim.

Four published exemplars settled this. In the Frontiers NLRP3 inflammasome
figure and in a review figure on SyK inhibition, colour carries species
identity, consistently, and there is no evidence channel at all, because
neither figure claims novelty: both explain an accepted mechanism. Applying
the role rule to such a figure spends the whole colour budget on a channel the
figure does not use, which is exactly why our review output read as a
wireframe.

So the budget is assigned by `meta.purpose`:

- `primary_research`: colour = narrative role. Grey for cited background, one
  accent for the contribution. Identity is carried by glyph and label. This is
  the v0.3 behaviour, unchanged, and remains the default.
- `explanatory`: colour = entity identity, from a fixed deuteranopia-safe
  palette assigned per entity or per `identity` group. Evidence keeps the
  stroke-pattern channel, so a hypothesised arc is still dotted in a review
  figure: the honesty channel is never the one traded away.

What does not change under either purpose: one variable per visual channel,
evidence always on stroke pattern, and the greyscale and deuteranopia checks.
"""

from __future__ import annotations

# Eight hues, checked for separation under deuteranopia and for distinct
# lightness so they survive greyscale. Ordered by how often a figure needs
# them, so a three-entity figure gets the three most separated.
IDENTITY_PALETTE = [
    "#1f6fb2",   # blue
    "#d1670b",   # orange
    "#2f7d5d",   # green
    "#8a4f9e",   # purple
    "#9c6a2f",   # brown
    "#4a7fa8",   # steel
    "#b3486b",   # rose
    "#5c6b73",   # slate
]

# Fill tints paired with the strokes above: same hue, high lightness, so a
# filled glyph still reads as a glyph and not as a block of colour.
IDENTITY_FILL = [
    "#e8f1f8", "#fbefe3", "#e6f1ec", "#f2ebf5",
    "#f4eee4", "#eaf1f6", "#f8ebf0", "#eef0f1",
]

CANONICAL_INK = "#8e8e8e"
CANONICAL_FILL = "#ffffff"
INK = "#1a1a1a"

# Compartment tints by nesting depth: a flat ramp, never hue, because
# hierarchy is read from nesting and the hue channel is already spoken for.
COMPARTMENT_TINT = ["#eef3f7", "#e5ecf2", "#dde6ed", "#d6e0e8"]

# prominence -> (stroke multiplier, font multiplier, pad multiplier)
PROMINENCE = {
    "primary": (1.45, 1.15, 1.25),
    "normal": (1.0, 1.0, 1.0),
    "secondary": (0.8, 0.88, 0.9),
}

# Default prominence by ontology family, so an organ is not drawn at the size
# of a metabolite without anyone having said so.
FAMILY_PROMINENCE = {
    "cellular": "primary",
    "process": "normal",
    "molecular": "normal",
    "procedural": "normal",
    "unknown": "secondary",
}


class Palette:
    """Resolves an entity or relation to its colours under one purpose."""

    def __init__(self, spec):
        meta = spec.get("meta", {})
        self.purpose = meta.get("purpose", "primary_research")
        self.accent = meta.get("accent_colour", "#0b6ea8")
        self.explanatory = self.purpose == "explanatory"
        self._assigned = {}
        if self.explanatory:
            # One hue per identity group. Entities sharing `identity` share a
            # hue, which is how a figure says "these are the same species in
            # two places" without drawing an arc.
            groups = []
            for e in spec.get("entities", []):
                key = e.get("identity") or e["id"]
                if key not in groups:
                    groups.append(key)
            for i, key in enumerate(groups):
                self._assigned[key] = i % len(IDENTITY_PALETTE)

    def _slot(self, entity):
        return self._assigned.get(entity.get("identity") or entity["id"], 0)

    def entity(self, entity, role):
        """Return (stroke, fill) for an entity glyph."""
        if not self.explanatory:
            stroke = self.accent if role == "contribution" else INK
            return stroke, CANONICAL_FILL
        i = self._slot(entity)
        return IDENTITY_PALETTE[i], IDENTITY_FILL[i]

    def icon_ink(self, entity, role):
        """Colour for an imported pictogram painted with currentColor."""
        if not self.explanatory:
            return self.accent if role == "contribution" else "#6e6e6e"
        return IDENTITY_PALETTE[self._slot(entity)]

    def keep_icon_colour(self, role):
        """Whether an imported icon keeps its own palette.

        Never. Under primary_research it would spend a channel reserved for
        role; under explanatory it would collide with the identity hue the
        figure has already assigned. The icon is recoloured either way.
        """
        return False

    def relation(self, rel):
        """Return (stroke, weight multiplier) for an arc.

        Under either purpose the arc stays neutral unless it is the
        contribution: an arc tinted with its source entity's identity hue
        would make the reader hunt for a meaning that is not there.
        """
        role = rel.get("role", "canonical")
        ev = rel.get("evidence", "established")
        if role == "contribution" and not self.explanatory:
            return self.accent, 1.45
        if role == "contribution":
            return INK, 1.35
        return (CANONICAL_INK, 0.85) if ev == "established" else (INK, 1.0)

    def legend_needs_role(self):
        return not self.explanatory


def prominence_of(entity, family):
    p = entity.get("prominence")
    if p in PROMINENCE:
        return p
    return FAMILY_PROMINENCE.get(family, "normal")
