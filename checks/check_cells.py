# Every Element-table row: are Type, Max and Description in the SAME row as in the PDF? PDF via poppler
# (pdftohtml -xml), independent of the converter's PyMuPDF. Rows paired by Element name, then cells compared.
import re, html, sys, json, collections, difflib
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
from common import OUT
XML = sys.argv[1]; MD = sys.argv[2]

pages = {}; cur = None
for line in open(XML):
    m = re.match(r'<page number="(\d+)"', line)
    if m: cur = int(m.group(1)); pages[cur] = []
    m = re.match(r'<text top="(\d+)" left="(\d+)" width="(\d+)" height="(\d+)" font="(\d+)">(.*)</text>', line)
    if m and cur:
        t, l, w, h, f, inner = m.groups()
        pages[cur].append(dict(top=int(t), left=int(l), h=int(h), text=html.unescape(re.sub(r'<[^>]+>', '', inner))))

def norm(s): return re.sub(r'[\s•]+', '', s)
def md_norm(c):
    c = re.sub(r'\[([^\]]*)\]\(#[^)]*\)', r'\1', c)
    c = re.sub(r'\*\*|<br>|&nbsp;|`|↳', '', c)
    c = re.sub(r'\\(?=[^\w\s])', '', c)
    return norm(html.unescape(c))

pdf = {}; layout = None
for p in sorted(pages):
    items = sorted((i for i in pages[p] if 100 < i["top"] < 1040 and i["h"] >= 13), key=lambda i: i["top"])
    key = None
    for i in items:                                   # same visual line within 3px (Int at 742, name at 743)
        if key is None or i["top"] - key > 3: key = i["top"]
        i["line"] = key
    items.sort(key=lambda i: (i["line"], i["left"]))
    rows = []; last = None
    for it in items:
        if it["text"].strip() in ("Element", "Elements"):
            hdr = sorted((j for j in items if abs(j["top"] - it["top"]) <= 2 and j["left"] > it["left"]), key=lambda j: j["left"])
            if hdr and hdr[0]["text"].strip() in ("Type", "Description", "Max"):
                layout = (it["left"], [(j["text"].strip(), j["left"]) for j in hdr]); last = None; continue
        if not layout: continue
        base, cols = layout; bound = cols[0][1]
        if it["left"] < base - 4 and it["text"].strip():
            layout = None; last = None; continue
        if base - 4 <= it["left"] < bound - 4:
            beside = any(j["line"] == it["line"] and j["left"] >= bound - 6 for j in items)
            if last and it["left"] == last["left"] and it["top"] - last["etop"] <= 22:
                last["name"] += it["text"]; last["etop"] = it["top"]; continue
            last = dict(left=it["left"], top=it["top"], etop=it["top"], name=it["text"], cells=collections.defaultdict(str))
            rows.append(last); continue
        if last is None: continue                      # continuation of a row from the previous page
        col = [c for c, x in cols if it["left"] >= x - 6]
        if col: last["cells"][col[-1]] += " " + it["text"]
    if rows: pdf[p] = [(norm(r["name"]), {k: norm(v) for k, v in r["cells"].items()}) for r in rows]

md = collections.defaultdict(list); page = None; hdr = None; prev = None
for line in open(MD, encoding="utf-8"):
    m = re.match(r'<!-- page (\d+) \|', line)
    if m: page = int(m.group(1)); continue
    if not line.startswith("|"):
        if line.strip() and not line.startswith(("<a id", "<!--")): prev = None
        hdr = None if not line.strip() or line.startswith(("<a id", "<!--")) else hdr
        if hdr: prev = hdr
        hdr = None; continue
    cells = [c.strip() for c in line.strip()[1:-1].split(" | ")]
    if hdr is None:
        names = [re.sub(r'\*', '', c) for c in cells]
        hdr = names if names[0] in ("Element", "Elements") else (prev if all(n == "" for n in names) and prev else ["x"])
        continue
    if re.fullmatch(r'\|(---\|)+', line.strip()) or hdr[0] not in ("Element", "Elements") or len(cells) != len(hdr): continue
    name = md_norm(cells[0])
    if name: md[page].append((name, {hdr[j]: md_norm(cells[j]) for j in range(1, len(hdr))}))

stats = collections.Counter(); bad = []; unp = []
for p in sorted(pdf):
    a, b = pdf[p], md.get(p, [])
    sm = difflib.SequenceMatcher(a=[r[0] for r in a], b=[r[0] for r in b], autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op != "equal":
            stats["unpaired_rows"] += i2 - i1
            if i2 > i1: unp.append(dict(page=p, op=op, pdf=[r[0] for r in a[i1:i2]], md=[r[0] for r in b[j1:j2]]))
            continue
        for (n, pc), (_, mc) in zip(a[i1:i2], b[j1:j2]):
            stats["rows"] += 1
            for col in ("Type", "Max", "Description"):
                if col not in mc and col not in pc: continue
                x, y = pc.get(col, ""), mc.get(col, "")
                stats[col + "_checked"] += 1
                ok = x == y if col != "Description" else (x == y or difflib.SequenceMatcher(a=x, b=y, autojunk=False).ratio() >= 0.98)
                if not ok: bad.append(dict(page=p, element=n, col=col, pdf=x, md=y))
print(dict(stats)); print("cell mismatches:", len(bad), collections.Counter(b["col"] for b in bad))
json.dump(bad, open(OUT / "cell_diffs.json", "w"), indent=0, ensure_ascii=False)
json.dump(unp, open(OUT / "unpaired_rows.json", "w"), indent=0, ensure_ascii=False)
