#!/usr/bin/env python3
"""
derive: geometry derived from open assets, and the local store that keeps it.

Why this exists. A mechanism figure needs containers that say where the reader
is, and hand-drawing one template per anatomy would tie the tool to whichever
field drew them. The open libraries already hold thousands of anatomical
shapes in every discipline, so the containers come from there.

The measurement that shaped the design. The first plan was to use a resolved
silhouette as the container boundary and place contents inside its outline.
Measured across seven shapes from three libraries, the largest rectangle that
fits inside the inked area was: kidney 13%, liver 19%, stomach 23%, vessel
27%, macrophage 38%, lung 41%, megakaryocyte 50% of the bounding box. Library
shapes are lobed, thin or irregular, so containing anything inside their
outline fails six times out of seven.

So the roles split:

- **Geometry** is ours: four neutral container shapes, no domain knowledge.
- **Anatomical identity** comes from the library, placed as a low-contrast
  anchor behind the contents. This is where generality lives: a lung here, a
  leaf for a botanist, a reactor vessel for a chemist, with no code change.
- **Frame mode**, contents inside the silhouette itself, is kept but is the
  exception, taken only when the measured inscribed fraction clears the
  threshold. The decision is per asset and automatic.

The inscribed rectangle is still computed in anchor mode, because its aspect
and position say what proportion the container should take and where inside
the anchor the contents belong. A vessel measures 0.28 wide-to-tall and wants
a tall container; a lung measures 1.33 and wants a wide one.

The store. Geometry costs one rasterisation per asset, so it is cached under
SCIFIG_HOME (default ~/.scientific-figures), never inside the repository.
Composed derivatives live there too, and the library grows with use. Every
entry carries the licence and provenance of every source that went into it,
because a derivative of a CC BY asset inherits the attribution obligation and
the chain has to survive composition: a cell composed from two Servier icons
credits both, and so does a third figure that reuses it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time

STORE = os.environ.get("SCIFIG_HOME") or os.path.join(
    os.path.expanduser("~"), ".scientific-figures")
GEOM_DIR = os.path.join(STORE, "geometry")
DERIVED_DIR = os.path.join(STORE, "derived")

# At or above this inscribed fraction the contents can live inside the
# silhouette. Set from the measurement above: it admits a round cell and
# refuses a lobed organ, which is the behaviour we want.
FRAME_THRESHOLD = 0.45

# A pictorial container below this rendered width is mush, so it falls back to
# a labelled geometric region. Roughly 12 mm at double-column width.
MIN_PICTORIAL_UNITS = 70.0


def _ensure(d):
    os.makedirs(d, exist_ok=True)
    return d


def asset_key(source_id, asset_id):
    return hashlib.sha1(f"{source_id}:{asset_id}".encode()).hexdigest()[:20]


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------

def _largest_inscribed_rect(mask):
    """Largest all-True axis-aligned rectangle, histogram method."""
    h, w = mask.shape
    import numpy as np
    heights = np.zeros(w, dtype=int)
    best = (0, 0, 0, 0, 0)
    for r in range(h):
        heights = np.where(mask[r], heights + 1, 0)
        stack = []
        for c in range(w + 1):
            cur = int(heights[c]) if c < w else 0
            start = c
            while stack and stack[-1][1] >= cur:
                s, hh = stack.pop()
                area = hh * (c - s)
                if area > best[0]:
                    best = (area, s, r - hh + 1, c - s, hh)
                start = s
            stack.append((start, cur))
    return best


def analyse_svg(svg_text, side=180):
    """Return the geometry a container needs, or None if it cannot be read."""
    try:
        import io
        import numpy as np
        import cairosvg
        from PIL import Image
    except ImportError:
        return None
    try:
        png = cairosvg.svg2png(bytestring=svg_text.encode("utf-8"),
                               output_width=side, output_height=side,
                               background_color="white")
        arr = np.array(Image.open(io.BytesIO(png)).convert("L"))
    except Exception:
        return None
    mask = arr < 245
    try:
        from scipy.ndimage import binary_fill_holes
        mask = binary_fill_holes(mask)
    except Exception:
        pass
    import numpy as np
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return None
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    bbox_area = (x1 - x0 + 1) * (y1 - y0 + 1)
    area, rx, ry, rw, rh = _largest_inscribed_rect(mask)
    frac = area / bbox_area if bbox_area else 0.0
    return {
        "side": side,
        "bbox": [x0 / side, y0 / side, (x1 - x0 + 1) / side, (y1 - y0 + 1) / side],
        # inscribed region in fractions of the full canvas, so it scales
        "inscribed": [rx / side, ry / side, rw / side, rh / side],
        "inscribed_fraction": round(frac, 4),
        "aspect": round(rw / max(rh, 1), 3),
        "mode": "frame" if frac >= FRAME_THRESHOLD else "anchor",
        "ink_fraction": round(float(mask.sum()) / (side * side), 4),
    }


def geometry_for(asset, svg_text):
    """Cached geometry for a resolved asset. One rasterisation, then never again."""
    key = asset_key(asset.get("source_id", "?"), asset.get("asset_id", "?"))
    path = os.path.join(_ensure(GEOM_DIR), key + ".json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass
    g = analyse_svg(svg_text)
    if g is None:
        return None
    g["source"] = {k: asset.get(k) for k in ("source_id", "asset_id", "license", "author", "url")}
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(g, fh, indent=1)
    except OSError:
        pass
    return g


# --------------------------------------------------------------------------
# Derivative store
# --------------------------------------------------------------------------

def _obligations(sources):
    """Attribution obligations carried by a set of source assets."""
    out = []
    for s in sources:
        lic = (s.get("license") or "").upper()
        if lic.startswith("CC-BY") or lic.startswith("CC BY"):
            out.append({
                "source_id": s.get("source_id"), "asset_id": s.get("asset_id"),
                "author": s.get("author"), "license": s.get("license"),
                "url": s.get("url"),
                "attribution": s.get("attribution"),
            })
    return out


def store_derivative(svg_text, sources, operations, name=None):
    """Keep a composed or transformed asset, with its whole provenance chain.

    `sources` is every asset that went into it, each with its licence. The
    obligations are the union, so reusing this derivative in a third figure
    still credits the originals. That is the part a human forgets and a store
    does not.
    """
    _ensure(DERIVED_DIR)
    digest = hashlib.sha1(svg_text.encode("utf-8")).hexdigest()[:20]
    svg_path = os.path.join(DERIVED_DIR, digest + ".svg")
    meta_path = os.path.join(DERIVED_DIR, digest + ".json")
    meta = {
        "id": digest,
        "name": name or "derivative",
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "operations": list(operations),
        "sources": [{k: s.get(k) for k in
                     ("source_id", "asset_id", "license", "author", "url", "attribution")}
                    for s in sources],
        "attribution_required": _obligations(sources),
    }
    try:
        with open(svg_path, "w", encoding="utf-8") as fh:
            fh.write(svg_text)
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=1)
    except OSError:
        return None
    return meta


def list_derivatives():
    if not os.path.isdir(DERIVED_DIR):
        return []
    out = []
    for f in sorted(os.listdir(DERIVED_DIR)):
        if f.endswith(".json"):
            try:
                with open(os.path.join(DERIVED_DIR, f), "r", encoding="utf-8") as fh:
                    out.append(json.load(fh))
            except Exception:
                pass
    return out


# --------------------------------------------------------------------------
# Anchor rendering
# --------------------------------------------------------------------------

def anchor_svg(svg_text, opacity=0.14):
    """An anatomical silhouette as background: desaturated and faint.

    It is background, never a participant: no relation may reach it, and it
    carries no label of its own beyond the container's.
    """
    body = re.sub(r"(?is)<script.*?</script>", "", svg_text)
    return body, opacity


def content_region(geometry, x, y, w, h, pad=0.06):
    """Where the contents go inside a container carrying this anchor.

    In frame mode that is the measured inscribed rectangle, so the contents
    sit inside the outline. In anchor mode the whole box is available, but the
    inscribed region still nudges the contents towards the full part of the
    silhouette rather than over a lobe or a gap.
    """
    if not geometry:
        return x + w * pad, y + h * pad, w * (1 - 2 * pad), h * (1 - 2 * pad)
    ix, iy, iw, ih = geometry["inscribed"]
    if geometry["mode"] == "frame":
        return (x + ix * w, y + iy * h, iw * w, ih * h)
    cx = x + (ix + iw / 2.0) * w
    cy = y + (iy + ih / 2.0) * h
    rw, rh = w * (1 - 2 * pad), h * (1 - 2 * pad)
    return (min(max(cx - rw / 2.0, x), x + w - rw),
            min(max(cy - rh / 2.0, y), y + h - rh), rw, rh)
