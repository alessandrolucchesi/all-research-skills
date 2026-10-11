#!/usr/bin/env python3
"""
figure_render: compile a figure-spec into journal-ready SVG.

Band B renderer (mechanism of action, pathways, study designs, clinical
algorithms). Bands A and C reuse this engine with their own templates and
validators.

Dependencies: Python 3.9+ and PyYAML (only if the spec is YAML; JSON specs
need nothing beyond the standard library). No network access, no external
layout engine, no generative model: the same spec always compiles to the
same drawing.

Usage:
    python figure_render.py spec.yaml -o figure.svg
    python figure_render.py spec.yaml --variant slide -o slide.svg
    python figure_render.py spec.yaml --caption caption.md
    python figure_render.py spec.yaml --check        # validate only
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys

try:
    import yaml
except ImportError:  # JSON specs still work
    yaml = None

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCES = os.path.join(HERE, os.pardir, "assets", "sources.json")

# --------------------------------------------------------------------------
# Lexicon constants. These encode references/02-visual-lexicon.md and are the
# only place where semantics touch appearance.
# --------------------------------------------------------------------------

INK = "#1a1a1a"
CANONICAL = "#8e8e8e"
TINT = "#eef3f7"
LABEL_MUTED = "#5b7384"

# Evidence level -> stroke pattern
DASH = {
    "established": None,
    "demonstrated_here": None,
    "associated": "11 6",
    "hypothesized": "2 5",
}
# Evidence level -> is the terminal head filled
HEAD_FILLED = {
    "established": True,
    "demonstrated_here": True,
    "associated": True,
    "hypothesized": False,
}

VARIANTS = {
    # name: (scale, base font, node font, stroke, output width)
    "journal": dict(scale=1.0, font=15.0, stroke=2.0, out_width_mm=178.0),
    "slide":   dict(scale=1.0, font=19.0, stroke=2.8, out_width_px=1600),
    "thumbnail": dict(scale=1.0, font=15.0, stroke=2.0, out_width_px=300),
}

# How far short of the node the stroke stops, so the terminal glyph sits on
# the boundary instead of floating away from the line.
SHRINK = {"binding": 0.0, "inhibition": 1.0, "catalysis": 13.0}

try:
    from .ontology import (ONTOLOGY, PICTOGRAM_CLASSES, depiction_of,  # noqa
                           generic_glyph)
except Exception:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ontology import (ONTOLOGY, PICTOGRAM_CLASSES, depiction_of,  # noqa
                          generic_glyph)
try:
    from .style import COMPARTMENT_TINT, PROMINENCE, Palette, prominence_of  # noqa
except Exception:
    from style import COMPARTMENT_TINT, PROMINENCE, Palette, prominence_of  # noqa
import derive as DERIVE  # noqa: E402
import layout_spatial as SPATIAL  # noqa: E402

BASE_FONT = 15.0
ICON_H = 46.0           # vertical room a resolved pictogram adds to a node
PROCESS_SIDE = 22.0     # SBGN process square, drawn on the arc, not around text


def wrap_label(text, max_chars=30):
    """Greedy wrap. Keeps a short label on one line and lets a long one grow
    downwards instead of stretching its column."""
    if not text:
        return []
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if len(trial) > max_chars and cur:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def text_width(s, font=BASE_FONT):
    """Approximate Helvetica advance width. One metric, used by every class.

    Every glyph must be sized from this function. The v0.1 `process` branch
    ignored the measured size and drew a fixed square, which is how labels
    came to overflow their own boxes.
    """
    narrow, wide = "iljtfr.,:;'|!()[] ", "mwMW@%"
    total = 0.0
    for ch in s:
        if ch in narrow:
            total += 0.30
        elif ch in wide:
            total += 0.92
        elif ch.isupper() or ch.isdigit():
            total += 0.66
        else:
            total += 0.54
    return total * font

# Layout metrics, in user units
GUTTER = 78.0       # horizontal clearance between rank columns
COL_W = 210.0
ROW_H = 86.0
ROW_GAP = 30.0      # clear space between two nodes stacked in the same rank
NODE_H = 40.0
NODE_MIN_W = 96.0
PAD = 26.0          # padding inside a compartment box
MARGIN = 34.0
HEAD_LEN = 14.0


# --------------------------------------------------------------------------
# Loading and validation
# --------------------------------------------------------------------------

def load_spec(path):
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    if path.endswith((".yaml", ".yml")):
        if yaml is None:
            sys.exit("PyYAML is required to read a YAML spec. Use JSON, or pip install pyyaml.")
        return yaml.safe_load(text)
    return json.loads(text)


def load_sources(path=SOURCES):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except OSError:
        return None


def licence_gate(spec, sources):
    """Check every declared asset against the gate for the declared target.

    Returns (errors, warnings). A denied licence is never overridable; an
    asset in 'review' passes only with a recorded override.
    """
    errors, warnings = [], []
    if not sources:
        warnings.append("asset registry not found: licence gate not enforced")
        return errors, warnings

    target = spec["meta"]["target"]
    gate = sources["license_gate"]["targets"].get(target)
    if gate is None:
        errors.append(f"unknown target '{target}'")
        return errors, warnings

    by_id = {s["id"]: s for s in sources["sources"]}
    overrides = {
        o["asset_id"]
        for o in spec.get("provenance", {}).get("gate_overrides", []) or []
    }

    for asset in spec.get("provenance", {}).get("assets", []) or []:
        src = by_id.get(asset.get("source_id"))
        if src is None:
            errors.append(f"asset {asset.get('asset_id')}: source '{asset.get('source_id')}' not in registry")
            continue
        if src.get("gate") == "deny":
            errors.append(
                f"asset {asset.get('asset_id')}: source '{src['id']}' is denied outright ({src['name']})"
            )
            continue
        lic = asset.get("license", "")
        if lic in gate.get("deny", []):
            errors.append(
                f"asset {asset.get('asset_id')} ({src['id']}): licence {lic} is not usable for target '{target}'"
            )
        elif lic in gate.get("review", []):
            if asset.get("asset_id") not in overrides:
                errors.append(
                    f"asset {asset.get('asset_id')} ({src['id']}): licence {lic} needs a recorded gate override"
                )
            else:
                warnings.append(f"asset {asset.get('asset_id')}: {lic} used under override")
        elif lic not in gate.get("allow", []):
            warnings.append(f"asset {asset.get('asset_id')}: licence {lic} not recognised by the gate")
    return errors, warnings


def validate(spec, sources=None):
    errors, warnings = [], []
    meta = spec.get("meta", {})
    for key in ("title", "band", "figure_class", "target", "claim"):
        if not meta.get(key):
            errors.append(f"meta.{key} is required")

    ents = {e["id"]: e for e in spec.get("entities", [])}
    comps = {c["id"]: c for c in spec.get("compartments", []) or []}

    for e in spec.get("entities", []):
        if e.get("compartment") and e["compartment"] not in comps:
            errors.append(f"entity {e['id']}: unknown compartment '{e['compartment']}'")
        holds = bool(e.get("contains")) or any(
            o.get("inside") == e["id"] for o in spec.get("entities", []))
        if holds:
            continue    # a container is drawn by its shape and its anchor
        if e["class"] in PICTOGRAM_CLASSES and not e.get("asset"):
            warnings.append(
                f"entity {e['id']}: no pictogram resolved for class '{e['class']}'; drawn as a plain "
                f"outline. Run with --resolve-assets, or set `asset:` by hand. Do not downgrade the "
                f"class to get a cleaner glyph: that corrupts the semantics."
            )
        if e["class"] == "subject" and not e.get("human_attributes"):
            warnings.append(
                f"entity {e['id']}: human attributes left implicit; set them explicitly to avoid inherited defaults"
            )

    for i, r in enumerate(spec.get("relations", [])):
        tag = f"relation {i} ({r.get('from')} -> {r.get('to')})"
        if r.get("from") not in ents:
            errors.append(f"{tag}: unknown source entity")
        if r.get("to") not in ents:
            errors.append(f"{tag}: unknown target entity")
        ev = r.get("evidence")
        if ev not in DASH:
            errors.append(f"{tag}: missing or invalid evidence level")
        elif ev != "demonstrated_here" and not r.get("source"):
            errors.append(f"{tag}: evidence '{ev}' requires a source")

    if meta.get("figure_class") in {"consort_flow", "prisma_flow", "stard_flow"}:
        errors.append(
            "band A figure classes must be compiled by the standard-conformant template, not by this renderer"
        )

    ge, gw = licence_gate(spec, sources if sources is not None else load_sources())
    return errors + ge, warnings + gw


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------

class Node:
    __slots__ = ("id", "label", "cls", "comp", "role", "spec", "x", "y", "w", "h",
                 "rank", "row", "modifier", "has_icon", "pictorial",
                 "qualifier", "lines", "qlines", "prom", "fsc", "depicted")

    def __init__(self, e, font=BASE_FONT, max_chars=30):
        self.modifier = False
        self.id = e["id"]
        fam = ONTOLOGY.get(e.get("class", "unspecified"), {}).get("family", "unknown")
        self.prom = prominence_of(e, fam)
        psw, pf, ppad = PROMINENCE[self.prom]
        self.fsc = pf
        self.label = e.get("label", e["id"])
        self.cls = e.get("class", "unspecified")
        self.comp = e.get("compartment")
        self.role = e.get("role", "canonical")
        self.spec = e
        mode = e.get("_label_mode", "full")
        self.qualifier = "" if mode != "full" else (e.get("qualifier") or "")
        self.has_icon = bool(e.get("asset", {}).get("_svg"))
        self.depicted = bool(e.get("_depicted")) and self.has_icon
        # A pictorial entity always gets icon room: with a resolved asset it
        # holds the icon, without one it holds this class's generic glyph.
        # Nothing is reduced to an anonymous box for want of an asset.
        self.pictorial = depiction_of(e) == "pictogram"
        # Wrap: a published algorithm box carries far more than three words
        # (the BJH thrombocytosis algorithm runs to about twenty-five), so a
        # label is wrapped rather than allowed to set the column width.
        self.lines = [] if mode == "outside" else wrap_label(self.label, max_chars)
        self.qlines = wrap_label(self.qualifier, int(max_chars * 1.25)) if self.qualifier else []
        ef = font * pf
        tw = max([text_width(l, ef) for l in self.lines] +
                 [text_width(l, ef * 0.78) for l in self.qlines] + [0.0])
        if self.cls == "process":
            self.w = max(NODE_MIN_W, PROCESS_SIDE + 10.0 + tw + 24.0)
        else:
            self.w = max(NODE_MIN_W, tw + 30.0 * ppad)
        if mode == "outside":
            # Only the glyph stays inside; the name goes out with a leader.
            # The glyph keeps the drawing's own proportion: a membrane
            # receptor is a wide shallow strip, and squeezing it into a
            # square box renders it as a smudge the reader cannot identify.
            self.h = ICON_H * 1.05
            ar = 1.0
            a = e.get("asset") or {}
            if a.get("_svg"):
                ar = (DERIVE.geometry_for(a, a["_svg"]) or {}).get("natural_aspect") or 1.0
            self.w = max(42.0, self.h * min(max(ar, 0.55), 3.2))
            return
        body = max(NODE_H, ef * 1.5 * len(self.lines) + ef * 1.15 * len(self.qlines) + 16.0)
        if self.depicted:
            # A drawing with a label under it: no box, so no padding for one,
            # and the glyph gets the room instead.
            self.w = max(ICON_H * 1.15, tw + 8.0)
            body = ef * 1.35 * len(self.lines) + ef * 1.05 * len(self.qlines) + 6.0
        self.h = body + (ICON_H if (self.has_icon or self.pictorial) else 0.0)
        self.x = self.y = 0.0
        self.rank = 0
        self.row = 0

    @property
    def cx(self):
        return self.x + self.w / 2.0

    @property
    def cy(self):
        return self.y + self.h / 2.0


def topological_ranks(nodes, relations):
    """Longest-path ranking with cycles broken at the weakest edge.

    Hypothesised relations are dropped first when breaking a cycle, which is
    almost always the feedback arc an author is proposing.
    """
    order = {n.id: i for i, n in enumerate(nodes)}
    edges = [(r["from"], r["to"], r.get("evidence")) for r in relations
             if r.get("from") in order and r.get("to") in order]

    kept, dropped = [], []
    adj = {n.id: [] for n in nodes}

    def creates_cycle(a, b):
        seen, stack = set(), [b]
        while stack:
            cur = stack.pop()
            if cur == a:
                return True
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(adj[cur])
        return False

    for a, b, ev in sorted(edges, key=lambda e: e[2] == "hypothesized"):
        if a == b or creates_cycle(a, b):
            dropped.append((a, b))
            continue
        adj[a].append(b)
        kept.append((a, b))

    rank = {n.id: 0 for n in nodes}
    for _ in range(len(nodes)):
        changed = False
        for a, b in kept:
            if rank[b] < rank[a] + 1:
                rank[b] = rank[a] + 1
                changed = True
        if not changed:
            break
    return rank


def compartment_tree(comps):
    children = {c["id"]: [] for c in comps}
    roots = []
    for c in comps:
        if c.get("parent") and c["parent"] in children:
            children[c["parent"]].append(c["id"])
        else:
            roots.append(c["id"])
    return roots, children


# Figure classes that read top to bottom. A decision procedure is read as a
# descent, and laying one out left to right both reads wrongly and produces a
# canvas too flat to hold legible type.
VERTICAL_CLASSES = {"clinical_algorithm", "consort_flow", "prisma_flow", "stard_flow"}


def orientation_of(spec):
    o = spec["meta"].get("orientation", "auto")
    if o in ("horizontal", "vertical"):
        return o
    if spec["meta"].get("figure_class") in VERTICAL_CLASSES and not spec.get("compartments"):
        return "vertical"
    return "horizontal"


def layout_vertical(spec, gutter=GUTTER, font=BASE_FONT):
    """Rank runs down the page; nodes sharing a rank spread across it."""
    nodes = [Node(e, font) for e in spec["entities"]]
    by_id = {n.id: n for n in nodes}
    rank = topological_ranks(nodes, spec.get("relations", []))
    for n in nodes:
        n.rank = rank[n.id]
    lanes = {}
    for n in sorted(nodes, key=lambda m: (m.rank, m.id)):
        lanes.setdefault(n.rank, []).append(n)
    row_gap = 54.0
    y = MARGIN + 10.0
    width = max(sum(n.w for n in g) + gutter * (len(g) - 1) for g in lanes.values())
    for rk in sorted(lanes):
        group = lanes[rk]
        total = sum(n.w for n in group) + gutter * (len(group) - 1)
        x = MARGIN + (width - total) / 2.0
        tallest = max(n.h for n in group)
        for n in group:
            n.x, n.y = x, y
            x += n.w + gutter
        y += tallest + row_gap
    w = width + 2 * MARGIN
    h = y - row_gap + MARGIN
    return nodes, by_id, {}, w, h


def layout_anatomical(spec, gutter=GUTTER, font=BASE_FONT):
    """Containment layout. Returns the same tuple the flow engines return, so
    the renderer does not care which engine produced it: leaf entities as
    Nodes, containers as rects carrying their shape and anchor."""
    ents, children, roots = SPATIAL.build_tree(spec)

    def node_size(e):
        n = Node(e, font)
        return n.w, n.h

    # Geometry before sizing: in frame mode the container has to be grown
    # until the measured inscribed region can hold its contents, so the
    # measurement cannot wait until after the box exists.
    # A container that holds other containers is a region, not a drawing.
    # Its job is to say where all this happens, and giving it the outline of
    # an organ forces the whole figure into that organ's proportions: a
    # spleen drawn around two cells stacked the figure into one tall column.
    # A container whose children are all leaves is drawn, which is what the
    # published figures do: the cell is drawn and holds molecules.
    geoms = {}
    for eid, e in ents.items():
        a = e.get("anchor") or {}
        if not a.get("_svg"):
            continue
        holds_container = any(bool(children.get(k)) for k in children.get(eid, []))
        if holds_container and e.get("depiction") != "pictogram":
            continue
        g = DERIVE.geometry_for(a, a["_svg"])
        if g:
            geoms[eid] = g
    boxes = [SPATIAL.measure(r, ents, children, node_size, geoms) for r in roots]

    x = MARGIN
    top = MARGIN + 28.0
    for b in boxes:
        SPATIAL.place(b, x, top)
        x += b.w + gutter

    leaves, containers = [], []
    for b in boxes:
        SPATIAL.flatten(b, leaves, containers)

    nodes, by_id = [], {}
    for lb in leaves:
        n = Node(lb.spec, font)
        n.x, n.y, n.w, n.h = lb.x, lb.y, lb.w, lb.h
        nodes.append(n)
        by_id[n.id] = n

    rank = topological_ranks(nodes, spec.get("relations", []))
    for n in nodes:
        n.rank = rank.get(n.id, 0)

    rects = {}
    for cb in containers:
        cls = cb.spec.get("class", "tissue")
        rects[cb.id] = dict(
            x=cb.x, y=cb.y, w=cb.w, h=cb.h,
            type=cb.spec.get("_ctype", "physical"),
            label=cb.spec.get("label", cb.id),
            parent=cb.spec.get("_parent"),
            depth=0 if cb.spec.get("_parent") is None else 1,
            shape=container_shape_for(cls, cb.geometry),
            has_boundary=any(c.slot == "boundary" for c in cb.children),
            anchor=cb.spec.get("anchor"),
            geometry=cb.geometry,
            cls=cls,
        )
    width = max([n.x + n.w for n in nodes] + [r["x"] + r["w"] for r in rects.values()]) + MARGIN
    height = max([n.y + n.h for n in nodes] + [r["y"] + r["h"] for r in rects.values()]) + MARGIN
    return nodes, by_id, rects, width, height


def layout(spec, gutter=GUTTER, font=BASE_FONT):
    mode = spec["meta"].get("layout", "auto")
    if mode == "anatomical" or (
            mode == "auto" and spec["meta"].get("figure_class") in
            ("mechanism_of_action", "pathway_curated", "pathway_data_derived",
             "conceptual_model")
            and any(e.get("contains") or e.get("inside") for e in spec.get("entities", []))):
        return layout_anatomical(spec, gutter=gutter, font=font)
    if orientation_of(spec) == "vertical":
        return layout_vertical(spec, gutter=gutter, font=font)
    return layout_horizontal(spec, gutter=gutter, font=font)


def layout_horizontal(spec, gutter=GUTTER, font=BASE_FONT):
    nodes = [Node(e, font) for e in spec["entities"]]
    by_id = {n.id: n for n in nodes}
    comps = spec.get("compartments", []) or []
    comp_by_id = {c["id"]: c for c in comps}
    rels = spec.get("relations", [])
    rank = topological_ranks(nodes, rels)
    for n in nodes:
        n.rank = rank[n.id]

    # Modifier nodes: no incoming relation and acting only as inhibitor or
    # catalyst. They sit above their target rather than in the reading line,
    # which is how such figures are drawn by hand and avoids an arrow that
    # crosses the node between them.
    indeg = {n.id: 0 for n in nodes}
    outgoing = {n.id: [] for n in nodes}
    for r in rels:
        if r.get("to") in indeg:
            indeg[r["to"]] += 1
        if r.get("from") in outgoing:
            outgoing[r["from"]].append(r)
    mod_target = {}
    for n in nodes:
        outs = outgoing[n.id]
        if outs and indeg[n.id] == 0 and all(r.get("type") in ("inhibition", "catalysis") for r in outs):
            tgt = outs[0].get("to")
            if tgt in by_id and tgt != n.id:
                n.modifier = True
                mod_target[n.id] = tgt
                n.rank = by_id[tgt].rank

    roots, children = compartment_tree(comps)
    order = []

    def walk(cid, depth):
        order.append((cid, depth))
        for ch in children[cid]:
            walk(ch, depth + 1)

    for r in roots:
        walk(r, 0)
    if any(n.comp is None for n in nodes):
        order.append((None, 0))

    # Column positions follow the widest node at each rank, so a long label
    # never squeezes the arc that follows it down to nothing.
    colw = {}
    for n in nodes:
        colw[n.rank] = max(colw.get(n.rank, 0.0), n.w)
    colx, acc = {}, 0.0
    for rk in sorted(colw):
        colx[rk] = acc
        acc += colw[rk] + gutter

    # Rows: within a compartment, nodes sharing a rank stack vertically.
    y = MARGIN + 34.0
    for cid, depth in order:
        members = [n for n in nodes if n.comp == cid and not n.modifier]
        mods = [n for n in nodes if n.comp == cid and n.modifier]
        if not members and not mods:
            continue
        lanes = {}
        for n in sorted(members, key=lambda m: (m.rank, m.id)):
            lanes.setdefault(n.rank, []).append(n)
        top = y + (62.0 if mods else 0.0)
        lane_bottom = top
        for rk, group in lanes.items():
            cy = top
            for n in group:
                n.x = MARGIN + PAD + colx[rk]
                n.y = cy
                cy += n.h + ROW_GAP
            lane_bottom = max(lane_bottom, cy - ROW_GAP)
        y = lane_bottom + 24.0
    for n in nodes:
        if n.modifier:
            t = by_id[mod_target[n.id]]
            n.x = t.x + (t.w - n.w) / 2.0
            n.y = t.y - 66.0

    # Compartment boxes hug their own members plus every descendant box.
    rects = {}

    def own_bbox(cid):
        ms = [n for n in nodes if n.comp == cid]
        if not ms:
            return None
        return (min(n.x for n in ms), min(n.y for n in ms),
                max(n.x + n.w for n in ms), max(n.y + n.h for n in ms))

    def build(cid, depth):
        parts = []
        b = own_bbox(cid)
        if b:
            parts.append(b)
        for ch in children.get(cid, []):
            cr = build(ch, depth + 1)
            if cr:
                parts.append((cr["x"], cr["y"], cr["x"] + cr["w"], cr["y"] + cr["h"]))
        if not parts:
            return None
        pad = PAD if depth == 0 else PAD * 0.8
        x0 = min(p[0] for p in parts) - pad
        y0 = min(p[1] for p in parts) - pad - 14.0
        x1 = max(p[2] for p in parts) + pad
        y1 = max(p[3] for p in parts) + pad
        r = dict(x=x0, y=y0, w=x1 - x0, h=y1 - y0,
                 type=comp_by_id[cid].get("type", "physical"),
                 label=comp_by_id[cid].get("label", cid), depth=depth,
                 parent=comp_by_id[cid].get("parent"))
        rects[cid] = r
        return r

    for cid in roots:
        build(cid, 0)

    width = max([n.x + n.w for n in nodes] + [r["x"] + r["w"] for r in rects.values()]) + MARGIN
    height = max([n.y + n.h for n in nodes] + [r["y"] + r["h"] for r in rects.values()]) + MARGIN
    return nodes, by_id, rects, width, height


# --------------------------------------------------------------------------
# Drawing primitives
# --------------------------------------------------------------------------

def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def rect_edge(node, tx, ty):
    """Point where the segment from the node centre to (tx,ty) leaves the box."""
    dx, dy = tx - node.cx, ty - node.cy
    if dx == 0 and dy == 0:
        return node.cx, node.cy
    hw, hh = node.w / 2.0 + 2.0, node.h / 2.0 + 2.0
    sx = hw / abs(dx) if dx else float("inf")
    sy = hh / abs(dy) if dy else float("inf")
    s = min(sx, sy)
    return node.cx + dx * s, node.cy + dy * s


_HEX = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")
_RGB = re.compile(r"rgb\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)\s*\)")


def desaturate_svg(text, keep=0.12):
    """Rewrite every colour in an imported icon towards grey.

    Done by rewriting the colour values rather than with an SVG filter: a
    filter is a rendering-time effect that some rasterisers ignore and some
    PDF and EPS conversions drop, which would let a canonical pictogram
    silently reclaim the colour channel at the worst moment, in the
    publisher's production pipeline.
    """
    def grey(r, g, b):
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        # Lift the darkest tones. A flat black pictogram, merely desaturated,
        # still outweighs everything around it and reclaims the emphasis that
        # belongs to the contribution.
        lum = max(lum, 112.0)
        return tuple(min(255, int(round(lum + (c - lum) * keep))) for c in (r, g, b))

    def hex_sub(m):
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        return "#%02x%02x%02x" % grey(r, g, b)

    def rgb_sub(m):
        r, g, b = (int(m.group(i)) for i in (1, 2, 3))
        return "rgb(%d,%d,%d)" % grey(r, g, b)

    return _RGB.sub(rgb_sub, _HEX.sub(hex_sub, text))


def embed_svg(svg_text, x, y, w, h, uid):
    """Inline a fetched SVG into the drawing, scaled into the given box.

    Ids are namespaced so two icons cannot collide, and any script or event
    handler is stripped: these files come from third-party repositories and
    the output is a figure, not a document that should execute anything.
    """
    svg_text = re.sub(r"(?is)<script.*?</script>", "", svg_text)
    svg_text = re.sub(r'(?i)\son\w+="[^"]*"', "", svg_text)
    m = re.search(r'viewBox="([-\d.eE\s,]+)"', svg_text)
    if m:
        nums = [float(t) for t in re.split(r"[\s,]+", m.group(1).strip())]
        vx, vy, vw, vh = nums if len(nums) == 4 else (0.0, 0.0, 100.0, 100.0)
    else:
        def attr(name, default):
            mm = re.search(name + r'="([\d.]+)', svg_text)
            return float(mm.group(1)) if mm else default
        vx, vy, vw, vh = 0.0, 0.0, attr("width", 100.0), attr("height", 100.0)
    if vw <= 0 or vh <= 0:
        return ""
    inner = re.sub(r"(?s)^.*?<svg[^>]*>", "", svg_text)
    inner = re.sub(r"(?s)</svg>\s*$", "", inner)
    for ident in set(re.findall(r'id="([^"]+)"', inner)):
        new = f"{uid}_{ident}"
        inner = (inner.replace(f'id="{ident}"', f'id="{new}"')
                      .replace(f"url(#{ident})", f"url(#{new})")
                      .replace(f'href="#{ident}"', f'href="#{new}"'))
    sc = min(w / vw, h / vh)
    tx = x + (w - vw * sc) / 2.0 - vx * sc
    ty = y + (h - vh * sc) / 2.0 - vy * sc
    return f'<g transform="translate({tx:.2f},{ty:.2f}) scale({sc:.4f})">{inner}</g>'


def resolve_spec_assets(spec, strict=False):
    """Populate entity.asset and provenance.assets from the open registry.

    Returns a list of messages. Nothing is auto-accepted below the resolver's
    exact-match threshold: a near match on a cell type is a misstatement, not
    an approximation.
    """
    try:
        from . import asset_resolver as AR          # noqa
    except Exception:
        sys.path.insert(0, HERE)
        import asset_resolver as AR
    msgs = []
    target = spec["meta"]["target"]

    # Anchors resolve like any other asset and through the same gates. An
    # anchor named by term rather than by asset is looked up in the open
    # libraries, which is where the tool's reach beyond one field comes from.
    contains = set()
    for e in spec["entities"]:
        for c in e.get("contains", []) or []:
            contains.add(e["id"])
        if e.get("inside"):
            contains.add(e["inside"])

    # A container with contents and no stated anchor asks the libraries for
    # one under its own label. This is what gives a macrophage the look of a
    # macrophage without anybody drawing one, and it generalises: the same
    # path fetches a leaf, a kidney or a fermenter.
    for e in spec["entities"]:
        if e["id"] in contains and e.get("anchor") is None:
            e["anchor"] = {"term": e.get("label", e["id"]), "_auto": True}
        if e.get("anchor") is False:
            e.pop("anchor")

    for e in spec["entities"]:
        anc = e.get("anchor")
        if not anc or anc.get("_svg"):
            continue
        term = anc.get("term") or anc.get("label") or e.get("label", e["id"])
        try:
            from . import asset_resolver as AR0  # noqa
        except Exception:
            sys.path.insert(0, HERE)
            import asset_resolver as AR0
        # A container asks the frame categories first: those hold drawn empty
        # cells whose middle can carry the contents, so the container becomes
        # a real cell instead of a neutral blob with a ghost behind it.
        prefer = ("Cell_membrane", "Tissues") if e["id"] in contains else ()
        acc, cand, terms = AR0.resolve(term, target=target, cls=e.get("class"),
                                       prefer_categories=prefer)
        if e["id"] in contains and not acc:
            acc, cand2, t2 = AR0.resolve("empty cell membrane", target=target,
                                         cls=e.get("class"),
                                         prefer_categories=("Cell_membrane",))
            terms = terms + t2
        pick = acc[0] if acc else (cand[0] if cand else None)
        if pick:
            e["anchor"] = {k: v for k, v in pick.items() if k != "score"}
            e["anchor"]["_svg"] = pick["svg"]
            e["anchor"]["role"] = "anchor"
            spec.setdefault("provenance", {}).setdefault("assets", []).append(
                {k: v for k, v in pick.items() if k not in ("svg", "score")})
            msgs.append(f"anchor {e['id']}: {pick['source_id']} {pick['asset_id']} ({pick['license']})")
        elif not anc.get("_auto"):
            msgs.append(f"warning: anchor {e['id']}: nothing resolved for [{', '.join(terms)}]")
        else:
            e.pop("anchor", None)
    prov = spec.setdefault("provenance", {}).setdefault("assets", [])
    used_assets = {}    # asset_id -> (entity id, score)
    prefer = None       # once one family is used, prefer it: mixing a flat
                        # pictogram set with a detailed illustration set reads
                        # as two figures spliced together
    # In an anatomical figure a glyph is depicted unless there is nothing to
    # depict it with. Counting the Frontiers inflammasome figure, five of
    # about forty entities sit in a box; the rest are drawings with a label
    # beside them, and that ratio is most of the distance between a diagram
    # and a figure.
    depict_all = (spec["meta"].get("layout") == "anatomical"
                  or spec["meta"].get("figure_class") in
                  ("mechanism_of_action", "pathway_curated", "pathway_data_derived"))
    for e in spec["entities"]:
        if e["id"] in contains:
            continue        # a container is drawn by its frame and its body
        if e.get("asset", {}).get("_svg"):
            continue
        if e.get("depiction") == "geometric":
            continue
        if e.get("class") not in PICTOGRAM_CLASSES and not depict_all:
            continue
        if e.get("class") in ("process", "step", "measure", "state"):
            continue    # these carry meaning in their glyph, not in a picture
        accepted, candidates, terms = AR.resolve(
            e.get("label", e["id"]), target=target,
            synonyms=e.get("synonyms"), cls=e.get("class"),
            prefer_source=prefer)
        if (accepted and accepted[0]["asset_id"] in used_assets
                and not accepted[0].get("adaptations")):
            prev_id, prev_score = used_assets[accepted[0]["asset_id"]]
            if accepted[0]["score"] <= prev_score:
                msgs.append(
                    f"error: entity {e['id']}: would reuse the asset already given to "
                    f"{prev_id}; two entities drawn with one glyph say they are the same "
                    f"thing. Falling back to the generic glyph for class '{e['class']}'. "
                    f"Set `asset:` explicitly, or add a synonym, to give it one of its own.")
                accepted = []
            else:
                msgs.append(
                    f"error: entity {prev_id}: its asset is a better match for {e['id']}; "
                    f"{prev_id} falls back to its class generic glyph.")
                for ent in spec["entities"]:
                    if ent["id"] == prev_id:
                        ent.pop("asset", None)
                prov[:] = [a for a in prov if a.get("asset_id") != accepted[0]["asset_id"]]
        if accepted:
            a = accepted[0]
            used_assets[a["asset_id"]] = (e["id"], a["score"])
            if depict_all:
                e["_depicted"] = True
            e["asset"] = a
            prefer = prefer or a["source_id"]
            prov.append({k: v for k, v in a.items() if k not in ("svg", "score")})
            msgs.append(f"entity {e['id']}: resolved {a['source_id']} {a['asset_id']} ({a['license']})")
            e["asset"]["_svg"] = a["svg"]
        else:
            tried = ", ".join(terms)
            extra = ""
            if candidates:
                extra = ("; closest non-exact: "
                         + ", ".join(f"{c['asset_id']} ({c['score']})" for c in candidates[:3])
                         + ". Set `asset:` explicitly to use one.")
            msg = (f"entity {e['id']}: no exact pictogram for terms [{tried}]{extra}")
            if strict:
                raise SystemExit(f"error: {msg}")
            msgs.append("warning: " + msg)
    return msgs


def seg_hits_node(x1, y1, x2, y2, node, pad=8.0):
    """Liang-Barsky test: does the segment cross this node's padded box?"""
    xmin, xmax = node.x - pad, node.x + node.w + pad
    ymin, ymax = node.y - pad, node.y + node.h + pad
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, x1 - xmin), (dx, xmax - x1), (-dy, y1 - ymin), (dy, ymax - y1)):
        if pp == 0:
            if qq < 0:
                return False
            continue
        t = qq / pp
        if pp < 0:
            if t > t1:
                return False
            t0 = max(t0, t)
        else:
            if t < t0:
                return False
            t1 = min(t1, t)
    return True


