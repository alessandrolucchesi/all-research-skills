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

PICTOGRAM_CLASSES = {"cell", "tissue", "organ", "subject"}
GEOMETRIC_CLASSES = {
    "macromolecule", "nucleic_acid", "small_molecule",
    "complex", "unspecified", "process",
}

# Layout metrics, in user units
GUTTER = 78.0       # horizontal clearance between rank columns
COL_W = 210.0
ROW_H = 86.0
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
        if e["class"] in PICTOGRAM_CLASSES and not e.get("asset"):
            warnings.append(
                f"entity {e['id']}: class '{e['class']}' expects a registry pictogram; rendered as a placeholder"
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
                 "rank", "row", "modifier")

    def __init__(self, e):
        self.modifier = False
        self.id = e["id"]
        self.label = e.get("label", e["id"])
        self.cls = e.get("class", "unspecified")
        self.comp = e.get("compartment")
        self.role = e.get("role", "canonical")
        self.spec = e
        self.w = max(NODE_MIN_W, 9.0 * len(self.label) + 34.0)
        self.h = NODE_H
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


def layout(spec, gutter=GUTTER):
    nodes = [Node(e) for e in spec["entities"]]
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
        rows = max((len(v) for v in lanes.values()), default=1)
        for rk, group in lanes.items():
            for k, n in enumerate(group):
                n.x = MARGIN + PAD + colx[rk]
                n.y = top + k * ROW_H
        y = top + rows * ROW_H + 20.0
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
                 label=comp_by_id[cid].get("label", cid), depth=depth)
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


