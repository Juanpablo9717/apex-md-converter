"""Layer A verifier: every page of the PDF (poppler pdftotext, an engine independent of the converter)
against the matching page section of the Markdown.

Per page:
  1. alphanumeric token multiset must match (wrap re-joins reconciled: md token == concat of 2-4 ref tokens);
  2. punctuation character multiset must match;
  3. order: every code block and prose paragraph, whitespace removed, must be a contiguous substring of
     the page's reference text (whitespace removed).
Usage: verify.py <md> [ref_txt]   -> writes out/verify_report.json, prints summary.
"""
import json, re, sys, collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import OUT, REF as REF_DIR, image_pages

MD = Path(sys.argv[1] if len(sys.argv) > 1 else OUT / "final_paged.md")
REF = Path(sys.argv[2] if len(sys.argv) > 2 else REF_DIR / "body.txt")
IMAGE_PAGES = set(image_pages())   # pages whose content is an image: checked by the two-reader transcription instead

TOK = re.compile(r"[A-Za-z0-9]+")
HIDDEN = {int(k): v for k, v in json.loads((OUT / "hidden_text.json").read_text()).items()}
DEHYPHEN = collections.Counter(int(l.split("\t")[0][1:]) for l in (OUT / "joins.tsv").read_text().splitlines()
                               if l.split("\t")[1:2] == ["dehyphen"])
IGNORE_PUNCT = set("• ")

def norm_chars(t):
    return t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')

def md_page_plain(section):
    """Strip only the Markdown syntax the converter emits. Returns (plain_text, code_blocks, prose_units)."""
    plain, codes, prose = [], [], []
    in_code, buf = False, []
    for line in section.split("\n"):
        if line.startswith("```"):
            if in_code: codes.append("\n".join(buf)); plain.extend(buf); buf = []
            in_code = not in_code; continue
        if in_code: buf.append(re.sub(r"^\s*- ", "", line)); continue  # symmetric with the ref '- ' bullet strip
        if re.fullmatch(r'<a id="[^"]*"></a>', line.strip()) or line.startswith("<!-- page"): continue
        if re.fullmatch(r"\|(---\|)+", line.strip()): continue
        s = line
        s = re.sub(r"^#{1,6} ", "", s)
        s = re.sub(r"^\s*- ", "", s)
        is_table = s.startswith("| ")
        s = re.sub(r"\[([^\]]*)\]\(#[^)]*\)", r"\1", s)      # internal links -> text
        s = s.replace("<br>", "\n").replace("↳", "").replace("&nbsp;", " ")
        s = s.replace("**", "")
        s = re.sub(r"``(.+?)``|`([^`]+)`", lambda m: m.group(1) or m.group(2), s)
        if is_table:
            cells = re.split(r"(?<!\\)\|", s)[1:-1]
            s = "\n".join(c.strip() for c in cells)
        s = re.sub(r"\\(.)", r"\1", s)
        s = s.rstrip()
        plain.append(s)
        if not is_table and s.strip(): prose.append(s)
    return re.sub(r"(?m)^\s*- ", "", "\n".join(plain)), codes, prose

def split_md(md):
    pages = {}
    parts = re.split(r"^<!-- page (\d+)[^>]*-->$", md, flags=re.M)
    for i in range(1, len(parts), 2): pages[int(parts[i])] = parts[i + 1]
    return pages

def reconcile(extra_md, missing_ref):
    """Cancel md tokens that are concatenations of ref tokens (re-joined wraps), and the reverse."""
    for a, b in ((extra_md, missing_ref), (missing_ref, extra_md)):
        for tok in sorted(list(a.elements()), key=len, reverse=True):
            if a[tok] <= 0: continue
            parts = [p for p in b if b[p] > 0 and tok.startswith(p) and p != tok]
            def search(rest, used):
                if rest == "": return used
                for p in [p for p in b if b[p] > 0 and rest.startswith(p) and used.count(p) < b[p]]:
                    r = search(rest[len(p):], used + [p])
                    if r: return r
                return None
            if parts and len(tok) <= 200:
                found = search(tok, [])
                if found and len(found) >= 2:
                    a[tok] -= 1
                    for p in found: b[p] -= 1
    return +extra_md, +missing_ref