class Obstacle:
    """A container presented to the router as something to go around.

    An arc is not free to cross any structure it likes. Crossing the membrane
    of the cell it starts in is what a mechanism arc does; crossing a third
    cell on the way past says that the signal went through that cell, which
    is a claim the specification never made. Containers therefore enter the
    router as obstacles, except the ones that contain an endpoint.
    """
    __slots__ = ("x", "y", "w", "h", "id")

    def __init__(self, cid, r, inset=0.0):
        self.id = cid
        self.x, self.y = r["x"] + inset, r["y"] + inset
        self.w, self.h = r["w"] - 2 * inset, r["h"] - 2 * inset


def containment_router(nodes, rects):
    """Return (obstacles_for, bounds_for) closed over the containment tree."""
    # The flow engines carry containment on `compartment` and the anatomical
    # engine on the tree it built; either way it is the same question, and
    # reading only one of them once made every compartment an obstacle to
    # every arc and routed a whole figure into lanes below itself.
    parent = {}
    for n in nodes:
        parent[n.id] = (n.spec.get("_parent") or n.spec.get("inside")
                        or n.spec.get("compartment"))
    for cid, r in rects.items():
        parent[cid] = r.get("parent")

    def chain(eid):
        out, p, guard = [], parent.get(eid), 0
        while p and guard < 12:
            out.append(p)
            p, guard = parent.get(p), guard + 1
        return out

    def obstacles_for(a, b):
        spare = set(chain(a.id)) | set(chain(b.id)) | {a.id, b.id}
        obs = [n for n in nodes if n is not a and n is not b]
        obs += [Obstacle(cid, r, inset=2.0)
                for cid, r in rects.items() if cid not in spare]
        return obs

    def bounds_for(a, b):
        """The innermost structure holding both ends. An arc between two
        entities in one compartment belongs inside that compartment; sending
        it around the outside says it left the tissue."""
        ca, cb = chain(a.id), set(chain(b.id))
        for cid in ca:
            if cid in cb and cid in rects:
                r = rects[cid]
                return (r["y"] + 12.0, r["y"] + r["h"] - 12.0,
                        r["x"] + 12.0, r["x"] + r["w"] - 12.0)
        return None

    return obstacles_for, bounds_for


