# PDF-first, search-based audit (adversarial)

A 3,404-page Fiserv PDF ("XP2 APEX Message Reference") was converted into ONE Markdown file:
`<work>/out/final.md` (call it MD).
Your job: start from the PDF, take a concrete item, FIND it in MD by searching for its content, and prove it is
there 100% identical. **Assume MD is wrong until you prove otherwise.** Never edit MD.

Your pages are in `<work>/audit/<batch>/pages.txt` (prepared by `checks/audit_prep.py`); page images in
`<work>/audit/<batch>/img/p<N>.png` (Read them). On those pages pick targets of every kind: XSD request/response schema,
example request and response XML, Schema Elements table rows, Types, message texts, error codes, FAQ, image tables and
cross-references `"X" on page N`. Do not open `md/`: find each target in MD by searching.

## Method, for every target
1. Read the PDF page image(s) and write down the target content exactly as the PDF shows it (from the image — do
   not use any text extraction tool for the PDF).
2. Locate it in MD **by content**, with Grep on MD (e.g. the message name `id="msg-Name"`, an XSD element name,
   an example value like `<MemberId>17028`, an error code `| 00686 |`, a distinctive phrase). Record the query you used
   and how many tool calls it took. Do NOT jump by page number first. Then Read the surrounding MD lines.
3. Confirm the MD location is the right one (the nearest `<!-- page N | printed P -->` line above it must be the
   same PDF page N).
4. Compare item by item, character by character:
   - XSD / XML examples: every line, every element name, attribute, value, namespace, closing tag, order of lines.
     Lines the PDF wrapped at the right margin are re-joined in MD into one line (intended). A space that may or may not
     exist exactly at a right-margin cut is not a finding.
   - Tables: every row and column; the value must be in the SAME row as in the PDF (Type/Max/Description belong to the
     right Element); bold Element = required (MD keeps `**bold**`); nesting: `↳` per indent level under the parent.
     Multi-line cell text joined with spaces or `<br>` is fine. Bullets in cells appear as `•` (sub-bullets prefixed `&nbsp;`).
   - Text: every sentence, number, enumeration value, note.
   - Image tables (FAQ A52/A53): every column of the rows you pick.
   - Cross-references `"X" on page N`: in MD they are links `["X" on page N](#anchor)`; follow the anchor
     (Grep `id="anchor"`) and confirm it is section X and lies on printed page N.
5. Typos that exist in the PDF itself must be kept; only report differences between PDF and MD.

Accepted conventions (not findings): running page header/footer removed; Markdown syntax (`#`, `**`, backslash escapes
`\*` `\<` `\|`, `` ` ``); a table continued on a new page may start with an empty header row; a table row split by a page
break appears as two rows; an XML line cut exactly at a page break stays split between two code blocks; italics not
reproduced; empty spacer rows dropped; `-` bullets become Markdown list items.

## Severity
DATA_MISSING (in PDF, absent in MD) · DATA_WRONG (value differs / in wrong row or cell / wrong nesting / glued or split
token) · ORDER · STRUCTURE · NOT_FOUND (could not find it by searching — say what you tried) · COSMETIC · OK.

## Output
Write `<work>/audit/<batch>/findings.json`: a JSON array with one object per target:
`{"id": <target id>, "cat": "...", "result": "OK|ISSUES", "items_checked": <number of lines/rows/values compared>,
"search": "<query that found it>", "tool_calls_to_find": <n>, "findings": [{"severity": "...", "pdf_page": N,
"pdf": "<exact PDF text>", "md": "<exact MD text>", "note": "..."}]}`.
Reply at the end with only: targets audited, total items_checked, and one line per non-COSMETIC finding.
