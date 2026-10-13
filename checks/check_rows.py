# Independent structure check of every Schema Elements row: Element name, nesting depth and bold (= required),
# PDF via poppler (pdftohtml -xml), not PyMuPDF which the converter uses. Depth = (x - header x) / 32px (21.5pt @1.5).
import re, html, sys, json, collections
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
from common import OUT
XML = sys.argv[1]; MD = sys.argv[2]

def segs(inner):  # [(bold, text)]
    out = []
    for m in re.finditer(r'<b>(.*?)</b>|([^<]+)|<[^>]+>', inner):
        if m.group(1) is not None: out.append((True, html.unescape(re.sub(r'<[^>]+>', '', m.group(1)))))
        elif m.group(2) is not None: out.append((False, html.unescape(m.group(2))))
    return out

fonts = {}; pages = {}
cur = None
for line in open(XML):
    m = re.match(r'\s*<fontspec id="(\d+)" size="(\d+)" family="([^"]+)"', line)
    if m: fonts[m.group(1)] = ("Bold" in m.group(3), int(m.group(2)))
    m = re.match(r'<page number="(\d+)"', line)
    if m: cur = int(m.group(1)); pages[cur] = []
    m = re.match(r'<text top="(\d+)" left="(\d+)" width="(\d+)" height="(\d+)" font="(\d+)">(.*)</text>', line)
    if m and cur:
        t, l, w, h, f, inner = m.groups()
        fb, fs = fonts[f]
        sg = [(b or fb, s) for b, s in segs(inner)]
        pages[cur].append(dict(top=int(t), left=int(l), h=int(h), size=fs, segs=sg, text="".join(s for _, s in sg)))

def norm(s): return re.sub(r'\s+', '', s)

pdf_rows = {}; layout = None
for p in sorted(pages):
    items = sorted((i for i in pages[p] if 100 < i["top"] < 1040), key=lambda i: (i["top"], i["left"]))
    rows = []; last = None
    for i, it in enumerate(items):
        if it["text"].strip() in ("Element", "Elements") and all(b for b, _ in it["segs"]):
            nxt = [j for j in items if abs(j["top"] - it["top"]) <= 2 and j["left"] > it["left"]]
            if nxt and nxt[0]["text"].strip() in ("Type", "Description", "Max"):
                layout = (it["left"], min(j["left"] for j in nxt)); last = None; continue
        if not layout: continue
        base, bound = layout
        if it["left"] < base - 4 and it["h"] >= 13 and it["text"].strip():
            layout = None; last = None; continue          # prose / heading / code resumes: table ended
        if it["h"] < 13 or not (base - 4 <= it["left"] < bound - 4): continue
        if last and it["left"] == last["left"] and it["top"] - last["bot"] <= 21:
            last["segs"] += it["segs"]; last["bot"] = it["top"]; continue
        last = dict(left=it["left"], top=it["top"], bot=it["top"], base=base, segs=list(it["segs"]))
        rows.append(last)
    out = []
    for r in rows:
        name = norm("".join(s for _, s in r["segs"]))
        if not name: continue
        bs = {b for b, s in r["segs"] if s.strip()}
        d = (r["left"] - r["base"]) / 32
        rd = 1 if 0.3 < d < 0.7 else round(d)   # half-step indent (~8.7pt) used by some tables = one level
        out.append((name, rd, "bold" if bs == {True} else "plain" if bs == {False} else "mixed", abs(d - round(d)) > 0.2 and not 0.3 < d < 0.7))
    if out: pdf_rows[p] = out

md_rows = collections.defaultdict(list); page = None; in_el = False; prev_el = False; hdr = False
for line in open(MD, encoding="utf-8"):
    m = re.match(r'<!-- page (\d+) \|', line)
    if m: page = int(m.group(1)); continue
    if not line.startswith("|"):
        if in_el: prev_el = True
        if line.strip() and not line.startswith("<a id") and not line.startswith("<!--"): prev_el = False
        in_el = False; hdr = False; continue
    cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
    if not hdr:
        hdr = True; h0 = re.sub(r'\*', '', cells[0])
        in_el = h0 in ("Element", "Elements") or (h0 == "" and all(c == "" for c in cells) and prev_el)
        continue
    if re.fullmatch(r'\|(---\|)+', line.strip()) or not in_el: continue
    c = cells[0]
    d = len(re.match(r'(↳*)', c).group(1)); c = c[d:].strip()
    parts = re.split(r'(\*\*.*?\*\*)', c)
    bs = {p.startswith("**") for p in parts if re.sub(r'\*\*|<br>|&nbsp;|\\', '', p).strip()}
    name = norm(html.unescape(re.sub(r'\*\*|<br>|&nbsp;|\\(?=[^\w])|`', '', c)))
    if not name: continue
    md_rows[page].append((name, d, "bold" if bs == {True} else "plain" if bs == {False} else "mixed"))

import difflib
rep = []; stats = collections.Counter()
for p in sorted(set(pdf_rows) | set(md_rows)):
    a = [r[:3] for r in pdf_rows.get(p, [])]; b = md_rows.get(p, [])
    stats["pdf_rows"] += len(a); stats["md_rows"] += len(b)
    for f in pdf_rows.get(p, []):
        if f[3]: rep.append((p, "OFFGRID", f, None))
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal": stats["match"] += i2 - i1; continue
        rep.append((p, op, a[i1:i2], b[j1:j2]))
print(dict(stats)); print("diff blocks:", len(rep))
json.dump(rep, open(OUT / "row_diffs.json", "w"), indent=0, ensure_ascii=False)
for r in rep[:40]: print(r)