def clear_lane(a, b, others, below=True, bounds=None):
    """Find a lane between a and b that no other glyph occupies.

    The whole route is tested, not just the horizontal run: the two vertical
    drops that join the lane to its endpoints cross the same space, and a
    feedback arc was passing straight through a process glyph that sat
    directly under its origin.

    `bounds` keeps the lane inside the structure that holds both ends.
    """
    edge_a = (a.y + a.h) if below else a.y
    edge_b = (b.y + b.h) if below else b.y
    lane = (max(a.y + a.h, b.y + b.h) + 30.0) if below else (min(a.y, b.y) - 30.0)
    stride = 22.0 if below else -22.0
    lo, hi = min(a.cx, b.cx), max(a.cx, b.cx)
    start = lane
    for _ in range(10):
        if bounds and not (bounds[0] <= lane <= bounds[1]):
            return lane, float("inf")
        clash = (any(seg_hits_node(lo, lane, hi, lane, n, pad=6.0) for n in others)
                 or any(seg_hits_node(a.cx, edge_a, a.cx, lane, n, pad=4.0) for n in others)
                 or any(seg_hits_node(b.cx, edge_b, b.cx, lane, n, pad=4.0) for n in others))
        if not clash:
            return lane, abs(lane - start)
        lane += stride
    return lane, float("inf") if bounds else abs(lane - start)


