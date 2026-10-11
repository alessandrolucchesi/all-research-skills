#!/usr/bin/env python3
"""Compare manuscript references against retrieved PubMed metadata.

Usage:
    python compare_refs.py refs.json pubmed.json -o report.md
    python compare_refs.py refs.json pubmed.json --authors "Lucchesi,Napolitano"

refs.json    output of extract_refs.py
pubmed.json  the get_article_metadata response, saved verbatim; may be a list
             of responses. Each article is tied to a reference by its PMID
             through pmid_map.json, by a "ref" field added to the record, or
             by its DOI where the manuscript carries one.
"""
import argparse
import json
import re
import sys
import unicodedata


def norm(s):
    if s is None:
        return ''
    s = unicodedata.normalize('NFKD', str(s))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', '', s.lower())


def surname(a):
    """The author's family name, whatever shape the record uses.

    The connector returns last_name and initials, but a record saved from a
    different route can carry a single `name`. Read only one of them and an
    author present in the record is reported as appearing nowhere in it,
    which is the most alarming verdict this tool can produce and the one it
    must never produce by accident.
    """
    if not isinstance(a, dict):
        return str(a or '').split()[0] if a else ''
    ln = a.get('last_name') or a.get('family') or ''
    if ln:
        return ln
    whole = a.get('name') or a.get('full_name') or ''
    return whole.split(',')[0].split()[0] if whole else ''


def initials(a):
    if not isinstance(a, dict):
        return ''
    if a.get('initials'):
        return a['initials']
    whole = a.get('name') or a.get('full_name') or ''
    parts = whole.replace(',', ' ').split()
    return parts[-1] if len(parts) > 1 and len(parts[-1]) <= 3 else ''


def first_page(pages):
    if not pages:
        return ''
    return re.split(r'[-–]', str(pages))[0].strip()


def load_articles(path):
    data = json.load(open(path, encoding='utf-8'))
    blocks = data if isinstance(data, list) else [data]
    out = []
    for b in blocks:
        out.extend(b.get('articles', []) if isinstance(b, dict) else [b])
    return out


def index_articles(articles):
    """Index the retrieved records every way a reference can point at one.

    By PMID, by a `ref` number added to the record by hand, and by DOI. The
    first alone meant the operator had to hand-build pmid_map.json before
    anything matched, while the documented `ref` field was never read: a
    saved get_article_metadata response compared against its own manuscript
    reported every entry as NOT MATCHED, which is the one verdict that must
    never be produced by the tool's own plumbing.
    """
    idx, by_ref, by_doi = {}, {}, {}
    for a in articles:
        ids = a.get('identifiers') or {}
        pmid = ids.get('pmid')
        if pmid:
            idx[str(pmid)] = a
        if a.get('ref') is not None:
            by_ref[str(a['ref'])] = a
        doi = (ids.get('doi') or '').lower().rstrip('.')
        if doi:
            by_doi[doi] = a
    return idx, by_ref, by_doi


