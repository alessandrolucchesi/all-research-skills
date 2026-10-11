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
# A class generic can never score as the entity itself: capped below the
# auto-accept line so it always travels the substitution path, where the
# adaptation is recorded and the credit line says what was swapped in.
GENERIC_CAP = 80

# Words a library adds to a head noun that do not change what the drawing
# denotes. Everything else does: "calciumsensing-receptor" is a different
# protein and "7helix-receptor" is a different structural class, and either
# one standing in for an unqualified receptor is a claim about the protein
# rather than a simplification of it. Head-noun generalisation is allowed
# only across this list.
NEUTRAL_QUALIFIERS = {
    "simple", "generic", "basic", "plain", "standard", "general",
    "membrane", "transmembrane", "surface", "bound",
    "schematic", "outline", "empty", "filled", "icon", "symbol", "shape",
    # A library's colour variants of one drawing are the same drawing.
    "blue", "green", "orange", "pink", "red", "yellow", "purple", "violet",
    "grey", "gray", "black", "white", "brown", "teal",
}

# Catalogue categories that can never depict a biological or clinical entity.
# "B cell" resolved to typography/B.svg, a drawing of the letter B, because
# the subset rule saw {"b"} inside {"b","cell"}. A letter is not a
# generalisation of a lymphocyte; it is a different kind of thing.
EXCLUDED_CATEGORIES = {"typography", "alphabet", "numbers", "symbols",
                       "machine_learning", "chemo-_and_bioinformatics",
                       "safety_symbols", "scientific_graphs"}

# A candidate name this short carries no depictive content of its own.
MIN_NAME_CHARS = 3


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


def _neutral_extras(cand_words, term_words):
    """True when everything the candidate adds to the query is a word that
    does not change what is denoted."""
    extras = [w for w in cand_words if w not in term_words]
    return all(w in NEUTRAL_QUALIFIERS for w in extras)


def shared_denotation(asset_name, label_a, label_b):
    """True when the asset's name is the noun the two labels have in common.

    A glyph says two entities are the same thing only when it names one of
    them. `Mouse` against "Mouse" and "OT-II mouse" names the word both
    already carry, and drawing both strains as mice is what a protocol
    figure does; `macrophage` against "Macrophage" and "Dendritic cell"
    names the first and would be a false statement about the second.
    """
    aw = _stem(_norm(asset_name)).split()
    if not aw:
        return False
    la = set(_stem(_norm(label_a)).split())
    lb = set(_stem(_norm(label_b)).split())
    if not la or not lb:
        return False
    return all((w in la and w in lb) or w in NEUTRAL_QUALIFIERS for w in aw)


def is_generic_name_for(asset_name, label):
    """True when the asset's name says nothing about this entity that the
    entity's own label does not already say.

    `receptor-membrane-2` against "GLP-1 receptor" is a plain receptor: the
    head noun is the entity's own, and what is added is a neutral word. Two
    such entities may share it, because the glyph names neither of them.
    `macrophage` against "Macrophage" is the entity itself and may not be
    shared, because a second entity drawn with it would be claimed to be a
    macrophage too.
    """
    lw = set(_stem(_norm(label)).split())
    aw = _stem(_norm(asset_name)).split()
    if not aw or not lw:
        return False
    if set(aw) <= lw:
        return False      # the asset IS the entity, under its own name
    return all(w in lw or w in NEUTRAL_QUALIFIERS for w in aw)