def clear_column(a, b, others, xbounds=None):
    """A vertical corridor joining two glyphs, for the case both horizontal
    lanes are walled in.

    Between two cells the free space is often a column rather than a band,
    and the whole dog-leg is tested, not just the column: out of one glyph at
    its own height, along the corridor, in at the other's. The corridor is
    not restricted to the gap between the two glyphs, because the structure
    in the way frequently fills exactly that gap; a channel past its edge is
    a shorter and more honest route than a line drawn through it.
    """
    lo, hi = min(a.cy, b.cy), max(a.cy, b.cy)
    xa = (a.x + a.w) if a.cx <= b.cx else a.x
    xb = b.x if a.cx <= b.cx else (b.x + b.w)
    mid = (xa + xb) / 2.0

    cand = [mid]
    span = abs(xb - xa)
    for f in (0.2, -0.2, 0.36, -0.36):
        cand.append(mid + span * f)
    # Channels immediately past whatever stands in the way.
    for n in others:
        cand.append(n.x - 15.0)
        cand.append(n.x + n.w + 15.0)

    best, best_cost = None, float("inf")
    for cx in cand:
        if xbounds and not (xbounds[0] <= cx <= xbounds[1]):
            continue
        if any(seg_hits_node(cx, lo, cx, hi, n, pad=5.0) for n in others):
            continue
        if any(seg_hits_node(xa, a.cy, cx, a.cy, n, pad=5.0) for n in others):
            continue
        if any(seg_hits_node(cx, b.cy, xb, b.cy, n, pad=5.0) for n in others):
            continue
        cost = abs(cx - mid)
        if cost < best_cost:
            best, best_cost = cx, cost
    return best, best_cost


