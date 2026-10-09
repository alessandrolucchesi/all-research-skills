#!/usr/bin/env python3
"""
asset_resolver: find an open-licensed vector pictogram for an entity.

Three gates, in this order, and an asset must clear all three:

1. **Licence gate.** The licence must be allowed for the declared publication
   target (`assets/sources.json`). Share-alike, non-commercial and
   no-derivative assets are refused for publication targets.
2. **Vector gate.** The file must be genuine vector. A licence-clean SVG that
   wraps an embedded raster is unusable: it produces a raster island inside a
   vector drawing and fails at print resolution. This gate is not optional and
   the registry cannot supply it, because it is a property of the file rather
   than of the source.
3. **Match.** Lexical match of the entity label, its synonyms and its class
   against the catalogue name and category.

When nothing clears all three the resolver returns None. The caller must then
warn and draw a plain outline, naming the terms it tried. It must never fall
back to the dashed outline, which in the lexicon means "unspecified entity",
that is, an identity the author could not state.

Sources wired here: Bioicons (2804 entries, licence carried in the directory
path) and Health Icons (uniformly CC0). The remaining registry sources have no
machine index and are resolved by hand through the `asset:` field.

Usage:
    python asset_resolver.py --search megakaryocyte
    python asset_resolver.py --search "bone marrow" --target oa_cc_by --show-rejected
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request

try:
    from .ontology import generic_assets, generic_terms, is_generalisation
except Exception:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ontology import generic_assets, generic_terms, is_generalisation

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCES = os.path.join(HERE, os.pardir, "assets", "sources.json")
CACHE = os.environ.get("SCIFIG_CACHE", os.path.join(HERE, os.pardir, "assets", "cache"))

BIOICONS_INDEX = "https://raw.githubusercontent.com/duerrsimon/bioicons/main/static/icons/icons.json"
BIOICONS_RAW = "https://raw.githubusercontent.com/duerrsimon/bioicons/main/static/icons"
BIOICONS_WEB = "https://bioicons.com/"
HEALTHICONS_INDEX = "https://raw.githubusercontent.com/resolvetosavelives/healthicons/main/public/icons/meta-data.json"
HEALTHICONS_RAW = "https://raw.githubusercontent.com/resolvetosavelives/healthicons/main"

# Bioicons licence directory names mapped to the registry's licence ids.
BIOICONS_LICENCE = {
    "cc-0": "CC0", "cc-by-3.0": "CC-BY-3.0", "cc-by-4.0": "CC-BY-4.0",
    "cc-by-sa-3.0": "CC-BY-SA", "cc-by-sa-4.0": "CC-BY-SA",
    "mit": "MIT", "bsd": "BSD",
}

# Terms that will not match on surface form. Kept small and explicit: a
# synonym map is a curation decision, not a guess the resolver should make.
SYNONYMS = {
    # Synonyms widen the search, never the meaning. Naming a coordinate term
    # here would reintroduce sideways substitution through the back door:
    # "mpn clone" once mapped to "megakaryocyte" and duly resolved to one.
    "endothelium": ["blood vessel", "endothelial"],
    "endothelial cell": ["blood vessel", "endothelial"],
    "platelet": ["thrombocyte", "platelet"],
    "lung": ["lung", "healthy-lung"],
    "pulmonary vasculature": ["blood vessel", "lung"],
}

# Only an exact match on a catalogue name or tag is accepted without a human
# in the loop. Anything weaker is offered as a candidate and must be confirmed
# with an explicit `asset:`.
#
# The rule exists because of a real near miss during testing: "neutrophil",
# widened by a synonym to "granulocyte", scored 86 against a Servier *basophil*
# icon. For a cell type a near match is not an approximation, it is a
# misstatement, and it would have shipped looking exactly like a correct one.
# Synonyms above are therefore identity preserving only: they widen the search,
# never the meaning.
AUTO_ACCEPT = 96


def _cache_path(name):
    os.makedirs(CACHE, exist_ok=True)
    return os.path.join(CACHE, name)


def _fetch(url, cache_name=None, binary=False):
    if cache_name:
        path = _cache_path(cache_name)
        if os.path.exists(path):
            mode = "rb" if binary else "r"
            with open(path, mode, **({} if binary else {"encoding": "utf-8"})) as fh:
                return fh.read()
    req = urllib.request.Request(url, headers={"User-Agent": "scientific-figures/0.2"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    data = raw if binary else raw.decode("utf-8", "replace")
    if cache_name:
        path = _cache_path(cache_name)
        mode = "wb" if binary else "w"
        with open(path, mode, **({} if binary else {"encoding": "utf-8"})) as fh:
            fh.write(data)
    return data


def load_gate(target, sources_path=SOURCES):
    with open(sources_path, "r", encoding="utf-8") as fh:
        reg = json.load(fh)
    gate = reg["license_gate"]["targets"].get(target)
    if gate is None:
        raise SystemExit(f"unknown target '{target}'")
    return gate


def licence_allowed(licence, gate):
    if licence in gate.get("deny", []):
        return False, "denied for this target"
    if licence in gate.get("review", []):
        return False, "needs a recorded gate override"
    if licence not in gate.get("allow", []):
        return False, "not recognised by the gate"
    return True, "allowed"


def is_vector(svg_text):
    """Reject anything that is a raster in an SVG wrapper.

    Verified case: bone_marrow.svg (El-Jayawant, CC-BY-4.0) is 310 KB, carries
    zero <path> elements and embeds a raster through <image>.
    """
    if "<image" in svg_text or "data:image" in svg_text:
        return False, "embeds a raster"
    if svg_text.count("<path") == 0 and svg_text.count("<polygon") == 0:
        return False, "no vector geometry"
    return True, "vector"


# --------------------------------------------------------------------------
# Catalogues
# --------------------------------------------------------------------------

def bioicons_catalogue():
    data = json.loads(_fetch(BIOICONS_INDEX, "bioicons-index.json"))
    out = []
    for e in data:
        lic_dir = e.get("license", "")
        out.append({
            "source_id": "bioicons",
            "name": e.get("name", ""),
            "category": e.get("category", ""),
            "author": e.get("author", ""),
            "license_dir": lic_dir,
            "license": BIOICONS_LICENCE.get(lic_dir, lic_dir),
            "path": f"{lic_dir}/{e.get('category')}/{e.get('author')}/{e.get('name')}.svg",
        })
    return out


def healthicons_catalogue():
    """749 entries from the repository's own metadata file.

    The GitHub tree API answers 403 from a sandboxed session; the raw
    metadata file does not, and it carries curated tags, which match better
    than a filename ever will.
    """
    try:
        data = json.loads(_fetch(HEALTHICONS_INDEX, "healthicons-index.json"))
    except Exception:
        return []
    out = []
    for e in data:
        rel = e.get("path") or f"{e.get('category')}/{e.get('id')}"
        out.append({
            "source_id": "health-icons",
            "name": e.get("id", ""),
            "title": e.get("title", ""),
            "tags": e.get("tags", []) or [],
            "category": e.get("category", ""),
            "author": "Health Icons",
            "license": "CC0",
            "path": f"public/icons/svg/filled/{rel}.svg",
        })
    return out


def raw_url(hit):
    # Catalogue entries include non-ASCII filenames, which must be percent
    # encoded or the request never leaves the client.
    quoted = urllib.parse.quote(hit["path"])
    if hit["source_id"] == "bioicons":
        return f"{BIOICONS_RAW}/{quoted}"
    return f"{HEALTHICONS_RAW}/{quoted}"


def attribution(hit, adaptations=()):
    """CC BY requires that changes be indicated, so the adaptations are part
    of the credit line rather than a footnote the author has to remember."""
    if hit["source_id"] != "bioicons":
        return None  # CC0, no attribution obligation
    verb = "Adapted from icon" if adaptations else "Icon"
    changes = f" Changes: {', '.join(adaptations)}." if adaptations else ""
    return (f"{verb} \"{hit['name']}\" by {hit['author']}, Bioicons "
            f"({BIOICONS_WEB}), licensed under {hit['license']}.{changes}")


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------

def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def search_terms(label, synonyms=None, cls=None):
    terms = [label] + list(synonyms or [])
    key = _norm(label)
    terms += SYNONYMS.get(key, [])
    if cls:
        terms.append(cls)
    seen, out = set(), []
    for t in terms:
        n = _norm(t)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def score(hit, term):
    """Word-aware match. Substring matching on short names is worthless:
    an icon called "R" matched "megakaryocyte" on the letter r."""
    name = _norm(hit["name"])
    title = _norm(hit.get("title", ""))
    cat = _norm(hit["category"])
    tags = [_norm(t) for t in hit.get("tags", [])]
    tw = term.split()
    best = 0
    for cand, weight in ((name, 0), (title, -4)):
        if not cand:
            continue
        cw = cand.split()
        if cand == term:
            best = max(best, 100 + weight)
        elif all(w in cw for w in tw):
            best = max(best, 82 + weight)
        elif len(term) >= 4 and term in cand:
            best = max(best, 58 + weight)
        elif len(cand) >= 4 and cand in term:
            best = max(best, 44 + weight)
    for t in tags:
        if t == term:
            best = max(best, 76)
        elif len(term) >= 4 and term in t:
            best = max(best, 50)
    if cat and (term == cat or (len(term) >= 4 and term in cat)):
        best = max(best, 20)
    return best


def resolve(label, target="oa_cc_by", synonyms=None, cls=None, catalogues=None,
            limit=1, collect_rejected=False, auto_accept=AUTO_ACCEPT,
            prefer_source=None):
    gate = load_gate(target)
    cats = catalogues if catalogues is not None else (healthicons_catalogue() + bioicons_catalogue())
    terms = search_terms(label, synonyms, cls)
    # The class's generic forms are searched too, so an entity with no exact
    # icon still reaches a legitimate, more general one instead of falling
    # back to a bare box.
    for g in generic_terms(cls or ""):
        if _norm(g) not in terms:
            terms.append(_norm(g))

    ranked = []
    for hit in cats:
        best = max((score(hit, t) for t in terms), default=0)
        if best:
            # Health Icons first on equal merit: CC0 means no composite-level
            # attribution bookkeeping. Servier, mirrored in Bioicons, is
            # genuine vector and carries the widest clinical coverage, so it
            # ranks immediately after.
            bonus = 6 if hit["source_id"] == "health-icons" else (4 if hit.get("author") == "Servier" else 0)
            if prefer_source and hit["source_id"] == prefer_source:
                bonus += 5
            ranked.append((best + bonus, hit))
    ranked.sort(key=lambda r: -r[0])

    accepted, candidates, rejected = [], [], []
    for sc, hit in ranked[:60]:
        ok, why = licence_allowed(hit["license"], gate)
        if not ok:
            rejected.append((hit, f"licence {hit['license']}: {why}"))
            continue
        try:
            key = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{hit['source_id']}-{hit['path']}")
            svg = _fetch(raw_url(hit), f"svg-{key[-120:]}")
        except Exception as exc:
            rejected.append((hit, f"fetch failed: {exc}"))
            continue
        vec, why = is_vector(svg)
        if not vec:
            rejected.append((hit, f"vector gate: {why}"))
            continue
        # Generalise up, never sideways. A candidate whose words are a subset
        # of the query drops qualifiers and may stand in, with the label
        # carrying the identity. A candidate that adds a word is more specific
        # or a sibling and is never taken automatically.
        cand_words = _norm(hit["name"]).split()
        generalises = (any(is_generalisation(cand_words, t.split()) for t in terms)
                       or hit["name"].lower() in generic_assets(cls or ""))
        adapt = []
        if sc < auto_accept and generalises:
            adapt.append("generic substitute for the labelled entity")
        record = {
            "source_id": hit["source_id"], "asset_id": hit["path"],
            "author": hit["author"], "license": hit["license"],
            "url": raw_url(hit), "adaptations": adapt,
            "attribution": attribution(hit, adapt),
            "vector": True, "score": sc, "svg": svg,
        }
        if sc >= auto_accept or adapt:
            accepted.append(record)
        else:
            candidates.append(record)
        if len(accepted) >= limit:
            break
    if collect_rejected:
        return accepted, candidates, rejected, terms
    return accepted, candidates, terms


def main():
    ap = argparse.ArgumentParser(description="Resolve an open-licensed vector pictogram.")
    ap.add_argument("--search", required=True)
    ap.add_argument("--target", default="oa_cc_by")
    ap.add_argument("--class", dest="cls", default=None)
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--show-rejected", action="store_true")
    args = ap.parse_args()

    accepted, candidates, rejected, terms = resolve(
        args.search, args.target, cls=args.cls, limit=args.limit, collect_rejected=True)
    print(f"terms tried: {', '.join(terms)}")
    if not accepted:
        print("nothing matched exactly: no asset auto-accepted")
    for a in accepted:
        print(f"  ACCEPTED [{a['score']:3d}] {a['source_id']:13s} {a['license']:12s} {a['asset_id']}")
        if a["attribution"]:
            print(f"           {a['attribution']}")
    for a in accepted:
        if a["adaptations"]:
            print(f"           adaptations: {'; '.join(a['adaptations'])}")
    for c in candidates[:5]:
        print(f"  candidate [{c['score']:3d}] {c['source_id']:13s} {c['license']:12s} {c['asset_id']}"
              f"   <- confirm with asset: before use")
    if args.show_rejected:
        for hit, why in rejected[:12]:
            print(f"  REJECTED {hit['source_id']:13s} {hit['path']}: {why}")


if __name__ == "__main__":
    main()
