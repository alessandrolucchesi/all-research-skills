#!/usr/bin/env python3
"""
figure_export: emit the compiled figure in the format its readers need.

Output follows the kind of figure, not a preference:

- **PPTX, native shapes**, for diagrams and flows. Revision is where a figure
  actually lives, and a co-author cannot revise an SVG. Every entity is a real
  shape and every relation a real connector, so the figure can be edited in
  the tool the group already uses without anyone rebuilding the geometry.
- **SVG plus PNG** for pictographic representations, where the artwork is the
  content and editability buys nothing.

Both are generated from the same layout as the SVG renderer, so the three
never drift apart.

Dependencies: python-pptx for the deck, cairosvg for the PNG. Each is needed
only for its own format.
"""

from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import figure_render as FR          # noqa: E402
from ontology import depiction_of   # noqa: E402

# Figure classes whose readers revise them: these default to PPTX.
EDITABLE_CLASSES = {
    "clinical_algorithm", "study_design", "consort_flow", "prisma_flow",
    "stard_flow",
}

MM_PER_UNIT_DEFAULT = 178.0


def default_outputs(spec):
    cls = spec["meta"].get("figure_class", "")
    if cls in EDITABLE_CLASSES:
        return ["pptx", "svg"]
    return ["svg", "png"]


# --------------------------------------------------------------------------
# PNG
# --------------------------------------------------------------------------

def to_png(svg_path, png_path, width_px=2400):
    try:
        import cairosvg
    except ImportError:
        raise SystemExit("PNG output needs cairosvg: pip install cairosvg")
    cairosvg.svg2png(url=svg_path, write_to=png_path,
                     output_width=width_px, background_color="white")
    return png_path


# --------------------------------------------------------------------------
# PPTX
# --------------------------------------------------------------------------

def _rgb(hexstr):
    from pptx.dml.color import RGBColor
    h = hexstr.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _arrow(connector, kind, evidence):
    """OOXML arrowheads. python-pptx has no API for these, so the line
    element is extended directly."""
    from lxml import etree
    from pptx.oxml.ns import qn
    ln = connector.line._get_or_add_ln()
    end = {
        "production": "triangle", "flow": "triangle",
        "stimulation": "arrow", "transport": "arrow",
        "catalysis": "oval", "inhibition": "none", "binding": "none",
    }.get(kind, "triangle")
    if end != "none":
        el = etree.SubElement(ln, qn("a:tailEnd"))
        el.set("type", end)
        el.set("w", "med")
        el.set("len", "med")


def _dash(connector, evidence):
    from pptx.enum.dml import MSO_LINE_DASH_STYLE
    style = {
        "associated": MSO_LINE_DASH_STYLE.DASH,
        "hypothesized": MSO_LINE_DASH_STYLE.ROUND_DOT,
    }.get(evidence)
    if style is not None:
        connector.line.dash_style = style


def parity_report(spec, nodes, pictures, routed, legend_in_pptx):
    """What the deck does not reproduce from the figure.

    The editable artefact is the one that circulates, and a co-author cannot
    tell "the author drew it badly" from "the export lost it". So the deck
    declares its own divergence, on the slide, until export parity lands.
    """
    gaps = []
    want_pics = sum(1 for n in nodes if n.spec.get("asset", {}).get("_svg"))
    if want_pics > pictures:
        gaps.append(f"{want_pics - pictures} of {want_pics} pictograms not placed")
    if routed:
        gaps.append(f"{routed} routed arc{'s' if routed > 1 else ''} flattened to straight lines")
    if not legend_in_pptx:
        gaps.append("legend not reproduced")
    return gaps