def head(kind, x, y, angle, colour, sw, filled=True):
    deg = math.degrees(angle)
    g = f'<g transform="translate({x:.1f},{y:.1f}) rotate({deg:.1f})">'
    if kind in ("production", "flow"):
        fill = colour if filled else "#ffffff"
        g += f'<path d="M0,0 L-13,-6 L-13,6 Z" fill="{fill}" stroke="{colour}" stroke-width="{sw*0.8:.1f}"/>'
    elif kind == "stimulation":
        # Always an open V head. The unfilled variant used for hypothesised
        # relations applies to production and flow heads, not to this one.
        g += (f'<path d="M-12,-6 L0,0 L-12,6" fill="none" stroke="{colour}" '
              f'stroke-width="{sw:.1f}" stroke-linejoin="round" stroke-linecap="round"/>')
    elif kind == "catalysis":
        g += f'<circle cx="-7" cy="0" r="6.5" fill="#ffffff" stroke="{colour}" stroke-width="{sw:.1f}"/>'
    elif kind == "inhibition":
        g += f'<path d="M0,-9 L0,9" stroke="{colour}" stroke-width="{sw*1.2:.1f}" stroke-linecap="round"/>'
    elif kind == "transport":
        g += f'<path d="M-11,-4.5 L0,0 L-11,4.5" fill="none" stroke="{colour}" stroke-width="{sw*0.7:.1f}" stroke-linejoin="round"/>'
    g += "</g>"
    return g


# Container geometry is ours and domain-neutral. Anatomical identity never
# comes from the geometry; it comes from the anchor behind it, which is what
# lets the same four shapes serve a cell, a vessel, a reactor or a catchment.
CONTAINER_SHAPES = ("blob", "rounded", "tube", "open")


def container_shape_for(cls, geometry):
    if cls in ("cell", "cell_population", "organelle"):
        return "blob"
    if geometry and geometry.get("aspect", 1.0) < 0.55:
        return "tube"
    if cls in ("organ", "tissue", "organism"):
        return "rounded"
    return "open"


def container_path(shape, x, y, w, h, fill, stroke, sw, dashed=False):
    d = ' stroke-dasharray="8 6"' if dashed else ""
    if shape == "blob":
        rx, ry = w / 2.0, h / 2.0
        cx, cy = x + rx, y + ry
        return (f'<path d="M{cx - rx:.1f},{cy:.1f} '
                f'C{cx - rx:.1f},{cy - ry * 1.08:.1f} {cx - rx * 0.52:.1f},{cy - ry:.1f} {cx:.1f},{cy - ry:.1f} '
                f'C{cx + rx * 0.56:.1f},{cy - ry:.1f} {cx + rx:.1f},{cy - ry * 0.96:.1f} {cx + rx:.1f},{cy - ry * 0.1:.1f} '
                f'C{cx + rx:.1f},{cy + ry * 0.86:.1f} {cx + rx * 0.5:.1f},{cy + ry:.1f} {cx:.1f},{cy + ry:.1f} '
                f'C{cx - rx * 0.58:.1f},{cy + ry:.1f} {cx - rx:.1f},{cy + ry * 0.9:.1f} {cx - rx:.1f},{cy:.1f} Z" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="{sw:.1f}"{d}/>')
    if shape == "tube":
        r = min(w, h) * 0.32
        return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                f'rx="{r:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw:.1f}"{d}/>')
    if shape == "rounded":
        return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="18" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="{sw:.1f}"{d}/>')
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="10" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw:.1f}" stroke-dasharray="8 6"/>')


def entity_shape(n, colour, sw, fill="#ffffff"):
    x, y, w, h = n.x, n.y, n.w, n.h
    dash = ""
    if getattr(n, "depicted", False):
        # The drawing is the glyph. A box around it is the thing that made
        # every mechanism figure look like an organigram, and it has to be
        # refused before any class branch gets to add one.
        return ""
    if n.cls == "macromolecule":
        return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="9" fill="{fill}" stroke="{colour}" stroke-width="{sw:.1f}"/>'
    if n.cls == "nucleic_acid":
        r = 12
        return (f'<path d="M{x:.1f},{y:.1f} h{w:.1f} v{h-r:.1f} a{r},{r} 0 0 1 -{r},{r} '
                f'h-{w-2*r:.1f} a{r},{r} 0 0 1 -{r},-{r} z" fill="{fill}" stroke="{colour}" stroke-width="{sw:.1f}"/>')
    if n.cls == "small_molecule":
        return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{h/2:.1f}" fill="{fill}" stroke="{colour}" stroke-width="{sw:.1f}"/>'
    if n.cls == "complex":
        c = 11
        return (f'<path d="M{x+c:.1f},{y:.1f} h{w-2*c:.1f} l{c},{c} v{h-2*c:.1f} l-{c},{c} '
                f'h-{w-2*c:.1f} l-{c},-{c} v-{h-2*c:.1f} z" fill="{fill}" stroke="{colour}" stroke-width="{sw:.1f}"/>')
    if n.cls == "process":
        # SBGN sense: a small square carried on the arc. The label sits beside
        # it, never inside it, so it cannot overflow.
        sq = PROCESS_SIDE
        return (f'<rect x="{x:.1f}" y="{n.cy - sq/2:.1f}" width="{sq:.1f}" height="{sq:.1f}" '
                f'fill="{fill}" stroke="{colour}" stroke-width="{sw:.1f}"/>')
    if n.cls == "step":
        return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="4" '
                f'fill="{fill}" stroke="{colour}" stroke-width="{sw:.1f}"/>')
    if n.cls == "state":
        # A clinical state or phenotype: a tag, clipped at the leading corner.
        c = 13
        return (f'<path d="M{x+c:.1f},{y:.1f} h{w-c:.1f} v{h:.1f} h-{w-c:.1f} '
                f'l-{c},-{h/2:.1f} z" fill="{fill}" stroke="{colour}" stroke-width="{sw:.1f}"/>')
    if n.cls == "measure":
        # A measured quantity: a box carrying a short scale on its lower edge.
        t = "".join(f'<path d="M{x + w*k:.1f},{y+h:.1f} v-5" stroke="{colour}" '
                    f'stroke-width="{sw*0.8:.1f}"/>' for k in (0.25, 0.5, 0.75))
        return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="3" '
                f'fill="{fill}" stroke="{colour}" stroke-width="{sw:.1f}"/>' + t)
    if n.cls in PICTOGRAM_CLASSES:
        return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="10" '
                f'fill="{fill}" stroke="{colour}" stroke-width="{sw:.1f}"/>')
        # Nothing resolved: draw this class's generic glyph. Never a dashed
        # box, which means "unspecified", and never a plain rectangle, which
        # tells the reader nothing the label has not already said.
        return generic_glyph(n.cls, n.x, n.y, n.w, ICON_H, colour, sw)
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="4" fill="#ffffff" '
            f'stroke="{colour}" stroke-width="{sw:.1f}" stroke-dasharray="6 5"/>')


# --------------------------------------------------------------------------
# Renderer
# --------------------------------------------------------------------------

def type_budget(spec, cfg, width_units):
    """Maximum canvas width in units before body type drops below the floor."""
    if "out_width_mm" not in cfg:
        return None
    floor = 12.0 if spec["meta"].get("figure_class") == "graphical_abstract" else 6.0
    return cfg["font"] * cfg["out_width_mm"] * 72.0 / (25.4 * floor)


