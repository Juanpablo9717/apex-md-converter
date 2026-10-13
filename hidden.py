"""Find text drawn BEFORE an opaque fill that covers it (invisible on the rendered page) -> out/hidden_text.json.
convert.py drops it and verify.py removes it from the reference."""
import json
import pymupdf

from common import OUT, pdf_path

doc = pymupdf.open(pdf_path())
out = {}
for i in range(doc.page_count):
    pg = doc[i]
    fills = [(d["seqno"], d["rect"]) for d in pg.get_drawings() if d["type"] in ("f", "fs") and d.get("fill") and d.get("fill_opacity", 1) == 1 and d["rect"].width > 2 and d["rect"].height > 2]
    if not fills: continue
    for t in pg.get_texttrace():
        bbox = pymupdf.Rect(t["bbox"])
        if bbox.is_empty: continue
        c = pymupdf.Point((bbox.x0 + bbox.x1) / 2, (bbox.y0 + bbox.y1) / 2)
        if any(seq > t["seqno"] and r.contains(c) for seq, r in fills):
            txt = "".join(chr(ch[0]) for ch in t["chars"])
            if txt.strip(): out.setdefault(i + 1, []).append([txt, [round(x, 1) for x in bbox]])
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "hidden_text.json").write_text(json.dumps(out, indent=0))
print(f"hidden text: {sum(len(v) for v in out.values())} runs on {len(out)} pages", {p: [x[0] for x in v] for p, v in out.items()})