def check(ref, art, own_authors):
    issues = []
    ids = art.get('identifiers') or {}
    cit = art.get('citation') or {}
    authors = art.get('authors') or []

    got_doi = (ids.get('doi') or '').lower().rstrip('.')
    our_doi = (ref.get('doi') or '').lower().rstrip('.')
    if our_doi and got_doi and our_doi != got_doi:
        issues.append(('DOI', ref['doi'], ids.get('doi')))

    got_year = str((art.get('publication_date') or {}).get('year') or '')
    if ref.get('year') and got_year and str(ref['year']) != got_year:
        issues.append(('year', ref['year'], got_year))

    if ref.get('volume') and cit.get('volume') and \
            str(ref['volume']) != str(cit['volume']):
        issues.append(('volume', ref['volume'], cit['volume']))

    if ref.get('issue') and cit.get('issue') and \
            str(ref['issue']) != str(cit['issue']):
        issues.append(('issue', ref['issue'], cit['issue']))

    gp = first_page(cit.get('pages'))
    if ref.get('first_page') and gp and norm(ref['first_page']) != norm(gp):
        issues.append(('first page', ref['first_page'], cit.get('pages')))

    if authors:
        got_first = surname(authors[0])
        if ref.get('author') and norm(ref['author']) != norm(got_first):
            surnames = [norm(surname(a)) for a in authors]
            where = surnames.index(norm(ref['author'])) + 1 \
                if norm(ref['author']) in surnames else None
            detail = f"{got_first} (ours appears at position {where})" \
                if where else f"{got_first} (ours appears nowhere in the list)"
            issues.append(('first author', ref['author'], detail))

    jt = (art.get('journal') or {}).get('iso_abbreviation') or ''
    if ref.get('journal') and jt and norm(ref['journal']) != norm(jt):
        issues.append(('journal', ref['journal'], jt))

    flags = []
    if own_authors:
        surnames = {norm(surname(a)) for a in authors}
        hits = [o for o in own_authors if norm(o) in surnames]
        if hits:
            flags.append('SELF-CITATION: ' + ', '.join(hits) +
                         ' is an author on this paper; the citation must be exact')
    return issues, flags


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('refs')
    ap.add_argument('pubmed')
    ap.add_argument('-o', '--out', default='report.md')
    ap.add_argument('--map', default='pmid_map.json',
                    help='optional {"R12": "32406549"} mapping')
    ap.add_argument('--authors', default='',
                    help='comma-separated surnames of the manuscript authors')
    args = ap.parse_args()

    refs = json.load(open(args.refs, encoding='utf-8'))
    articles, by_ref, by_doi = index_articles(load_articles(args.pubmed))
    own = [a.strip() for a in args.authors.split(',') if a.strip()]

    try:
        mapping = json.load(open(args.map, encoding='utf-8'))
    except FileNotFoundError:
        mapping = {}

    lines = ['# Bibliography verification report', '']
    clean = defective = unchecked = 0
    manual = []

    for ref in refs:
        n = ref['ref']
        if ref['route'] != 'pubmed':
            manual.append((n, ref['route'], ref['raw'][:90]))
            continue

        pmid = mapping.get(f"R{n}") or mapping.get(str(n)) or ref.get('pmid')
        art = articles.get(str(pmid)) if pmid else None
        if art is None:
            art = by_ref.get(str(n))
        if art is None and ref.get('doi'):
            art = by_doi.get(ref['doi'].lower().rstrip('.'))
        if not art:
            unchecked += 1
            lines += [f"## [{n}] NOT MATCHED", '',
                      'No PubMed record for the coordinates as written. '
                      'Rebuild from the source or remove.', '',
                      f"    {ref['raw'][:200]}", '']
            continue

        issues, flags = check(ref, art, own)
        if not issues and not flags:
            clean += 1
            continue

        defective += 1
        ids = art.get('identifiers') or {}
        cit = art.get('citation') or {}
        lines.append(f"## [{n}] {'CHECK' if not issues else 'DEFECTIVE'}")
        lines.append('')
        for f in flags:
            lines.append(f"> {f}")
            lines.append('')
        if issues:
            lines.append('| field | manuscript | PubMed |')
            lines.append('|---|---|---|')
            for field, ours, theirs in issues:
                lines.append(f"| {field} | {ours} | {theirs} |")
            lines.append('')
        au = art.get('authors') or []
        alist = ', '.join(f"{surname(a)} {initials(a)}".strip() for a in au[:3])
        if len(au) > 3:
            alist += ', et al'
        jt = (art.get('journal') or {}).get('iso_abbreviation') or ''
        vol = cit.get('volume', '')
        iss = f"({cit['issue']})" if cit.get('issue') else ''
        pg = cit.get('pages', '')
        yr = (art.get('publication_date') or {}).get('year', '')
        title = (art.get('title') or '').rstrip('.')
        lines += ['Corrected:', '',
                  f"    {alist}. {title}. {jt} {yr};{vol}{iss}:{pg}. "
                  f"doi:{ids.get('doi','')}", '']

    head = [f"- verified clean: {clean}",
            f"- defective: {defective}",
            f"- not matched: {unchecked}",
            f"- outside PubMed, verify at source: {len(manual)}", '']
    lines[2:2] = head

    if manual:
        lines += ['## Outside PubMed', '',
                  'These cannot be validated here and are the highest-risk '
                  'category. Verify each at its own source.', '']
        for n, kind, raw in manual:
            lines.append(f"- **[{n}]** ({kind}) {raw}")
        lines.append('')

    open(args.out, 'w', encoding='utf-8').write('\n'.join(lines))
    print('\n'.join(head))
    print(f"report -> {args.out}")
    if defective or unchecked:
        sys.exit(1)


if __name__ == '__main__':
    main()