def render(spec, variant="journal"):
    cfg = VARIANTS[variant]
    pal = Palette(spec)
    accent = pal.accent
    font = cfg["font"]
    sw = cfg["stroke"]

    nodes, by_id, rects, width, height = layout(spec, font=font)

    # Fit to the physical column width. Type size is a hard floor, so the
    # canvas is what gives: tighten the gutters until the body type clears
    # the floor, and refuse if tightening is not enough.
    fit_note = None
    budget = type_budget(spec, cfg, width)
    if budget and width > budget:
        for g in (66.0, 56.0, 48.0, 42.0):
            nodes, by_id, rects, width, height = layout(spec, gutter=g, font=font)
            if width <= budget:
                fit_note = f"gutters tightened to {g:.0f} units to clear the type floor"
                break
        else:
            if orientation_of(spec) == "horizontal" and spec["meta"].get("layout") == "anatomical":
                tops = len([r for r in rects.values() if r.get("depth", 0) == 0])
                fit_note = (
                    f"CANNOT FIT: {tops} top-level container(s) laid side by side leave body "
                    f"type below the floor at {cfg.get('out_width_mm', 0):.0f} mm. Nest a "
                    "container inside another, or move entities into fewer containers: both "
                    "keep the content, dropping entities loses it.")
            else:
                ncols = len({n.rank for n in nodes})
                fit_note = (
                    f"CANNOT FIT: {ncols} rank columns leave body type below the floor at "
                    f"{cfg.get('out_width_mm', 0):.0f} mm. The binding constraint is the number of "
                    "columns, not the entity count: merging two adjacent ranks keeps all the "
                    "content, removing entities loses it. Try merging ranks first.")

    vertical = orientation_of(spec) == "vertical"
    used = {"relations": set(), "evidence": set(), "roles": set(), "comp_types": set()}

    out = []
    out.append("")  # placeholder for the opening tag
    out.append("")  # placeholder for the background, sized once the canvas is final

    # compartments, outermost first
    for cid, r in sorted(rects.items(), key=lambda kv: kv[1]["depth"]):
        used["comp_types"].add(r["type"])
        if r.get("shape"):
            tint = COMPARTMENT_TINT[min(r["depth"], len(COMPARTMENT_TINT) - 1)]
            geo0 = r.get("geometry") or {}
            has_drawn = (DERIVE.is_frame(geo0)
                         or (geo0.get("outline") and geo0.get("inscribed_fraction", 0) >= 0.26))
            if not has_drawn:
                out.append(container_path(r["shape"], r["x"], r["y"], r["w"], r["h"],
                                          tint if r["type"] == "physical" else "none",
                                          INK, sw, dashed=r["type"] != "physical"))
            anc = r.get("anchor") or {}
            geo = r.get("geometry") or {}
            outline = geo.get("outline")
            if outline and geo.get("inscribed_fraction", 0) >= 0.26:
                # The outline IS the container: stroked at full strength,
                # filled pale, contents in its lumen. Fading the whole drawing
                # so a label could sit on it is what made a cell read as
                # wallpaper rather than as the structure being explained.
                tint = COMPARTMENT_TINT[min(r["depth"], len(COMPARTMENT_TINT) - 1)]
                d = DERIVE.scale_path(outline["d"], r["x"], r["y"], r["w"], r["h"])
                out.append(f'<path d="{d}" fill="{tint}" stroke="{INK}" '
                           f'stroke-width="{sw*1.15:.1f}" stroke-linejoin="round"/>')
            elif DERIVE.is_frame(geo) and anc.get("_svg"):
                # A frame asset is the container: drawn at full strength, with
                # the contents in the empty middle the measurement found.
                out.append(f'<g color="{INK}">'
                           + embed_svg(desaturate_svg(anc["_svg"]), r["x"], r["y"],
                                       r["w"], r["h"],
                                       "frm" + re.sub(r"[^A-Za-z0-9]", "", cid))
                           + '</g>')
            elif anc.get("_svg") and (anc.get("style") == "wash"):
                # Only on request. A faint silhouette behind the contents
                # reads as an ornament on the background rather than as the
                # structure the figure is explaining, which is the whole
                # reason the outline treatment exists.
                body, op = DERIVE.anchor_svg(desaturate_svg(anc["_svg"]))
                out.append(f'<g opacity="{op}" color="#4a5a66">'
                           + embed_svg(body, r["x"], r["y"] + 10, r["w"], r["h"] - 14,
                                       "anc" + re.sub(r"[^A-Za-z0-9]", "", cid))
                           + '</g>')
            # A blob has no top-left corner to put a label in, so it is set
            # centred above the curve; a rectangle keeps the corner.
            if outline and geo.get("inscribed_fraction", 0) >= 0.26:
                out.append(f'<text x="{r["x"] + r["w"]/2:.1f}" y="{r["y"] + r["h"] + 15:.1f}" '
                           f'font-size="{font*0.8:.1f}" text-anchor="middle" '
                           f'fill="{LABEL_MUTED}" letter-spacing="0.5">{esc(r["label"].upper())}</text>')
            elif r["shape"] == "blob":
                # Centred above is where a boundary child sits, so a container
                # that has one moves its label aside rather than under it.
                if r.get("has_boundary"):
                    out.append(f'<text x="{r["x"] + r["w"]*0.14:.1f}" y="{r["y"] + 26:.1f}" '
                               f'font-size="{font*0.78:.1f}" '
                               f'fill="{LABEL_MUTED}" letter-spacing="0.6">{esc(r["label"].upper())}</text>')
                else:
                    out.append(f'<text x="{r["x"] + r["w"]/2:.1f}" y="{r["y"] - 6:.1f}" '
                               f'font-size="{font*0.78:.1f}" text-anchor="middle" '
                               f'fill="{LABEL_MUTED}" letter-spacing="0.6">{esc(r["label"].upper())}</text>')
            else:
                out.append(f'<text x="{r["x"]+16:.1f}" y="{r["y"]+20:.1f}" font-size="{font*0.78:.1f}" '
                           f'fill="{LABEL_MUTED}" letter-spacing="0.6">{esc(r["label"].upper())}</text>')
            continue
        if r["type"] == "physical":
            tint = COMPARTMENT_TINT[min(r["depth"], len(COMPARTMENT_TINT) - 1)]
            out.append(f'<rect x="{r["x"]:.1f}" y="{r["y"]:.1f}" width="{r["w"]:.1f}" height="{r["h"]:.1f}" '
                       f'rx="14" fill="{tint}" stroke="{INK}" stroke-width="{sw:.1f}"/>')
        else:
            out.append(f'<rect x="{r["x"]:.1f}" y="{r["y"]:.1f}" width="{r["w"]:.1f}" height="{r["h"]:.1f}" '
                       f'rx="14" fill="none" stroke="{INK}" stroke-width="{sw:.1f}" stroke-dasharray="8 6"/>')
        out.append(f'<text x="{r["x"]+14:.1f}" y="{r["y"]+20:.1f}" font-size="{font*0.78:.1f}" '
                   f'fill="{LABEL_MUTED}" letter-spacing="0.6">{esc(r["label"].upper())}</text>')

    # relations under the nodes
    obstacles_for, bounds_for = containment_router(nodes, rects)
    for rel in spec.get("relations", []):
        a, b = by_id.get(rel["from"]), by_id.get(rel["to"])
        if not a or not b:
            continue
        kind = rel.get("type", "production")
        ev = rel.get("evidence", "established")
        role = rel.get("role", "canonical")
        used["relations"].add(kind)
        used["evidence"].add(ev)
        used["roles"].add(role)

        colour, wmul = pal.relation(rel)
        stroke_w = sw * wmul
        dash = DASH.get(ev)
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        if kind == "transport":
            stroke_w *= 0.6

        label_at = None
        x1, y1 = rect_edge(a, b.cx, b.cy)
        x2, y2 = rect_edge(b, a.cx, a.cy)
        ang = math.atan2(y2 - y1, x2 - x1)
        shrink = SHRINK.get(kind, HEAD_LEN)
        ex, ey = x2 - math.cos(ang) * shrink, y2 - math.sin(ang) * shrink

        # Route into a clear lane whenever the straight path would cut through
        # another glyph, not merely when the arc runs backwards. A rank-span
        # rule would miss a long arc that happens to pass over a node and
        # divert a short one that passes over nothing.
        obstacles = obstacles_for(a, b)
        blocked = any(seg_hits_node(x1, y1, ex, ey, n) for n in obstacles)
        back_edge = b.rank < a.rank
        detour = None
        if kind != "flow" and (back_edge or blocked):
            bnd = bounds_for(a, b)
            ybnd = bnd[:2] if bnd else None
            lane_lo, cost_lo = clear_lane(a, b, obstacles, below=True, bounds=ybnd)
            lane_hi, cost_hi = clear_lane(a, b, obstacles, below=False, bounds=ybnd)
            if lane_hi < 16.0:
                cost_hi = float("inf")
            if back_edge:
                cost_lo -= 18.0
            col, cost_col = clear_column(a, b, obstacles, bnd[2:] if bnd else None)
            if min(cost_lo, cost_hi) == float("inf") and cost_col < float("inf"):
                detour = ("column", col)
            elif min(cost_lo, cost_hi) < float("inf"):
                detour = ("lane", lane_lo if cost_lo <= cost_hi else lane_hi,
                          cost_lo <= cost_hi)
        if detour and detour[0] == "column":
            # Out of one side, across the corridor, into the other.
            cx = detour[1]
            x1, y1 = ((a.x + a.w) if cx >= a.cx else a.x), a.cy
            if abs(cx - b.cx) <= b.w / 2.0:
                # The corridor lands over or under the target, so the arc
                # comes in vertically instead of doubling back.
                from_above = y1 < b.cy
                y2 = b.y if from_above else b.y + b.h
                x2, ex = cx, cx
                ey = y2 - shrink if from_above else y2 + shrink
                ang = math.pi / 2.0 if from_above else -math.pi / 2.0
                d = f"M{x1:.1f},{y1:.1f} L{cx:.1f},{y1:.1f} L{cx:.1f},{ey:.1f}"
            else:
                x2, y2 = (b.x if cx < b.cx else b.x + b.w), b.cy
                rightward = x2 >= cx
                ex = x2 - shrink if rightward else x2 + shrink
                ey = y2
                ang = 0.0 if rightward else math.pi
                d = (f"M{x1:.1f},{y1:.1f} L{cx:.1f},{y1:.1f} "
                     f"L{cx:.1f},{y2:.1f} L{ex:.1f},{y2:.1f}")
            label_at = (cx + 6.0, (y1 + y2) / 2.0 - 4.0)
        elif detour and detour[0] == "lane":
            # Feedback below, long forward arcs above, so the two stay
            # distinguishable. Both sides are costed and the shorter detour
            # wins: committing to one side and pushing until it clears drags
            # the arc past the figure and leaves a void the size of it.
            _, lane, below = detour
            x1, x2, ex = a.cx, b.cx, b.cx
            if below:
                y1, y2 = a.y + a.h, b.y + b.h
                ey = y2 + shrink
                ang = -math.pi / 2.0
                height = max(height, lane + 26.0)
            else:
                y1, y2 = a.y, b.y
                ey = y2 - shrink
                ang = math.pi / 2.0
            d = (f"M{x1:.1f},{y1:.1f} L{x1:.1f},{lane:.1f} "
                 f"L{x2:.1f},{lane:.1f} L{x2:.1f},{ey:.1f}")
            label_at = ((x1 + x2) / 2.0, lane - 9.0)
        elif kind == "flow":
            if vertical:
                x1, y1 = a.cx, a.y + a.h
                x2, y2 = b.cx, b.y
                ey, ex = y2 - shrink, x2
                my = (y1 + ey) / 2.0
                d = (f"M{x1:.1f},{y1:.1f} L{x1:.1f},{my:.1f} "
                     f"L{x2:.1f},{my:.1f} L{x2:.1f},{ey:.1f}")
                ang = math.pi / 2.0
            else:
                mx = (x1 + ex) / 2.0
                d = f"M{x1:.1f},{y1:.1f} L{mx:.1f},{y1:.1f} L{mx:.1f},{ey:.1f} L{ex:.1f},{ey:.1f}"
                ang = 0.0 if abs(ex - mx) > 1 else math.atan2(ey - y1, 0.001)
        else:
            dx, dy = ex - x1, ey - y1
            k = 0.32
            c1x, c1y = x1 + dx * k, y1 + dy * k * 0.2
            c2x, c2y = ex - dx * k, ey - dy * k * 0.2
            d = f"M{x1:.1f},{y1:.1f} C{c1x:.1f},{c1y:.1f} {c2x:.1f},{c2y:.1f} {ex:.1f},{ey:.1f}"
            ang = math.atan2(ey - c2y, ex - c2x)

        out.append(f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="{stroke_w:.1f}"{dash_attr} '
                   f'stroke-linecap="round" stroke-linejoin="round"/>')
        if kind != "binding":
            out.append(head(kind, x2, y2, ang, colour, stroke_w, HEAD_FILLED.get(ev, True)))
        if rel.get("modifier") and rel["modifier"] in by_id:
            m = by_id[rel["modifier"]]
            mid_x, mid_y = (x1 + ex) / 2.0, (y1 + ey) / 2.0
            mx, my = rect_edge(m, mid_x, mid_y)
            out.append(f'<line x1="{mx:.1f}" y1="{my:.1f}" x2="{mid_x:.1f}" y2="{mid_y:.1f}" '
                       f'stroke="{colour}" stroke-width="{stroke_w*0.8:.1f}"/>')
            out.append(head("catalysis", mid_x, mid_y,
                            math.atan2(mid_y - my, mid_x - mx), colour, stroke_w))
        if rel.get("label"):
            if vertical and kind == "flow" and not label_at:
                label_at = (x2 + 6.0, (y1 + ey) / 2.0 - 4.0)
            lx, ly = label_at or ((x1 + ex) / 2.0, (y1 + ey) / 2.0 - 8.0)
            out.append(f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="{font*0.8:.1f}" text-anchor="middle" '
                       f'fill="{colour}">{esc(rel["label"])}</text>')

    # Labels that moved out of their container: stacked beside it, each tied
    # to its glyph by a thin leader. The drawing keeps its size and shape and
    # the text is still readable, which is what a published figure does.
    externals = {}
    above = []
    for n in nodes:
        if n.spec.get("_label_mode") != "outside":
            continue
        if n.spec.get("_label_side") == "above":
            above.append(n)
        else:
            externals.setdefault(n.spec.get("_parent"), []).append(n)

    # A membrane protein is named above the membrane. The names are laid out
    # left to right and pushed apart where two receptors sit close together,
    # so the band over a cell reads as a row of labels and not as a pile.
    placed = []
    for n in sorted(above, key=lambda m: m.cx):
        half = text_width(n.label, font * 0.9) / 2.0
        cx = n.cx
        for pcx, phalf in placed:
            if abs(cx - pcx) < half + phalf + 8.0:
                cx = pcx + phalf + half + 8.0
        placed.append((cx, half))
        ly = n.y - 7.0
        out.append(f'<text x="{cx:.1f}" y="{ly:.1f}" font-size="{font*0.9:.1f}" '
                   f'text-anchor="middle" fill="{INK}">{esc(n.label)}</text>')
        if abs(cx - n.cx) > 2.0:
            out.append(f'<path d="M{n.cx:.1f},{n.y - 2.0:.1f} L{cx:.1f},{ly - font*0.32:.1f}" '
                       f'fill="none" stroke="{CANONICAL}" stroke-width="{sw*0.5:.1f}"/>')
        width = max(width, cx + half + MARGIN)

    for pid, group in externals.items():
        r = rects.get(pid)
        if not r:
            continue
        lx = r["x"] + r["w"] + 16.0
        ly = r["y"] + 26.0
        for n in sorted(group, key=lambda m: m.y):
            colour, _ = pal.entity(n.spec, n.role)
            out.append(f'<path d="M{n.cx:.1f},{n.cy:.1f} L{lx-6:.1f},{ly-4:.1f}" '
                       f'fill="none" stroke="{CANONICAL}" stroke-width="{sw*0.55:.1f}"/>')
            out.append(f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="{font*0.92:.1f}" '
                       f'fill="{INK}">{esc(n.label)}</text>')
            ly += font * 1.15
            if n.spec.get("qualifier"):
                out.append(f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="{font*0.74:.1f}" '
                           f'fill="#6b7780">{esc(n.spec["qualifier"])}</text>')
                ly += font * 1.05
            ly += font * 0.5
            width = max(width, lx + text_width(n.label, font * 0.92) + MARGIN)

    # entities
    for n in nodes:
        colour, fill = pal.entity(n.spec, n.role)
        nsw = sw * PROMINENCE[n.prom][0] * (1.3 if n.role == "contribution" and not pal.explanatory else 1.0)
        nfont = font * n.fsc
        used["roles"].add(n.role)
        out.append(entity_shape(n, colour, nsw, fill))

        if n.has_icon:
            art = n.spec["asset"]["_svg"]
            # Health Icons and others paint with fill="currentColor", which no
            # rewrite of colour values can touch; without an explicit colour on
            # the wrapper the icon inherits black and arrives at full strength.
            ink = pal.icon_ink(n.spec, n.role)
            if not pal.keep_icon_colour(n.role):
                art = desaturate_svg(art)
            # With the name outside, the whole node is the drawing.
            ih = (n.h - 4.0) if n.spec.get("_label_mode") == "outside" else ICON_H - 6
            out.append(f'<g color="{ink}">'
                       + embed_svg(art, n.x + 4, n.y + 2, n.w - 8, ih,
                                   re.sub(r"[^A-Za-z0-9]", "", n.id))
                       + '</g>')
        elif n.pictorial:
            out.append(generic_glyph(n.cls, n.x + 4, n.y + 4, n.w - 8, ICON_H - 6, colour, nsw))

        # label block: name, then qualifier set smaller and lighter beneath it
        top = n.y + (ICON_H if (n.has_icon or n.pictorial) else 0.0)
        body_h = n.h - (ICON_H if (n.has_icon or n.pictorial) else 0.0)
        nlines = len(n.lines) + len(n.qlines) * 0.78
        ty = top + (body_h - (nlines - 1) * nfont * 1.35) / 2.0 + nfont * 0.34
        if n.cls == "process":
            for ln in n.lines:
                out.append(f'<text x="{n.x + PROCESS_SIDE + 10:.1f}" y="{ty:.1f}" '
                           f'font-size="{nfont:.1f}" fill="{INK}">{esc(ln)}</text>')
                ty += nfont * 1.35
        else:
            for ln in n.lines:
                out.append(f'<text x="{n.cx:.1f}" y="{ty:.1f}" font-size="{nfont:.1f}" '
                           f'text-anchor="middle" fill="{INK}">{esc(ln)}</text>')
                ty += nfont * 1.35
            for ln in n.qlines:
                out.append(f'<text x="{n.cx:.1f}" y="{ty:.1f}" font-size="{nfont*0.78:.1f}" '
                           f'text-anchor="middle" fill="#6b7780">{esc(ln)}</text>')
                ty += nfont * 1.05

        for i, st in enumerate(n.spec.get("state", []) or []):
            sxc, syc = n.x + 12 + i * 24, n.y
            out.append(f'<circle cx="{sxc:.1f}" cy="{syc:.1f}" r="11" fill="#ffffff" stroke="{colour}" stroke-width="{sw*0.85:.1f}"/>')
            out.append(f'<text x="{sxc:.1f}" y="{syc + font*0.3:.1f}" font-size="{font*0.72:.1f}" '
                       f'text-anchor="middle" fill="{INK}">{esc(st.get("label", ""))}</text>')

    # legend, mandatory above four lexicon elements
    if not pal.legend_needs_role():
        used["roles"] = set()
    n_elements = len(used["relations"]) + len(used["evidence"]) + len(used["roles"])
    legend_h = 0.0
    if n_elements > 4:
        legend_h, legend_svg = build_legend(used, width, height, font, sw, accent)
        out.append(legend_svg)

    total_h = height + legend_h
    # Written last: the lane router and the legend both grow the canvas after
    # the glyphs are laid out, and a background sized before them leaves the
    # lower part of the figure transparent.
    out[1] = f'<rect x="0" y="0" width="{width:.0f}" height="{total_h:.0f}" fill="#ffffff"/>' 
    out[0] = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {total_h:.0f}" '
              f'{size_attrs(cfg, width, total_h)} font-family="Helvetica, Arial, sans-serif">')
    out.append("</svg>")
    return "\n".join(out), width, total_h, fit_note


