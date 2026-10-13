"""Debug helper: print every text span (x, y, font, size, color, text) of the given physical pages."""
import sys
from pathlib import Path
import pymupdf
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import pdf_path

doc = pymupdf.open(pdf_path())
for p in map(int, sys.argv[1:]):
    print("=== page", p)
    for b in doc[p - 1].get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                if s["text"].strip(): print(f'{s["bbox"][0]:6.1f} {s["bbox"][1]:6.1f} {s["font"][:14]:14} {s["size"]:4.1f} {s["color"]:8} |{s["text"][:70]}')
