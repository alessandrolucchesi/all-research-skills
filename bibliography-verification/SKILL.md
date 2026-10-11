---
name: bibliography-verification
description: Verify every reference in a manuscript against PubMed before submission, detecting fabricated or mis-cited entries (wrong authors, wrong volume/pages, wrong DOI, non-existent articles). Use this skill whenever a manuscript, review, letter, correspondence, grant or thesis with a reference list is being prepared, revised, or submitted, and ALWAYS before any submission to a journal. Also use it whenever the user asks to check, audit, validate or "verify the references/bibliography/citations", or when references have been drafted, renumbered, merged or reformatted by a model rather than exported from a reference manager. Trigger even if the user only says "check this is ready to submit".
---

# Bibliography verification

Language models complete bibliographic details from memory. The result looks
correct: plausible authors, plausible volume, plausible DOI. It is frequently
wrong in ways that survive every reading and are caught only by a reviewer,
an editor, or a reader. In a manuscript that argues for scientific priority,
or that criticises another group's citation practice, a fabricated reference
is fatal to credibility.

This skill replaces reading with matching. Never confirm a reference by
recognising it. Match it against a database record or mark it unverified.

## The one rule

**Never fill in a bibliographic field you have not retrieved in this session.**

Not the author list, not the volume, not the page range, not the DOI, not a
congress abstract number, not a trial registration number. If a field is
missing, leave an explicit placeholder for the human. A gap is recoverable;
an invention is not.

## Workflow

### 1. Extract

```bash
python scripts/extract_refs.py <manuscript.docx|.md|.txt> -o refs.json
```

Parses the reference list into structured fields and classifies each entry by
verification route. Review the `unparsed` list it prints: entries it could not
parse must be handled by hand, not skipped.

### 2. Match against PubMed

For every entry classed `pubmed`, call `lookup_article_by_citation` in batches
of 20, passing `author`, `journal`, `year`, `volume`, `first_page` and using
the reference number as `key`.

This tool is the validator. It matches the citation *as written*. A returned
PMID means the coordinates are real; `NOT_FOUND` means they are not.

Two traps:

- **`convert_article_ids` is not a validator.** It returns a PMID only for
  articles deposited in PMC. Silence there means nothing.
- **An empty `author` field in the response is a soft failure.** The record
  matched on journal/year/volume/page but the author did not confirm. Treat it
  as suspect and resolve it in step 3, never as a pass.

### 3. Fetch ground truth

Call `get_article_metadata` on every returned PMID. Save the full response to
`pubmed.json`. Do not compare from reading, compare mechanically in step 4.

The comparison ties each record to its reference by PMID through
`pmid_map.json`, by a `ref` field added to the record, or by DOI where the
manuscript carries one. Write `pmid_map.json` as `{"R1": "19005182", ...}`
when the references carry no DOI, so nothing falls through as unmatched for
want of a key.

### 4. Compare

```bash
python scripts/compare_refs.py refs.json pubmed.json -o report.md
```

Produces a field-by-field diff: title, first author, journal, year, volume,
issue, pages, DOI. Anything flagged is either a manuscript error or a parsing
error, and both need the human.

### 5. Handle what PubMed cannot see

These never appear in PubMed and are **the highest-risk category**, because
they are exactly where invented identifiers hide:

| Type | Route |
|---|---|
| Congress abstracts (ASH, ASCO, EHA) | Search the society's own abstract archive. Verify the abstract number and author list, or replace with the full publication if one now exists |
| Trial registrations (NCT…) | Verify the number resolves on ClinicalTrials.gov and that the registered title matches |
| Books, monographs | Verify publisher and year; no DOI expected |
| Preprints | Use the bioRxiv/medRxiv connector; check whether a peer-reviewed version has since appeared and prefer it |

A congress abstract that has since been published as a full paper should be
replaced, not merely corrected: it strengthens the citation.

### 6. Report

Give the user a verdict with counts, then list each defective entry with what
is wrong, what the record actually says, and the corrected string. Include the
DOI as a link for anything retrieved from PubMed, and attribute PubMed
explicitly — this is a requirement of the connector, not a stylistic choice.

Never silently repair. The author signs the bibliography and must see every
change.

## Failure patterns actually observed

Ordered by frequency in real audits:

1. **DOI correct, everything else invented.** The DOI resolves to a real and
   pertinent paper, but the author list, year, volume and pages belong to
   nothing. Caught only by `lookup_article_by_citation`, never by checking
   that the DOI resolves.
2. **Right paper, wrong coordinates.** Correct title and journal, wrong
   issue and page range, and often a wrong DOI that still looks well-formed.
   Common in papers published in the last 18 months.
3. **Article does not exist at those coordinates.** Plausible author, journal
   and year; no record. Usually a conflation of two real papers.
4. **Invented congress abstract.** Fabricated abstract number, and an author
   who appears in no version of the author list.
5. **Self-citation cited wrongly.** The user is an author on the paper being
   mis-cited. Embarrassing in proportion to the paper's importance. Check the
   author lists of retrieved records against the manuscript's own authors and
   flag any match, because these must be exactly right.

## Scope note

PubMed indexes biomedical and life sciences literature only. Physics,
mathematics, computer science, pure chemistry, engineering and non-medical
social science are not there; absence is not evidence of fabrication. Route
those to the appropriate database or to manual verification and say which.
