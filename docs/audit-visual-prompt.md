# Visual audit: PDF page vs Markdown page (adversarial)

You audit a PDF → Markdown conversion of a Fiserv "XP2 APEX Message Reference" (3,404 pages).
**Assume the Markdown is wrong until the image proves otherwise.** Your job is to find every place where
the Markdown page does not carry the same information as the PDF page.

For each page N in `<work>/audit/<batch>/pages.txt`:
1. Read `<work>/audit/<batch>/md/pN.md` (the Markdown for that PDF page; prepared by `checks/audit_prep.py`).
2. Read `<work>/audit/<batch>/img/pN.png` (the rendered PDF page) with the Read tool.
3. Compare, top to bottom: every heading, paragraph, list item, table row and cell, XML/XSD line, note.

## Deliberate conventions — NOT findings
- The running page header ("XP2 APEX Suite, Message Reference", section name, "Fiserv") and footer
  ("2023.1.10 XP2 APEX", page number, "FISERV CONFIDENTIAL | Intended Only for XP2 Clients") are removed on purpose.
  The page marker `<!-- page N | printed P -->` + `<a id="page-P">` replaces them.
- `<a id="...">` anchors, Markdown heading `#` levels, `**bold**`, backslash escapes (`\*`, `\<`, `\|`), `` `code` `` spans.
- Cross-references `"X" on page N` are wrapped as Markdown links `["X" on page N](#...)` — fine.
- Tables: `<br>` = line break inside a cell; `↳` = nesting depth in the Element column (`↳` child, `↳↳` grandchild);
  a table that continues from the previous page starts with an empty header row `|  |  |`.
- In XML/XSD code blocks, lines the PDF wrapped at the right margin were re-joined into one line (intended).
- Element names that the PDF split over several lines inside a cell were joined (e.g. `PrintDescription`/`OnReceipt`/`Statement` → `PrintDescriptionOnReceiptStatement`) — intended.
- Words the PDF broke across lines in a narrow cell (e.g. `FinancialServi`/`ces`) were joined — intended.
- Bullets `•` outside tables become Markdown list items `- `.
- Images: the content of images is transcribed in place (marked `<!-- image pN_k ... -->`). For those, DO compare the transcription with the picture row by row.
- Typos that exist in the PDF itself (e.g. "ExampleResponse", "CreditBureaReport", a missing `>` in XML) must be kept — they are NOT findings. Only report when Markdown differs from the PDF.

## What IS a finding
- DATA_MISSING: text/value/row/cell/line present in the PDF but absent in the Markdown.
- DATA_WRONG: a value differs (digit, character, symbol, sign, case), a value is in the wrong cell/column/row,
  a description attached to the wrong element, wrong nesting depth (`↳` count) vs the indentation in the PDF,
  two different words glued together that are separate in the PDF (or one identifier split), wrong number.
- ORDER: content in a different order than the PDF reading order (e.g. list columns interleaved, Q/A labels misplaced).
- STRUCTURE: table broken (row split/merged wrongly, columns shifted), heading on the wrong text, code block that
  should be prose or vice-versa, list item merged with the next.
- COSMETIC: anything else worth fixing that does not change information.

Be specific and verifiable. Quote the exact Markdown text and the exact PDF text.

## Output
Write `<work>/audit/<batch>/findings.json`: a JSON array, one object per finding:
`{"page": N, "severity": "DATA_MISSING|DATA_WRONG|ORDER|STRUCTURE|COSMETIC", "md": "<exact md excerpt>", "pdf": "<what the PDF shows>", "note": "<short explanation>"}`
Also include one object per page with no findings: `{"page": N, "severity": "OK"}` so coverage can be counted.
Reply at the end with only: number of pages audited, and counts per severity.