def exact_partition(extras, missing):
    """True iff every extra md token is exactly a concatenation of missing ref tokens, using each once."""
    if not extras: return sum(missing.values()) == 0
    tok, rest = extras[0], extras[1:]
    def split(s, pool):
        if s == "": yield pool; return
        for p in [p for p in pool if pool[p] > 0 and s.startswith(p)]:
            pool[p] -= 1
            yield from split(s[len(p):], pool)
            pool[p] += 1
    for pool in split(tok, missing):
        if exact_partition(rest, pool): return True
    return False

def main():
    md_pages = split_md(MD.read_text())
    ref_pages = REF.read_text().split("\f")
    report, totals = {}, collections.Counter()
    for pno in range(1, len(ref_pages)):
        ref = norm_chars(ref_pages[pno - 1])
        ref = re.sub(r"(?m)^- ", "", ref)  # '-' used as a bullet glyph becomes a Markdown list marker
        for h in HIDDEN.get(pno, []):     # invisible text (painted under an opaque fill), see hidden.py
            ref = ref.replace(h[0], "", 1)
        sec = md_pages.get(pno)
        if sec is None:
            report[pno] = {"missing_page": True}; totals["missing_pages"] += 1; continue
        plain, codes, prose = md_page_plain(sec)
        plain = norm_chars(plain)
        rt, mt = collections.Counter(TOK.findall(ref)), collections.Counter(TOK.findall(plain))
        raw_extra, raw_missing = mt - rt, rt - mt
        if raw_extra and exact_partition(list(raw_extra.elements()), collections.Counter(raw_missing)):
            extra, missing = collections.Counter(), collections.Counter()   # every md token = exact concat of ref tokens
            rejoined = {"ref": dict(raw_missing), "md": dict(raw_extra)}
        else:
            rejoined = None
            extra, missing = reconcile(raw_extra, raw_missing)
        rp = collections.Counter(c for c in ref if not c.isspace() and not c.isalnum() and c not in IGNORE_PUNCT)
        mp = collections.Counter(c for c in plain if not c.isspace() and not c.isalnum() and c not in IGNORE_PUNCT)
        refws = re.sub(r"\s+", "", ref).replace("•", "")
        order = []
        for unit in codes + prose:
            u = re.sub(r"\s+", "", norm_chars(unit)).replace("•", "")
            if u and u not in refws: order.append(unit[:160])
        entry = {}
        if rejoined: entry["rejoin_equivalent"] = rejoined
        if pno in IMAGE_PAGES:
            entry["image_page"] = True
            missing = collections.Counter()  # ref has (almost) nothing on image pages; checked by OCR consensus
            extra = collections.Counter()
        if missing: entry["missing_tokens"] = dict(missing)
        if extra: entry["extra_tokens"] = dict(extra)
        if DEHYPHEN.get(pno): rp["-"] -= DEHYPHEN[pno]   # line-break hyphens dropped on purpose (joins.tsv)
        pdiff = {k: v for k, v in (rp - mp).items() if v > 0}; pextra = {k: v for k, v in (mp - rp).items()}
        if pdiff and pno not in IMAGE_PAGES: entry["missing_punct"] = pdiff
        if pextra and pno not in IMAGE_PAGES: entry["extra_punct"] = pextra
        if order and pno not in IMAGE_PAGES: entry["order_mismatch"] = order
        for k in ("missing_tokens", "extra_tokens", "missing_punct", "extra_punct", "order_mismatch"):
            if k in entry: totals[k + "_pages"] += 1
        totals["missing_token_count"] += sum(missing.values())
        if any(k in entry for k in ("missing_tokens", "extra_tokens", "missing_punct", "extra_punct", "order_mismatch")):
            report[pno] = entry
    (OUT / "verify_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(json.dumps(totals, indent=1))
    print("pages with any issue:", len(report))

if __name__ == "__main__":
    main()