def entity_shape(n, colour, sw):
    x, y, w, h = n.x, n.y, n.w, n.h
    dash = ""
    if n.cls == "macromolecule":
        return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="9" fill="#ffffff" stroke="{colour}" stroke-width="{sw:.1f}"/>'
    if n.cls == "nucleic_acid":
        r = 12
        return (f'<path d="M{x:.1f},{y:.1f} h{w:.1f} v{h-r:.1f} a{r},{r} 0 0 1 -{r},{r} '
                f'h-{w-2*r:.1f} a{r},{r} 0 0 1 -{r},-{r} z" fill="#ffffff" stroke="{colour}" stroke-width="{sw:.1f}"/>')
    if n.cls == "small_molecule":
        return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{h/2:.1f}" fill="#ffffff" stroke="{colour}" stroke-width="{sw:.1f}"/>'
    if n.cls == "complex":
        c = 11
        return (f'<path d="M{x+c:.1f},{y:.1f} h{w-2*c:.1f} l{c},{c} v{h-2*c:.1f} l-{c},{c} '
                f'h-{w-2*c:.1f} l-{c},-{c} v-{h-2*c:.1f} z" fill="#ffffff" stroke="{colour}" stroke-width="{sw:.1f}"/>')
    if n.cls == "process":
        return f'<rect x="{n.cx-11:.1f}" y="{n.cy-11:.1f}" width="22" height="22" fill="#ffffff" stroke="{colour}" stroke-width="{sw:.1f}"/>'
    if n.cls in PICTOGRAM_CLASSES:
        dash = ' stroke-dasharray="1 4"' if not n.spec.get("asset") else ""
        return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="9" '
                f'fill="#ffffff" stroke="{colour}" stroke-width="{sw:.1f}"{dash}/>')
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
    accent = spec["meta"].get("accent_colour", "#0b6ea8")
    font = cfg["font"]
    sw = cfg["stroke"]

    nodes, by_id, rects, width, height = layout(spec)

    # Fit to the physical column width. Type size is a hard floor, so the
    # canvas is what gives: tighten the gutters until the body type clears
    # the floor, and refuse if tightening is not enough.
    fit_note = None
    budget = type_budget(spec, cfg, width)
    if budget and width > budget:
        for g in (66.0, 56.0, 48.0, 42.0):
            nodes, by_id, rects, width, height = layout(spec, gutter=g)
            if width <= budget:
                fit_note = f"gutters tightened to {g:.0f} units to clear the type floor"
                break
        else:
            fit_note = ("CANNOT FIT: body type stays below the floor at this width. "
                        "Reduce the number of semantic units or split the figure.")

    used = {"relations": set(), "evidence": set(), "roles": set(), "comp_types": set()}

    out = []
    out.append("")  # placeholder for the opening tag
    out.append(f'<rect x="0" y="0" width="{width:.0f}" height="{height:.0f}" fill="#ffffff"/>')

    # compartments, outermost first
    for cid, r in sorted(rects.items(), key=lambda kv: kv[1]["depth"]):
        used["comp_types"].add(r["type"])
        if r["type"] == "physical":
            out.append(f'<rect x="{r["x"]:.1f}" y="{r["y"]:.1f}" width="{r["w"]:.1f}" height="{r["h"]:.1f}" '
                       f'rx="14" fill="{TINT}" stroke="{INK}" stroke-width="{sw:.1f}"/>')
        else:
            out.append(f'<rect x="{r["x"]:.1f}" y="{r["y"]:.1f}" width="{r["w"]:.1f}" height="{r["h"]:.1f}" '
                       f'rx="14" fill="none" stroke="{INK}" stroke-width="{sw:.1f}" stroke-dasharray="8 6"/>')
        out.append(f'<text x="{r["x"]+14:.1f}" y="{r["y"]+20:.1f}" font-size="{font*0.78:.1f}" '
                   f'fill="{LABEL_MUTED}" letter-spacing="0.6">{esc(r["label"].upper())}</text>')

    # relations under the nodes
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

        colour = accent if role == "contribution" else CANONICAL if ev == "established" else INK
        if role == "contribution":
            stroke_w = sw * 1.45
        elif ev == "established":
            stroke_w = sw * 0.85
        else:
            stroke_w = sw
        dash = DASH.get(ev)
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        if kind == "transport":
            stroke_w *= 0.6

        x1, y1 = rect_edge(a, b.cx, b.cy)
        x2, y2 = rect_edge(b, a.cx, a.cy)
        ang = math.atan2(y2 - y1, x2 - x1)
        shrink = SHRINK.get(kind, HEAD_LEN)
        ex, ey = x2 - math.cos(ang) * shrink, y2 - math.sin(ang) * shrink

        back_edge = b.rank < a.rank and kind != "flow"
        if back_edge:
            # Feedback arcs travel along a clear lane below both nodes instead
            # of cutting across whatever sits between them.
            bus = max(a.y + a.h, b.y + b.h) + 34.0
            height = max(height, bus + 26.0)
            x1, y1 = a.cx, a.y + a.h
            x2, y2 = b.cx, b.y + b.h
            ey = y2 + shrink
            d = (f"M{x1:.1f},{y1:.1f} L{x1:.1f},{bus:.1f} "
                 f"L{x2:.1f},{bus:.1f} L{x2:.1f},{ey:.1f}")
            ang = -math.pi / 2.0
            ex = x2
        elif kind == "flow":
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
            lx, ly = (x1 + ex) / 2.0, (y1 + ey) / 2.0 - 8.0
            out.append(f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="{font*0.8:.1f}" text-anchor="middle" '
                       f'fill="{colour}">{esc(rel["label"])}</text>')

    # entities
    for n in nodes:
        colour = accent if n.role == "contribution" else INK
        nsw = sw * (1.3 if n.role == "contribution" else 1.0)
        used["roles"].add(n.role)
        out.append(entity_shape(n, colour, nsw))
        out.append(f'<text x="{n.cx:.1f}" y="{n.cy + font*0.36:.1f}" font-size="{font:.1f}" '
                   f'text-anchor="middle" fill="{INK}">{esc(n.label)}</text>')
        for i, st in enumerate(n.spec.get("state", []) or []):
            sxc, syc = n.x + 12 + i * 24, n.y
            out.append(f'<circle cx="{sxc:.1f}" cy="{syc:.1f}" r="11" fill="#ffffff" stroke="{colour}" stroke-width="{sw*0.85:.1f}"/>')
            out.append(f'<text x="{sxc:.1f}" y="{syc + font*0.3:.1f}" font-size="{font*0.72:.1f}" '
                       f'text-anchor="middle" fill="{INK}">{esc(st.get("label", ""))}</text>')

    # legend, mandatory above four lexicon elements
    n_elements = len(used["relations"]) + len(used["evidence"]) + len(used["roles"])
    legend_h = 0.0
    if n_elements > 4:
        legend_h, legend_svg = build_legend(used, width, height, font, sw, accent)
        out.append(legend_svg)

    total_h = height + legend_h
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

    assets = spec.get("provenance", {}).get("assets", []) or []
    if assets:
        lines.append("")
        lines.append("Image credits: " + " ".join(
            a.get("attribution") or f"{a.get('source_id')} {a.get('asset_id')} ({a.get('license')})"
            for a in assets))
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
    args = ap.parse_args()

    spec = load_spec(args.spec)
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
