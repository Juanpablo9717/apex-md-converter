"""Proof that the readability pass (codeblocks.py) is whitespace-only: compares final_paged.md (verified, layers A-F)
with final.md. Header lines that describe the pass are excluded (they are the only intended text change)."""
import json, re, sys, collections
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
from common import OUT
a, b = (open(sys.argv[1]).read(), open(sys.argv[2]).read()) if len(sys.argv) > 2 else ((OUT / "final_paged.md").read_text(), (OUT / "final.md").read_text())
body = lambda s: s[s.index("## Table of contents"):]
def toks(s):
    keep = [l for l in body(s).split("\n") if not l.startswith("```") and not l.startswith("<!-- page ") and not re.fullmatch(r'<a id="page-[^"]+"></a>', l)]
    return "\n".join(keep).split()
ta, tb = toks(a), toks(b)
print("tokens", len(ta), len(tb), "identical sequence:", ta == tb)
pa = re.findall(r"^<!-- page (\d+) \| printed (\S*) -->$", a, re.M); pb = re.findall(r"^<!-- page (\d+) \| printed (\S*) -->$", b, re.M)
print("page markers", len(pa), len(pb), "same order:", pa == pb)
ia = collections.Counter(re.findall(r'<a id="([^"]+)"></a>', a)); ib = collections.Counter(re.findall(r'<a id="([^"]+)"></a>', b))
print("anchors identical:", ia == ib)
fa, fb = len(re.findall(r"^```xml$", a, re.M)), len(re.findall(r"^```xml$", b, re.M))
print("xml blocks", fa, "->", fb, "merged:", fa - fb)
if ta != tb:
    import difflib
    for op in difflib.SequenceMatcher(a=ta, b=tb, autojunk=False).get_opcodes():
        if op[0] != "equal": print(op, ta[op[1]:op[2]][:8], tb[op[3]:op[4]][:8]); break
json.dump({"tokens_identical": ta == tb, "markers_identical": pa == pb, "anchors_identical": ia == ib, "merged_blocks": fa - fb},
          open(OUT / "codeblocks_report.json", "w"))
sys.exit(0 if ta == tb and pa == pb and ia == ib else 1)