def to_pptx(spec, path, width_mm=MM_PER_UNIT_DEFAULT, variant="journal", note_divergence=True):
    from pptx import Presentation
    from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
    from pptx.util import Mm, Pt

    cfg = FR.VARIANTS[variant]
    accent = spec["meta"].get("accent_colour", "#0b6ea8")
    font_units = cfg["font"]

    nodes, by_id, rects, w_units, h_units = FR.layout(spec, font=font_units)
    k = width_mm / w_units                       # mm per layout unit
    def X(v):
        return Mm(v * k)

    prs = Presentation()
    # PowerPoint refuses a slide under one inch in either direction, and a
    # figure laid out along one axis can easily be shorter than that.
    height_mm = max(26.0, h_units * k)
    prs.slide_width = Mm(width_mm)
    prs.slide_height = Mm(height_mm)
    slide = prs.slides.add_slide(prs.slide_layouts[6])     # blank
    pt_per_unit = k * 72.0 / 25.4

    # compartments first, so they sit behind
    for cid, r in sorted(rects.items(), key=lambda kv: kv[1]["depth"]):
        box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                     X(r["x"]), X(r["y"]), X(r["w"]), X(r["h"]))
        box.fill.solid()
        box.fill.fore_color.rgb = _rgb(FR.TINT if r["type"] == "physical" else "#ffffff")
        if r["type"] != "physical":
            box.fill.background()
        box.line.color.rgb = _rgb(FR.INK)
        box.line.width = Pt(cfg["stroke"] * pt_per_unit * 0.5)
        if r["type"] != "physical":
            from pptx.enum.dml import MSO_LINE_DASH_STYLE
            box.line.dash_style = MSO_LINE_DASH_STYLE.DASH
        tf = box.text_frame
        tf.text = r["label"].upper()
        p = tf.paragraphs[0]
        p.font.size = Pt(max(6.0, font_units * pt_per_unit * 0.78))
        p.font.color.rgb = _rgb(FR.LABEL_MUTED)
        from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
        tf.vertical_anchor = MSO_ANCHOR.TOP
        p.alignment = PP_ALIGN.LEFT

    shape_for = {
        "small_molecule": MSO_SHAPE.ROUNDED_RECTANGLE,
        "macromolecule": MSO_SHAPE.ROUNDED_RECTANGLE,
        "nucleic_acid": MSO_SHAPE.ROUNDED_RECTANGLE,
        "complex": MSO_SHAPE.OCTAGON,
        "process": MSO_SHAPE.RECTANGLE,
        "step": MSO_SHAPE.RECTANGLE,
        "state": MSO_SHAPE.PENTAGON,
        "measure": MSO_SHAPE.RECTANGLE,
        "intervention": MSO_SHAPE.ROUNDED_RECTANGLE,
        "unspecified": MSO_SHAPE.RECTANGLE,
    }

    handles = {}
    for n in nodes:
        colour = accent if n.role == "contribution" else FR.INK
        pictorial = depiction_of(n.spec) == "pictogram"
        if pictorial and n.spec.get("asset", {}).get("_svg"):
            # The artwork cannot be a native shape; it is placed as an image
            # and the label stays editable beside it.
            png = _icon_png(n)
            if png:
                pic = slide.shapes.add_picture(png, X(n.x), X(n.y),
                                               height=X(FR.ICON_H))
                handles[n.id] = pic
        shp = slide.shapes.add_shape(
            shape_for.get(n.cls, MSO_SHAPE.ROUNDED_RECTANGLE),
            X(n.x), X(n.y + (FR.ICON_H if pictorial else 0.0)),
            X(n.w), X(FR.NODE_H))
        shp.fill.solid()
        shp.fill.fore_color.rgb = _rgb("#ffffff")
        if pictorial:
            shp.fill.background()
            shp.line.fill.background()
        else:
            shp.line.color.rgb = _rgb(colour)
            shp.line.width = Pt(cfg["stroke"] * pt_per_unit * 0.5)
        tf = shp.text_frame
        tf.word_wrap = True
        tf.text = n.label
        p = tf.paragraphs[0]
        p.font.size = Pt(max(6.0, font_units * pt_per_unit))
        p.font.color.rgb = _rgb(FR.INK)
        handles.setdefault(n.id, shp)

    for rel in spec.get("relations", []):
        a, b = by_id.get(rel["from"]), by_id.get(rel["to"])
        if not a or not b:
            continue
        role = rel.get("role", "canonical")
        ev = rel.get("evidence", "established")
        colour = accent if role == "contribution" else (
            FR.CANONICAL if ev == "established" else FR.INK)
        x1, y1 = a.cx, a.cy
        x2, y2 = b.cx, b.cy
        conn = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                                          X(x1), X(y1), X(x2), X(y2))
        conn.line.color.rgb = _rgb(colour)
        conn.line.width = Pt(cfg["stroke"] * pt_per_unit * (0.75 if role == "contribution" else 0.5))
        _dash(conn, ev)
        _arrow(conn, rel.get("type", "production"), ev)
        try:    # glue the ends so the connector follows a shape that is moved
            conn.begin_connect(handles[a.id], 3)
            conn.end_connect(handles[b.id], 1)
        except Exception:
            pass

    # Count what the SVG would have routed: any arc the renderer diverts into
    # a lane is a straight preset connector here.
    routed = 0
    for rel in spec.get("relations", []):
        a, b = by_id.get(rel["from"]), by_id.get(rel["to"])
        if a and b and rel.get("type") != "flow" and abs(a.rank - b.rank) > 1:
            routed += 1
    pictures = sum(1 for sh in slide.shapes if sh.shape_type is not None
                   and sh.__class__.__name__ == "Picture")
    gaps = parity_report(spec, nodes, pictures, routed, legend_in_pptx=False)
    if gaps and note_divergence:
        tb = slide.shapes.add_textbox(X(0), Mm(height_mm) - Mm(6), X(w_units), Mm(5.5))
        tf = tb.text_frame
        tf.text = "Export preview, not the figure: " + "; ".join(gaps) + "."
        pr = tf.paragraphs[0]
        pr.font.size = Pt(7)
        pr.font.italic = True
        pr.font.color.rgb = _rgb("#b3261e")
    prs.save(path)
    return path, gaps


