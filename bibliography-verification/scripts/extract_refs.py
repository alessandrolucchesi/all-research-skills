#!/usr/bin/env python3
"""Extract a manuscript's reference list into structured JSON for verification.

Usage:
    python extract_refs.py manuscript.docx -o refs.json
    python extract_refs.py manuscript.md --heading "Bibliography" -o refs.json

Handles .docx (via pandoc), .md, .txt. Emits one record per reference with the
fields needed by PubMed's lookup_article_by_citation, plus a routing class.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

# Entries matching these never reach PubMed and must be verified by hand.
NON_PUBMED = [
    (r'\bNCT\d{8}\b', 'trial_registration'),
    (r'\b(?:ASH|ASCO|EHA|EBMT|ISTH)\b.{0,40}\babstract\b', 'congress_abstract'),
    (r'\babstract\s+\d+\b', 'congress_abstract'),
    (r'\b(?:bioRxiv|medRxiv)\b', 'preprint'),
    (r'\bPress\b|\bPublishers?\b|\bEdition\b', 'book'),
]


def load_text(path, heading):
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.docx', '.odt', '.rtf'):
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tmp:
            out = tmp.name
        subprocess.run(['pandoc', '-f', 'docx' if ext == '.docx' else ext[1:],
                        path, '-t', 'plain', '-o', out], check=True)
        text = open(out, encoding='utf-8').read()
        os.unlink(out)
    else:
        text = open(path, encoding='utf-8').read()

    idx = text.rfind(heading)
    if idx < 0:
        sys.exit(f"Heading {heading!r} not found. Use --heading to set it.")
    return text[idx + len(heading):]


def split_entries(block):
    """Rejoin wrapped lines, then split on leading 'N.' markers."""
    block = re.sub(r'\n(?!\s*\d+\.\s)', ' ', block)
    found = re.findall(r'(?:^|\n)\s*(\d+)\.\s+(.+?)(?=\n\s*\d+\.\s|\Z)',
                       block, flags=re.S)
    return [(int(n), re.sub(r'\s+', ' ', t).strip()) for n, t in found]


def classify(text):
    for pattern, label in NON_PUBMED:
        if re.search(pattern, text, flags=re.I):
            return label
    return 'pubmed'


def parse(num, text):
    rec = {'ref': num, 'raw': text, 'route': classify(text)}

    m = re.search(r'\b(10\.\d{4,9}/[^\s,;]+)', text)
    if m:
        rec['doi'] = m.group(1).rstrip('.')

    m = re.search(r'\b(1[89]\d{2}|20\d{2})\b', text)
    if m:
        rec['year'] = int(m.group(1))

    # First author surname: leading token(s) before initials.
    m = re.match(r'([A-Z][A-Za-z\u00C0-\u024F\'\-]+(?:\s+[A-Za-z\u00C0-\u024F\'\-]+)?)'
                 r',?\s+[A-Z]{1,3}\b', text)
    if m:
        rec['author'] = m.group(1).strip()

    # Anchor on "<year>;<volume>(<issue>):<page>" then walk back for the journal.
    m = re.search(r'(1[89]\d{2}|20\d{2})\s*;\s*(\d+)'
                  r'(?:\s*\(([^)]+)\))?\s*:\s*([A-Za-z]?\d+)', text)
    if m:
        rec['volume'] = m.group(2)
        if m.group(3):
            rec['issue'] = m.group(3)
        rec['first_page'] = m.group(4)
        head = text[:m.start()].rstrip()
        # Journal sits after the last sentence-ending period. Abbreviation dots
        # ("J Clin Invest.") are followed by a capital with no space-word break,
        # so split on ". " and take the final fragment.
        frag = head
        for sep in ('. ', '? ', '! '):
            if sep in frag:
                frag = frag.split(sep)[-1]
        frag = frag.strip().rstrip('.').strip()
        if 0 < len(frag) <= 60:
            rec['journal'] = frag

    needed = ('author', 'journal', 'year', 'volume', 'first_page')
    rec['parsed'] = all(k in rec for k in needed)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('manuscript')
    ap.add_argument('-o', '--out', default='refs.json')
    ap.add_argument('--heading', default='References')
    args = ap.parse_args()

    entries = split_entries(load_text(args.manuscript, args.heading))
    if not entries:
        sys.exit("No numbered references found.")

    recs = [parse(n, t) for n, t in entries]
    json.dump(recs, open(args.out, 'w', encoding='utf-8'),
              indent=2, ensure_ascii=False)

    pm = [r for r in recs if r['route'] == 'pubmed' and r['parsed']]
    unparsed = [r['ref'] for r in recs if r['route'] == 'pubmed' and not r['parsed']]
    manual = [(r['ref'], r['route']) for r in recs if r['route'] != 'pubmed']

    print(f"{len(recs)} references -> {args.out}")
    print(f"  {len(pm)} ready for PubMed matching")
    if unparsed:
        print(f"  {len(unparsed)} could not be parsed, handle by hand: {unparsed}")
    if manual:
        print("  not in PubMed, verify at source:")
        for n, kind in manual:
            print(f"    [{n}] {kind}")

    print("\nCitation payload for lookup_article_by_citation "
          "(batch in groups of 20):")
    payload = [{k: r[k] for k in ('author', 'journal', 'year', 'volume', 'first_page')}
               | {'key': f"R{r['ref']}"} for r in pm]
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == '__main__':
    main()
