"""Prepare a visual audit batch (layers C/D) for sub-agents.
Usage: audit_prep.py <batch name> (--pages 48 613 ... | --random 60 [--seed 1])
Writes <work>/audit/<batch>/md/p<N>.md (that page's Markdown, from out/final_paged.md) and img/p<N>.png (100 dpi),
plus pages.txt. Give each sub-agent docs/audit-visual-prompt.md or docs/audit-pdf-first-prompt.md and its pages."""
import random, re, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import OUT, WORK, pdf_path

name, args = sys.argv[1], sys.argv[2:]
md = (OUT / "final_paged.md").read_text()
parts = re.split(r"^(<!-- page (\d+)[^>]*-->)$", md, flags=re.M)
pages = {int(parts[i + 1]): parts[i] + parts[i + 2] for i in range(1, len(parts), 3)}
if args[0] == "--pages": chosen = [int(x) for x in args[1:]]
else:
    seed = int(args[args.index("--seed") + 1]) if "--seed" in args else 1
    chosen = sorted(random.Random(seed).sample(sorted(pages), int(args[1])))
d = WORK / "audit" / name
(d / "md").mkdir(parents=True, exist_ok=True); (d / "img").mkdir(exist_ok=True)
for p in chosen:
    (d / "md" / f"p{p}.md").write_text(pages[p])
    subprocess.run(["pdftoppm", "-r", "100", "-png", "-singlefile", "-f", str(p), "-l", str(p), pdf_path(), str(d / "img" / f"p{p}")], check=True)
(d / "pages.txt").write_text(" ".join(map(str, chosen)) + "\n")
print(f"{len(chosen)} pages -> {d}")
