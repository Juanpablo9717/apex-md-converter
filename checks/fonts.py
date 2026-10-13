"""Debug helper: font usage histogram (font, size, color) with an example span. Usage: fonts.py <pdf>"""
import pymupdf, collections, sys
doc = pymupdf.open(sys.argv[1])
c = collections.Counter(); ex = {}
for pno in range(doc.page_count):
    for b in doc[pno].get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                k = (s["font"], round(s["size"],1), s["color"])
                c[k] += len(s["text"])
                ex.setdefault(k, (pno+1, s["text"][:60]))
for k, n in c.most_common(40): print(n, k, ex[k])
