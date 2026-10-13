"""Layer B: structural checks on out/final.md.
- 3,404 page markers, in order
- anchors unique; every internal link resolves
- every Markdown table row has the header's column count
- code fences balanced; XML blocks (consecutive fences across a page break merged) parse, failures classified
- every PDF outline (TOC) entry has its heading
"""
import json, re, collections
import xml.etree.ElementTree as ET
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import OUT

md = (OUT / "final.md").read_text()
meta = json.loads((OUT / "meta.json").read_text())
res = {}

pages = [int(p) for p in re.findall(r"^<!-- page (\d+)", md, flags=re.M)]
res["page_markers"] = len(pages); res["pages_in_order"] = pages == list(range(1, meta["release"]["pages"] + 1))

ids = re.findall(r'<a id="([^"]+)"></a>', md)
c = collections.Counter(ids)
res["anchor_dupes"] = [k for k, v in c.items() if v > 1]
links = re.findall(r"\]\(#([^)]+)\)", md)
res["links"] = len(links); res["broken_links"] = sorted({l for l in links if l not in c})[:20]

# tables
bad_tables, ntables, in_code = [], 0, False
lines = md.split("\n")
i = 0
while i < len(lines):
    l = lines[i]
    if l.startswith("```"): in_code = not in_code
    if not in_code and l.startswith("| ") and i + 1 < len(lines) and re.fullmatch(r"\|(---\|)+", lines[i + 1]):
        ntables += 1
        ncol = len(re.split(r"(?<!\\)\|", l)) - 2
        j = i + 2
        while j < len(lines) and lines[j].startswith("| "):
            if len(re.split(r"(?<!\\)\|", lines[j])) - 2 != ncol: bad_tables.append((i + 1, j + 1))
            j += 1
        i = j; continue
    i += 1
res["tables"] = ntables; res["table_rows_with_wrong_column_count"] = bad_tables[:20]
res["fences_balanced"] = md.count("\n```") % 2 == 0

# XML blocks: merge fences separated only by a page marker / page anchor
blocks, cur, in_code, gap = [], None, False, []
for l in lines:
    if l.startswith("```xml"):
        in_code = True
        if cur is not None and all(re.match(r"(<!-- page|<a id=\"page-|$)", g) for g in gap): pass
        else:
            if cur is not None: blocks.append(cur)
            cur = []
        gap = []; continue
    if l.startswith("```") and in_code: in_code = False; gap = []; continue
    if in_code: cur.append(l)
    elif cur is not None: gap.append(l)
if cur: blocks.append(cur)
kinds = collections.Counter(); samples = collections.defaultdict(list)
for b in blocks:
    t = "\n".join(re.sub(r"^\s*- ", "", x) for x in b).strip()
    if not t.startswith("<"): kinds["not-xml (url/text)"] += 1; continue
    try:
        ET.fromstring(re.sub(r"<\?xml[^>]*\?>", "", t)); kinds["ok"] += 1
    except ET.ParseError as e:
        msg = str(e).split(":")[0]
        try:  # many PDF snippets are several sibling elements or an unwrapped fragment
            ET.fromstring("<root " + " ".join(f'xmlns:{p}="u:{p}"' for p in set(re.findall(r"</?(\w+):", t)) | {"xsi", "xsd", "s", "soap", "mes", "typ"}) + ">" + re.sub(r"<\?xml[^>]*\?>", "", t) + "</root>")
            kinds["ok-as-fragment"] += 1
        except ET.ParseError as e2:
            kinds["fail"] += 1
            if len(samples["fail"]) < 400: samples["fail"].append((str(e2), t[:200]))
res["xml_blocks"] = dict(kinds)

heads = set(re.sub(r"^#+ ", "", h).replace("\\", "") for h in re.findall(r"^#{1,6} .+$", md, flags=re.M))
res["toc_entries_without_heading"] = [t for t in meta["toc"] if t[1].strip() not in heads]
(OUT / "structure_report.json").write_text(json.dumps({**res, "xml_fail_samples": samples["fail"]}, indent=1, ensure_ascii=False))
print(json.dumps(res, indent=1, ensure_ascii=False))