def size_attrs(cfg, w, h):
    if "out_width_mm" in cfg:
        mm = cfg["out_width_mm"]
        return f'width="{mm:.1f}mm" height="{mm*h/w:.1f}mm"'
    px = cfg["out_width_px"]
    return f'width="{px}" height="{px*h/w:.0f}"'


LEGEND_TEXT = {
    "production": "production / conversion",
    "stimulation": "stimulation",
    "catalysis": "catalysis",
    "inhibition": "inhibition",
    "transport": "transport",
    "binding": "binding",
    "flow": "procedural flow",
    "established": "established (cited)",
    "demonstrated_here": "demonstrated here",
    "associated": "associated, causality not shown",
    "hypothesized": "hypothesised",
    "canonical": "canonical background",
    "contribution": "contribution of this work",
}


def build_legend(used, width, top, font, sw, accent):
    rows = []
    for k in ("production", "stimulation", "catalysis", "inhibition", "transport", "binding", "flow"):
        if k in used["relations"]:
            rows.append(("relation", k))
    for k in ("established", "demonstrated_here", "associated", "hypothesized"):
        if k in used["evidence"]:
            rows.append(("evidence", k))
    for k in ("canonical", "contribution"):
        if k in used["roles"]:
            rows.append(("role", k))

    cols = 2
    per_col = (len(rows) + cols - 1) // cols
    row_h = 26.0
    h = 30.0 + per_col * row_h + 16.0
    y0 = top + 6.0
    svg = [f'<line x1="{MARGIN}" y1="{y0:.1f}" x2="{width-MARGIN:.1f}" y2="{y0:.1f}" stroke="#dddddd" stroke-width="1"/>']

    for i, (group, key) in enumerate(rows):
        col, row = i // per_col, i % per_col
        x = MARGIN + col * (width - 2 * MARGIN) / cols
        y = y0 + 28.0 + row * row_h
        colour = accent if key == "contribution" else CANONICAL if key == "canonical" else INK
        lw = sw * (1.45 if key == "contribution" else 0.85 if key == "canonical" else 1.0)
        dash = DASH.get(key) if group == "evidence" else None
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        kind = key if group == "relation" else "production"
        if kind == "flow":
            svg.append(f'<path d="M{x:.1f},{y-7:.1f} L{x+34:.1f},{y-7:.1f} L{x+34:.1f},{y:.1f} L{x+54:.1f},{y:.1f}" '
                       f'fill="none" stroke="{colour}" stroke-width="{lw:.1f}"/>')
            svg.append(head("production", x + 68, y, 0.0, colour, lw, True))
        else:
            end = x + 68 - SHRINK.get(kind, HEAD_LEN)
            svg.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{end:.1f}" y2="{y:.1f}" stroke="{colour}" '
                       f'stroke-width="{lw:.1f}"{dash_attr} stroke-linecap="round"/>')
            if kind != "binding":
                filled = HEAD_FILLED.get(key, True) if group == "evidence" else True
                svg.append(head(kind, x + 68, y, 0.0, colour, lw, filled))
        svg.append(f'<text x="{x+84:.1f}" y="{y + font*0.34:.1f}" font-size="{font*0.82:.1f}" '
                   f'fill="{INK}">{esc(LEGEND_TEXT[key])}</text>')
    return h, "\n".join(svg)