def _stem(n):
    """Fold the two differences that are spelling, not meaning.

    Libraries name a file for the drawing, not for the query: Health Icons
    has `kidneys` and Servier has `kidney-1`, `kidney-2`, so an exact test
    on "kidney" found neither and the container fell back to a cell
    membrane, drawing an organ as a cell. A trailing variant number and a
    plural are dropped; a short word keeps its s, so `ras` is not stemmed
    to `ra`.
    """
    out = []
    for w in n.split():
        if w.isdigit():
            continue
        if len(w) >= 5 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return " ".join(out)


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
    term_s = _stem(term)
    tw = term_s.split()
    best = 0
    for cand0, weight in ((name, 0), (title, -4)):
        if not cand0:
            continue
        cand = _stem(cand0)
        cw = cand.split()
        if cand == term_s:
            best = max(best, 100 + weight)
        elif all(w in cw for w in tw):
            best = max(best, 82 + weight)
        elif len(term_s) >= 4 and term_s in cand:
            best = max(best, 58 + weight)
        elif (tw and cw and tw[-1] in cw and len(tw) > 1
              and _neutral_extras(cw, tw)):
            # Head-noun generalisation. "Fc receptor" IS a kind of receptor,
            # so an asset whose name contains the query's head noun denotes
            # something more general, which the label then specialises. This
            # is the same generalise-up rule, extended to English compounds:
            # it reaches "receptor-3helix-membrane" for "Fc receptor" and
            # still refuses a basophil for a neutrophil, whose head noun is
            # the whole word and appears nowhere in the basophil's name.
            # Penalised by how much the candidate adds. A library names an
            # asset for the structure it drew, so "7helix-receptor-membrane"
            # is a GPCR and standing it in for a single-pass receptor is a
            # claim about the protein, not a simplification. The plainest
            # candidate carrying the head noun wins.
            best = max(best, 86 + weight - 2 * max(0, len(cw) - len(tw)))
        elif cw and set(cw).issubset(set(tw)) and tw and tw[-1] in cw:
            # The candidate drops a qualifier from the query: "megakaryocyte"
            # against "clonal megakaryocyte". This is the most useful match
            # there is and it must outrank a class-level generic, which is
            # what sent two different entities to one blood-cells glyph.
            # The head noun has to survive: dropping it is not dropping a
            # qualifier but naming something else, and "B cell receptor"
            # minus "receptor" is a B cell, which is what one figure drew
            # in place of the receptor on its surface.
            best = max(best, 92 + weight)
        elif len(cand) >= 4 and cand in term_s:
            # Containment scored by how much of the query the candidate
            # covers. "antibody" covers two thirds of "autoantibody" and is
            # a real generalisation; "body" covers a third and is an
            # orthographic coincidence that once resolved an autoantibody to
            # a drawing of a human body.
            ratio = len(cand) / max(len(term_s), 1)
            best = max(best, 38 + int(34 * ratio) + weight)
    for t in tags:
        if _stem(t) == term_s:
            best = max(best, 76)
        elif len(term_s) >= 4 and term_s in _stem(t):
            best = max(best, 50)
    if cat and (term_s == _stem(cat) or (len(term_s) >= 4 and term_s in _stem(cat))):
        best = max(best, 20)
    return best


