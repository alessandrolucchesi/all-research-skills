#!/usr/bin/env python3
"""
layout_spatial: position carries location, arcs carry causality.

The flow engine ranks entities topologically and puts rank N in column N, so
position encodes the same thing the arrows already encode and nothing is left
to say where the reader is. That is why its output is boxes: there is nothing
to draw around a glyph whose only reason for being there is that it is third
in a chain.

Here position is anatomical. An entity sits inside the thing that contains it
and on the boundary if it is a boundary protein; rank only orders siblings
within one region. A container is simply an entity that contains others, so a
macrophage can hold a kinase and still be drawn as a macrophage, which is what
published figures do.

Three slots, deliberately not named after any anatomy, so the same construct
serves a cell, a vessel, a reactor or a watershed:

- `interior` (default): inside the container's content region.
- `boundary`: straddling the container's edge, which is where a receptor,
  a channel or a port belongs.
- nested containers: an entity with children placed in the interior, which is
  how a nucleus sits in a cell without the word "nucleus" appearing in the code.

Scale comes from the ontology. A container must stand on a higher scale level
than everything it contains, which is validated, and the level also sets the
default size of a leaf, so an organ is not drawn at the size of a metabolite.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from ontology import ONTOLOGY  # noqa: E402

# Scale ladder. A container's level must exceed its children's.
SCALE_LEVEL = {
    "small_molecule": 0, "macromolecule": 0, "nucleic_acid": 0, "complex": 0,
    "process": 0, "state": 0, "measure": 0, "step": 0, "intervention": 0,
    "unspecified": 0,
    "organelle": 1,
    "cell": 2, "cell_population": 2,
    "tissue": 3,
    "organ": 4,
    "organism": 5,
}

# Leaf size multiplier by level. Measured against published figures, each step
# down the ladder is worth roughly a factor of three in linear size; damped
# here because a figure also has to fit on a page.
LEVEL_SCALE = {0: 1.0, 1: 1.25, 2: 1.6, 3: 1.9, 4: 2.2, 5: 2.4}

PAD = 22.0          # inside a container, around its contents
GAP = 26.0          # between siblings
HEADER = 20.0       # room for the container's own label
TOP_CLEAR = 22.0    # room above a container for a label set outside it
BOUNDARY_INSET = 0.5   # fraction of a boundary glyph that sits outside the edge

# Putting contents inside a drawing means growing the drawing until its empty
# middle can hold them, and the factor is 1/fraction: a shape measuring 30 per
# cent costs 3.3x in each direction. Nested containers multiply those factors,
# which once blew a figure up until the type was unreadable. Past this cap the
# drawing goes behind the contents instead, which costs nothing.
MAX_FRAME_GROWTH = 1.7


def level_of(cls):
    return SCALE_LEVEL.get(cls, 0)


def build_tree(spec):
    """Entities and legacy compartments into one containment tree.

    `compartments` from earlier specs keep working: a compartment is just a
    container whose class was never stated.
    """
    ents = {e["id"]: dict(e) for e in spec.get("entities", [])}
    order = [e["id"] for e in spec.get("entities", [])]

    for c in spec.get("compartments", []) or []:
        if c["id"] in ents:
            continue
        ents[c["id"]] = {
            "id": c["id"], "label": c.get("label", c["id"]),
            "class": c.get("class", "tissue"),
            "_compartment": True, "_ctype": c.get("type", "physical"),
            "inside": c.get("parent"),
        }
        order.append(c["id"])

    children = {i: [] for i in ents}
    roots = []
    for i in order:
        e = ents[i]
        parent = e.get("inside") or e.get("compartment")
        if parent and parent in ents and parent != i:
            e["_parent"] = parent
            children[parent].append(i)
        else:
            e["_parent"] = None
            roots.append(i)

    # `contains` is the other direction and wins where both are given.
    for i in order:
        for ch in ents[i].get("contains", []) or []:
            if ch in ents and ents[ch].get("_parent") != i:
                old = ents[ch].get("_parent")
                if old and ch in children[old]:
                    children[old].remove(ch)
                elif ch in roots:
                    roots.remove(ch)
                ents[ch]["_parent"] = i
                children[i].append(ch)
    return ents, children, roots


def validate_scale(ents, children):
    errors = []
    for pid, kids in children.items():
        if not kids:
            continue
        pl = level_of(ents[pid].get("class", "unspecified"))
        if ents[pid].get("_compartment"):
            continue
        for k in kids:
            kl = level_of(ents[k].get("class", "unspecified"))
            if kl >= pl:
                errors.append(
                    f"entity {pid} ({ents[pid].get('class')}) contains {k} "
                    f"({ents[k].get('class')}): a container must stand on a higher "
                    f"scale level than its contents")
    return errors


class Box:
    """A laid-out entity: leaf or container."""
    __slots__ = ("id", "spec", "x", "y", "w", "h", "children", "is_container",
                 "slot", "geometry", "content", "rank")

    def __init__(self, eid, espec):
        self.id = eid
        self.spec = espec
        self.x = self.y = 0.0
        self.w = self.h = 0.0
        self.children = []
        self.is_container = False
        self.slot = espec.get("slot", "interior")
        self.geometry = None
        self.content = None       # (x, y, w, h) region for children
        self.rank = 0


def _rows_of(interior):
    """Break the interior children into rows. Called by both passes, because
    computing it twice is how children came to overflow their container."""
    import math
    if not interior:
        return []
    n = len(interior)
    tallest = max(c.h for c in interior)
    total = sum(c.w + GAP for c in interior) - GAP
    per_row = max(1, int(math.ceil(math.sqrt(n * (total / n) / max(tallest, 1.0)))))
    per_row = min(per_row, n)
    rows, cur = [], []
    for c in interior:
        cur.append(c)
        if len(cur) >= per_row:
            rows.append(cur)
            cur = []
    if cur:
        rows.append(cur)
    return rows


def _rows_extent(rows):
    if not rows:
        return 120.0, 60.0
    w = max(sum(c.w for c in r) + GAP * (len(r) - 1) for r in rows)
    h = sum(max(c.h for c in r) for r in rows) + GAP * (len(rows) - 1)
    return w, h


def measure(bid, ents, children, node_size, geoms=None, depth=0):
    """Bottom-up sizing: a leaf from its label and scale, a container from its
    contents, never smaller than its own scale demands."""
    e = ents[bid]
    b = Box(bid, e)
    kids = children.get(bid, [])
    lvl = level_of(e.get("class", "unspecified"))

    if not kids:
        w, h = node_size(e)
        s = LEVEL_SCALE.get(lvl, 1.0)
        b.w, b.h = w * (1.0 if lvl == 0 else min(s, 1.6)), h * (1.0 if lvl == 0 else min(s, 1.35))
        return b

    b.is_container = True
    inner = [measure(k, ents, children, node_size, geoms, depth + 1) for k in kids]
    b.children = inner
    interior = [c for c in inner if c.slot != "boundary"]
    boundary = [c for c in inner if c.slot == "boundary"]
    b.geometry = (geoms or {}).get(bid)

    cw, chh = _rows_extent(_rows_of(interior))
    b.content = (0.0, 0.0, cw, chh)

    bw = cw + 2 * PAD
    bh = chh + 2 * PAD + HEADER
    region = None
    if b.geometry and b.geometry.get("kind") == "frame":
        region = b.geometry.get("frame_rect")
    elif b.geometry and b.geometry.get("inscribed_fraction", 0) >= 0.30:
        region = b.geometry.get("inscribed")
    if region:
        # Contents go inside the drawing, so the container is grown until the
        # measured empty middle can hold them, unless that costs too much.
        _, _, iw, ih = region
        if iw > 0.05 and ih > 0.05:
            gw, gh = (cw / iw) / max(bw, 1.0), (chh / ih) / max(bh, 1.0)
            if max(gw, gh) <= MAX_FRAME_GROWTH:
                bw = max(bw, cw / iw)
                bh = max(bh, chh / ih)
            else:
                b.geometry = dict(b.geometry or {}, kind="mark",
                                  inscribed_fraction=0.0, _demoted=True)
    if boundary:
        bw = max(bw, sum(c.w + GAP for c in boundary) - GAP + 2 * PAD)
    b.w, b.h = bw, bh
    return b


def place(b, x, y):
    """Top-down placement. The content box is the one `measure` sized, centred
    in the container; in frame mode it is centred on the inscribed region
    instead, which is the part of the silhouette that can actually hold it."""
    b.x, b.y = x, y
    if not b.is_container:
        return
    interior = [c for c in b.children if c.slot != "boundary"]
    boundary = [c for c in b.children if c.slot == "boundary"]
    rows = _rows_of(interior)
    cw, ch = _rows_extent(rows)

    avail_y = y + HEADER
    avail_h = b.h - HEADER
    region = None
    if b.geometry and b.geometry.get("kind") == "frame":
        region = b.geometry.get("frame_rect")
        avail_y, avail_h = y, b.h      # a drawn frame carries its own label room
    elif b.geometry and b.geometry.get("inscribed_fraction", 0) >= 0.30:
        region = b.geometry.get("inscribed")
        avail_y, avail_h = y, b.h
    if region:
        ix, iy, iw, ih = region
        cx0 = x + (ix + iw / 2.0) * b.w - cw / 2.0
        cy0 = avail_y + (iy + ih / 2.0) * avail_h - ch / 2.0
    else:
        cx0 = x + (b.w - cw) / 2.0
        cy0 = avail_y + (avail_h - ch) / 2.0
    cx0 = min(max(cx0, x), max(x, x + b.w - cw))
    cy0 = min(max(cy0, avail_y), max(avail_y, avail_y + avail_h - ch))

    ry = cy0
    for r in rows:
        rw = sum(c.w for c in r) + GAP * (len(r) - 1)
        rx = cx0 + max(0.0, (cw - rw) / 2.0)
        for c in r:
            place(c, rx, ry)
            rx += c.w + GAP
        ry += max(c.h for c in r) + GAP

    # Boundary children straddle the top edge, which is where a reader expects
    # a receptor or a port, spread evenly across the span.
    if boundary:
        span = b.w - 2 * PAD
        step = span / len(boundary)
        for i, c in enumerate(boundary):
            bx = b.x + PAD + step * (i + 0.5) - c.w / 2.0
            place(c, bx, b.y - c.h * BOUNDARY_INSET)


def flatten(b, leaves, containers):
    if b.is_container:
        containers.append(b)
        for c in b.children:
            flatten(c, leaves, containers)
    else:
        leaves.append(b)
