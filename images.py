"""Content images (charts, image-only tables) need a human/agent transcription in ocr/p<page>_<n>.md.

  images.py            list every content image, write out/images/p<page>_<n>.png (200 dpi crops) and
                       out/images.json (page, index, md5 of the embedded image, transcribed yes/no)
  images.py --reuse <old work dir>
                       copy a transcription from a previous release when the embedded image is byte-identical
                       (same md5 in the old out/images.json); page numbers usually shift between releases.
Independent of convert.py (run.sh runs it first); exits 1 while any content image has no transcription.
"""
import json, shutil, sys
import pymupdf

from common import OCR, OUT, pdf_path

def content_images(page):   # same selection and order as convert.py (index n of ocr/p<page>_<n>.md)
    return sorted([im for im in page.get_image_info(hashes=True) if im["bbox"][2] - im["bbox"][0] > 60 and im["bbox"][3] - im["bbox"][1] > 40],
                  key=lambda im: im["bbox"][1])

doc = pymupdf.open(pdf_path())
old = {}
if "--reuse" in sys.argv:
    from pathlib import Path
    prev = Path(sys.argv[sys.argv.index("--reuse") + 1]).resolve()
    old = {r["md5"]: prev / "ocr" / f'p{r["page"]}_{r["index"]}.md' for r in json.loads((prev / "out/images.json").read_text())}
(OUT / "images").mkdir(parents=True, exist_ok=True); OCR.mkdir(parents=True, exist_ok=True)
rows, missing = [], []
for pno in range(doc.page_count):
    for i, im in enumerate(content_images(doc[pno])):
        md5 = im["digest"].hex(); f = OCR / f"p{pno + 1}_{i}.md"
        if not f.exists() and md5 in old and old[md5].exists(): shutil.copy(old[md5], f)
        doc[pno].get_pixmap(dpi=200, clip=im["bbox"]).save(OUT / "images" / f"p{pno + 1}_{i}.png")
        rows.append({"page": pno + 1, "index": i, "md5": md5, "transcribed": f.exists()})
        if not f.exists(): missing.append(f.name)
(OUT / "images.json").write_text(json.dumps(rows, indent=0))
print(f"{len(rows)} content images, {len(rows) - len(missing)} transcribed; missing: {missing or 'none'}")
sys.exit(1 if missing else 0)