def resolve(label, target="oa_cc_by", synonyms=None, cls=None, catalogues=None,
            limit=1, collect_rejected=False, auto_accept=AUTO_ACCEPT,
            prefer_source=None, prefer_categories=(), prefer_author=None):
    gate = load_gate(target)
    cats = catalogues if catalogues is not None else (healthicons_catalogue() + bioicons_catalogue())
    own = search_terms(label, synonyms, None)
    # The class's generic forms are searched too, so an entity with no exact
    # icon still reaches a legitimate, more general one instead of falling
    # back to a bare box. They are kept apart from the entity's own terms and
    # capped: a drawing called "cell" is an exact match for the word "cell"
    # and nothing at all like an exact match for an osteoblast, and scoring
    # it as one let a generic enter as though it were the entity itself,
    # silently and with no substitution recorded.
    gen = []
    for g in ([cls] if cls else []) + list(generic_terms(cls or "")):
        n = _norm(g)
        if n and n not in own and n not in gen:
            gen.append(n)
    terms = own + gen

    ranked = []
    for hit in cats:
        if _norm(hit.get("category", "")).replace(" ", "_") in EXCLUDED_CATEGORIES:
            continue
        if len(_norm(hit["name"]).replace(" ", "")) < MIN_NAME_CHARS:
            continue
        own_best = max((score(hit, t) for t in own), default=0)
        best = own_best
        if gen:
            best = max(best, min(max((score(hit, t) for t in gen), default=0),
                                 GENERIC_CAP))
        if best:
            # Health Icons first on equal merit: CC0 means no composite-level
            # attribution bookkeeping. Servier, mirrored in Bioicons, is
            # genuine vector and carries the widest clinical coverage, so it
            # ranks immediately after.
            # Source rank only breaks ties. Attribution is a line of text; a
            # glyph that says the wrong thing is a wrong claim.
            bonus = 2 if hit["source_id"] == "health-icons" else (2 if hit.get("author") == "Servier" else 0)
            if prefer_source and hit["source_id"] == prefer_source:
                bonus += 1
            # One collection per figure wherever the collection has the
            # subject. Libraries differ in style, not only in coverage, and
            # a figure assembled from four of them reads as a patchwork
            # whatever the drawing quality of each piece. Style never
            # overrides sense: this is worth two points and a tiebreak, so
            # a better match from another collection still wins.
            # prefer_author may carry style hints after the collection name,
            # "Servier 3d" against "Servier": a library often ships the same
            # subject in two finishes, and a figure should pick one.
            same_author = False
            if prefer_author:
                want = _norm(prefer_author).split()
                au = _norm(hit.get("author", "")).split()
                same_author = bool(au) and all(w in want for w in au)
                if same_author:
                    bonus += 2
                    hints = [w for w in want if w not in au]
                    if hints:
                        nm = _stem(_norm(hit["name"])).split()
                        bonus += 4 * sum(1 for w in hints if w in nm)
                        # A variant of the same subject is the same subject:
                        # `nucleus-full-3d` denotes what `nucleus` denotes,
                        # so it scores as an exact match and the hint
                        # decides between them. Without this the plain name
                        # always won and the variant could never be chosen.
                        for t in own:
                            tw = _stem(t).split()
                            if (tw and all(w in nm for w in tw)
                                    and all(w in tw or w in hints
                                            or w in NEUTRAL_QUALIFIERS for w in nm)):
                                best = max(best, 100)
                                break
            # A container wants a drawn empty cell rather than a solid one,
            # and the library keeps those in their own category. It breaks a
            # tie and nothing more: as a score it was outweighing an exact
            # match on the asked-for name, which is the one thing no
            # preference should be able to do.
            pref = 1 if (prefer_categories
                         and hit.get("category") in prefer_categories) else 0
            ranked.append((best + bonus, pref + (1 if same_author else 0),
                           own_best, hit))
    ranked.sort(key=lambda r: (-r[0], -r[1]))


    accepted, candidates, rejected = [], [], []
    for sc, _pref, own_sc, hit in ranked[:60]:
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
        cand_norm = _stem(_norm(hit["name"]))
        cand_words = cand_norm.split()

        def _more_general(t):
            t = _stem(t)
            tw = t.split()
            if is_generalisation(cand_words, tw) and tw and tw[-1] in cand_words:
                return True
            # head noun: "Fc receptor" is a kind of receptor, but only
            # where what the candidate adds does not name something else.
            if (len(tw) > 1 and tw[-1] in cand_words
                    and _neutral_extras(cand_words, tw)):
                return True
            # contained word: "antibody" is more general than "autoantibody",
            # but only when it covers enough of it to be the same noun.
            return (len(cand_norm) >= 4 and cand_norm in t
                    and len(cand_norm) / max(len(t), 1) >= 0.5)

        # Judged against what the entity actually is. Run over the class
        # generics as well, every candidate matching "cell" counted as a
        # generalisation of every cell, which is how a drawing of blood
        # cells came to stand for an osteoblast.
        generalises = (any(_more_general(t) for t in own)
                       or _stem(_norm(hit["name"])) in
                       [_stem(_norm(g)) for g in generic_assets(cls or "")])
        adapt = []
        if sc < auto_accept and generalises:
            adapt.append("generic substitute for the labelled entity")
        record = {
            "source_id": hit["source_id"], "asset_id": hit["path"],
            "name": hit["name"],
            "author": hit["author"], "license": hit["license"],
            "url": raw_url(hit), "adaptations": adapt,
            "attribution": attribution(hit, adapt),
            "vector": True, "score": sc, "own_score": own_sc, "svg": svg,
            "generic_name": is_generic_name_for(hit["name"], label),
        }
        # A class generic must not be taken while something that matched the
        # entity's own name is on the table. Ranking puts the better match
        # first, so by now it is already in `candidates`: a drawing of cell
        # nuclei was being accepted for a neutrophil while the library's own
        # neutrophil sat in the candidate list, unreported. Judged against
        # what passed the gates, not against the raw ranking, where the
        # better match may have been refused for its licence.
        if adapt and any(c.get("own_score", 0) > own_sc for c in candidates):
            adapt = []
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
