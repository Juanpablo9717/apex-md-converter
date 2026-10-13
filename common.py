"""Shared paths and release facts. Everything release-specific is derived from the PDF (outline, title page)."""
import json, os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = Path(os.environ.get("APEX_WORK", ROOT / "work")).resolve()   # ocr/ (input), out/ and ref/ (generated)
OUT, OCR, REF = WORK / "out", WORK / "ocr", WORK / "ref"

def pdf_path():
    p = os.environ.get("APEX_PDF")
    if not p or not Path(p).exists(): sys.exit("APEX_PDF must point to the APEX Message Reference PDF")
    return p

def parts(toc, page_count):
    """Level-1 outline entries -> {title: range(first physical page, next entry's first page)}."""
    top = [(t, p) for lvl, t, p in toc if lvl == 1]
    return {t: range(p, (top[i + 1][1] if i + 1 < len(top) else page_count + 1)) for i, (t, p) in enumerate(top)}

def part(toc, page_count, prefix):
    hits = [r for t, r in parts(toc, page_count).items() if t.startswith(prefix)]
    if len(hits) != 1: sys.exit(f"outline: expected one level-1 entry starting with {prefix!r}, found {len(hits)}")
    return hits[0]

def image_pages():
    return sorted({int(m.group(1)) for f in OCR.glob("p*_*.md") if (m := re.match(r"p(\d+)_", f.name))})

def meta():
    return json.loads((OUT / "meta.json").read_text())
