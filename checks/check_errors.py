# Error-code table: every code paired with its full message, PDF (poppler) vs MD, in order.
import re, html, sys
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
from common import OUT
xml, md = open(sys.argv[1]).read(), open(sys.argv[2], encoding="utf-8").read()
def n(s): return re.sub(r'\s+', '', s)
pdf = []
for pg in xml.split('<page number=')[1:]:
    items = sorted(((int(t), int(l), html.unescape(re.sub(r'<[^>]+>', '', x))) for t, l, x in
                    re.findall(r'<text top="(\d+)" left="(\d+)"[^>]*height="1[34]"[^>]*>(.*?)</text>', pg) if 100 < int(t) < 1040))
    cur = None
    for t, l, x in items:
        if 88 <= l <= 100 and re.fullmatch(r'\d{5}', x.strip()): cur = [x.strip(), ""]; pdf.append(cur)
        elif cur and 150 <= l and x.strip(): cur[1] += x
        elif l < 88: cur = None
md_rows = [(c, m) for c, m in re.findall(r'^\| (\d{5}) \| (.*) \|$', md, re.M)]
clean = lambda s: n(html.unescape(re.sub(r'\*\*|<br>|\\(?=[^\w\s])|\[([^\]]*)\]\(#[^)]*\)', lambda m: m.group(1) or '', s)))
print("pdf", len(pdf), "md", len(md_rows))
bad = [(a, b) for a, b in zip(pdf, md_rows) if a[0] != b[0] or n(a[1]) != clean(b[1])]
print("mismatches", len(bad))
for a, b in bad[:20]: print(a, "||", b)
