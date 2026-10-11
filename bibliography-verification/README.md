# bibliography-verification

Verify every reference in a manuscript against PubMed before submission.

Language models complete bibliographic details from memory, and the result looks
correct: plausible authors, plausible volume, plausible DOI. It is frequently
wrong in ways that survive every reading and are caught only by a reviewer, an
editor, or a reader. This skill replaces reading with matching. A reference is
either matched against a retrieved database record or marked unverified; it is
never confirmed by recognition.

The governing rule is one line: never fill in a bibliographic field you have not
retrieved in this session. A gap is recoverable, an invention is not.

Start at `SKILL.md`.

## What it does

`scripts/extract_refs.py` parses a reference list out of a `.docx`, `.md` or
`.txt` manuscript into structured fields, and routes each entry. Entries that
PubMed cannot see are separated out rather than skipped: congress abstracts,
trial registrations, books and preprints are the highest-risk category, because
they are exactly where invented identifiers hide.

The PubMed connector then matches each citation *as written*, which is the step
that catches a reference whose DOI resolves to a real paper while its authors,
year, volume and pages belong to nothing. `scripts/compare_refs.py` diffs the
manuscript against the retrieved records field by field and writes a report
naming what is wrong, what the record says, and the corrected string.

Nothing is repaired silently. The author signs the bibliography and must see
every change.

## Quickstart

```bash
python scripts/extract_refs.py manuscript.docx -o refs.json
# match refs.json against PubMed with lookup_article_by_citation,
# then get_article_metadata, saving the response to pubmed.json
python scripts/compare_refs.py refs.json pubmed.json -o report.md \
    --authors "Lucchesi,Napolitano"
```

`--authors` flags any retrieved record whose author list contains one of the
manuscript's own authors, because a mis-cited self-citation is embarrassing in
proportion to the paper's importance.

Python 3.9 or later, standard library only. `.docx` input needs `pandoc` on the
path; `.md` and `.txt` need nothing. The matching steps need the PubMed
connector, which is not code and is not bundled here.

## Scope

PubMed indexes biomedical and life sciences literature only. Physics,
mathematics, computer science, pure chemistry, engineering and non-medical
social science are not there, and absence is not evidence of fabrication. The
report says which entries were routed elsewhere rather than passing them.

## Layout

```
SKILL.md                   the workflow, the one rule, the observed failure modes
scripts/extract_refs.py    manuscript to structured references, with routing
scripts/compare_refs.py    field-by-field diff against retrieved records
examples/refs-sample.md    a short reference list exercising all four routes
```
