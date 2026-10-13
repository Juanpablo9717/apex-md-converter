"""Two independent transcriptions of each content image must agree row by row (#UNSURE lines are reader notes).
Usage: compare_readers.py   (reads ocr/readerA/*.tsv and ocr/readerB/*.tsv in the work dir; exit 1 on any difference)"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import OCR

a_dir, b_dir = OCR / "readerA", OCR / "readerB"
names = sorted({f.name for f in a_dir.glob("*.tsv")} | {f.name for f in b_dir.glob("*.tsv")})
bad = 0
for n in names:
    fa, fb = a_dir / n, b_dir / n
    if not (fa.exists() and fb.exists()): print(f"{n}: only one reader"); bad += 1; continue
    rows = lambda f: [l for l in f.read_text().strip().split("\n") if not l.startswith("#UNSURE")]   # reader notes, not data
    ra, rb = rows(fa), rows(fb)
    diffs = [(i + 1, x, y) for i, (x, y) in enumerate(zip(ra, rb)) if x.split("\t") != y.split("\t")]
    if len(ra) != len(rb): diffs.append(("rows", len(ra), len(rb)))
    for d in diffs: print(n, d)
    bad += bool(diffs)
print(f"{len(names)} images, {bad} with differences")
sys.exit(1 if bad else 0)