# --------------------------------------------------------------------------
# Caption and attribution, generated from the spec
# --------------------------------------------------------------------------

def caption(spec):
    meta = spec["meta"]
    lines = [f"**{meta['title']}.** {meta['claim'].strip()}", ""]
    ents = {e["id"]: e.get("label", e["id"]) for e in spec["entities"]}

    new = [r for r in spec["relations"] if r.get("evidence") == "demonstrated_here"]
    hyp = [r for r in spec["relations"] if r.get("evidence") == "hypothesized"]
    assoc = [r for r in spec["relations"] if r.get("evidence") == "associated"]

    verb = {
        "production": "is converted to", "stimulation": "activates",
        "catalysis": "catalyses", "inhibition": "inhibits",
        "transport": "translocates to", "binding": "binds",
        "flow": "leads to",
    }
    if new:
        lines.append("Shown in this work: " + "; ".join(
            f"{ents.get(r['from'])} {verb.get(r['type'], r['type'])} {ents.get(r['to'])}"
            for r in new) + ".")
    if assoc:
        lines.append("Shown as association without demonstrated causality (long dash): " + "; ".join(
            f"{ents.get(r['from'])} to {ents.get(r['to'])}" for r in assoc) + ".")
    if hyp:
        lines.append("Proposed and not tested (dotted, unfilled head): " + "; ".join(
            f"{ents.get(r['from'])} to {ents.get(r['to'])}" for r in hyp) + ".")

    cited = sorted({r["source"] for r in spec["relations"]
                    if r.get("source") and not r["source"].lower().startswith("this work")})
    if cited:
        lines.append("")
        lines.append("Cited for the established steps: " + ", ".join(cited) + ".")

    # Only assets that actually carry an attribution obligation appear here.
    # A CC0 icon needs no credit, and printing one anyway trains authors to
    # ignore the credit line.
    credited = [a for a in (spec.get("provenance", {}).get("assets", []) or [])
                if a.get("attribution")]
    if credited:
        lines.append("")
        lines.append("Image credits: " + " ".join(a["attribution"] for a in credited))
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------


def legibility(spec, variant, width_units):
    """Report the smallest type size at the declared output width.

    Below 6 pt the figure fails any journal; a graphical abstract needs 12 pt.
    At thumbnail width the figure is not expected to stay readable word by
    word, but its main message must still survive, which only the eye judges.
    """
    cfg = VARIANTS[variant]
    font_units = cfg["font"]
    if "out_width_mm" in cfg:
        mm_per_unit = cfg["out_width_mm"] / width_units
        pt = font_units * mm_per_unit * 72.0 / 25.4
        floor = 12.0 if spec["meta"].get("figure_class") == "graphical_abstract" else 6.0
        verdict = "ok" if pt >= floor else f"TOO SMALL, floor is {floor:.0f} pt"
        return (f"body type {pt:.1f} pt at {cfg['out_width_mm']:.0f} mm wide: {verdict}. "
                f"Aspect ratio {width_units:.0f} units wide.")
    px = cfg["out_width_px"]
    return (f"raster width {px} px, body type about {font_units * px / width_units:.1f} px. "
            "Check by eye that the message survives.")


def main():
    ap = argparse.ArgumentParser(description="Compile a figure-spec into SVG.")
    ap.add_argument("spec")
    ap.add_argument("-o", "--out")
    ap.add_argument("--variant", choices=sorted(VARIANTS), default="journal")
    ap.add_argument("--caption", help="write the generated caption to this path")
    ap.add_argument("--check", action="store_true", help="validate only")
    ap.add_argument("--resolve-assets", action="store_true",
                    help="resolve pictograms from the open registry (network)")
    ap.add_argument("--strict-assets", action="store_true",
                    help="refuse to render when a pictogram cannot be resolved exactly")
    args = ap.parse_args()

    spec = load_spec(args.spec)
    if args.resolve_assets or args.strict_assets:
        for m in resolve_spec_assets(spec, strict=args.strict_assets):
            print(m, file=sys.stderr)
    errors, warnings = validate(spec)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    if args.check:
        print("spec valid")
        return

    svg, w, h, fit_note = render(spec, args.variant)
    out = args.out or os.path.splitext(args.spec)[0] + f".{args.variant}.svg"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"wrote {out} ({w:.0f} x {h:.0f} units)")
    if fit_note:
        print(f"layout: {fit_note}")
    print(legibility(spec, args.variant, w))

    if args.caption:
        with open(args.caption, "w", encoding="utf-8") as fh:
            fh.write(caption(spec))
        print(f"wrote {args.caption}")


if __name__ == "__main__":
    main()