def _icon_png(node):
    """Rasterise a resolved icon for placement in the deck."""
    try:
        import cairosvg
    except ImportError:
        return None
    import tempfile
    art = node.spec["asset"]["_svg"]
    if node.role != "contribution":
        art = FR.desaturate_svg(art)
    fd, out = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        cairosvg.svg2png(bytestring=art.encode("utf-8"), write_to=out,
                         output_height=600, background_color=None)
        return out
    except Exception:
        return None


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Export a compiled figure.")
    ap.add_argument("spec")
    ap.add_argument("--stem", help="output path without extension")
    ap.add_argument("--formats", help="comma separated: svg,png,pptx (default: by figure class)")
    ap.add_argument("--variant", choices=sorted(FR.VARIANTS), default="journal")
    ap.add_argument("--resolve-assets", action="store_true")
    ap.add_argument("--no-divergence-note", action="store_true",
                    help="omit the on-slide note about what the deck does not reproduce")
    args = ap.parse_args()

    spec = FR.load_spec(args.spec)
    if args.resolve_assets:
        for m in FR.resolve_spec_assets(spec):
            print(m, file=sys.stderr)
    errors, warnings = FR.validate(spec)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    stem = args.stem or os.path.splitext(args.spec)[0]
    formats = (args.formats.split(",") if args.formats else default_outputs(spec))
    made = []
    svg_path = f"{stem}.svg"
    if "svg" in formats or "png" in formats:
        svg, w, h, note = FR.render(spec, args.variant)
        with open(svg_path, "w", encoding="utf-8") as fh:
            fh.write(svg)
        made.append(svg_path)
        if note:
            print(f"layout: {note}")
    if "png" in formats:
        made.append(to_png(svg_path, f"{stem}.png"))
    if "pptx" in formats:
        out_path, gaps = to_pptx(spec, f"{stem}.pptx", variant=args.variant,
                                 note_divergence=not args.no_divergence_note)
        made.append(out_path)
        if gaps:
            print("PARITY: the deck is not a faithful copy of the figure:", file=sys.stderr)
            for g in gaps:
                print(f"  - {g}", file=sys.stderr)
            print("  The slide carries a visible note saying so. Send the SVG or PDF "
                  "as the figure of record.", file=sys.stderr)
    for m in made:
        print(f"wrote {m}")


if __name__ == "__main__":
    main()
