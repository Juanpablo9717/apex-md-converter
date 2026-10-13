"""Reads the check reports and prints one verdict per layer. Exit 1 if a hard gate fails.
Hard gates (must be exactly clean): A text, B structure, G code-block pass. E/F produce candidate
differences that are mostly checker artifacts: they must be triaged against the page images (RUNBOOK.md)."""
import json, sys
from common import OUT

def load(n): return json.loads((OUT / n).read_text())
ok = True
def line(layer, passed, detail):
    global ok
    ok &= passed
    print(f"{'PASS' if passed else 'FAIL'}  {layer:<34} {detail}")

v = load("verify_report.json")
line("A  text vs pdftotext", not v, f"{len(v)} pages with differences" + (f": {sorted(v, key=int)[:15]}" if v else ""))
s = load("structure_report.json")
sb = s["pages_in_order"] and not s["anchor_dupes"] and not s["broken_links"] and not s["table_rows_with_wrong_column_count"] \
    and s["fences_balanced"] and not s["toc_entries_without_heading"]
line("B  structure", sb, f'{s["page_markers"]} markers, {s["links"]} links, {len(s["broken_links"])} broken, {s["tables"]} tables, '
     f'XML blocks {s["xml_blocks"]}')
c = load("codeblocks_report.json")
line("G  code blocks whitespace-only", c["tokens_identical"] and c["markers_identical"] and c["anchors_identical"],
     f'{c["merged_blocks"]} page-split blocks merged')
img = load("images.json")
line("OCR transcriptions present", all(r["transcribed"] for r in img), f"{len(img)} content images")
print(f"TRIAGE E  row name/depth/bold     {len(load('row_diffs.json'))} diff blocks -> out/row_diffs.json")
print(f"TRIAGE F  Type/Max/Description    {len(load('cell_diffs.json'))} cell diffs -> out/cell_diffs.json")
sys.exit(0 if ok else 1)
