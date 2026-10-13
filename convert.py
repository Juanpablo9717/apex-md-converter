"""APEX Message Reference PDF -> single Markdown file.

Deterministic, geometry-based:
- tables come from the filled cell rectangles the PDF draws (exact rows/cols, nesting from x offset);
- code keeps Courier column positions; lines the PDF wrapped at the right margin are re-joined
  (mid-token wraps without a space), every join is logged to out/joins.tsv for audit;
- prose lines are joined only when the PDF wrapped them (wrap test against the right edge),
  otherwise the line break is kept;
- headings from font + the PDF outline; large images replaced by ocr/p<page>_<idx>.md.
"""
import json, re, sys, collections
from pathlib import Path
import pymupdf

from common import OCR, OUT, part, pdf_path
HEADER_MAX_Y, FOOTER_MIN_Y = 56.0, 696.0
FLOW_LEFT, FLOW_RIGHT, CODE_RIGHT = 56.2, 562.0, 559.5
GRAY_LABEL = 6710886
CELL_FILLS = {(1.0, 1.0, 1.0), (0.4, 0.6, 0.8), (0.86, 0.86, 0.86), (1.0, 1.0, 0.0)}
CH3 = CH4 = range(0)     # physical pages of Chapter 3 / Chapter 4: Type Definitions, set from the outline in main()

VOCAB, VOCAB_W, STANDALONE = set(), set(), collections.Counter()
NOT_AT_END, NOT_AT_START = collections.Counter(), collections.Counter()
JOINS = []

def is_code(s): return s["font"].startswith("CourierNew")
def is_bold(s): return "Bold" in s["font"]
def slug(s): return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")

def esc(t, in_table=False):
    t = t.replace("\\", "\\\\").replace("*", "\\*").replace("<", "\\<").replace("`", "\\`")
    return t.replace("|", "\\|") if in_table else t

def text_width(t, size): return pymupdf.get_text_length(t, fontname="helv", fontsize=size)

# ---------------------------------------------------------------- runs
# a "line" is a list of runs (kind, text); kind in plain|bold|code
def spans_to_runs(spans):
    runs, last_x1 = [], None
    for s in spans:
        t = s["text"]
        if not t: continue
        if last_x1 is not None and runs and not runs[-1][1].endswith(" ") and not t.startswith(" "):
            if s["bbox"][0] - last_x1 > s["size"] * 0.15: t = " " + t
        kind = "code" if is_code(s) else "bold" if is_bold(s) else "plain"
        runs.append((kind, t)); last_x1 = s["bbox"][2]
    return runs

def runs_text(runs): return "".join(t for _, t in runs)

def fmt(runs, in_table=False):
    merged = []
    for k, t in runs:
        if merged and merged[-1][0] == k: merged[-1] = (k, merged[-1][1] + t)
        else: merged.append((k, t))
    out = ""
    for k, t in merged:
        lead = t[: len(t) - len(t.lstrip())]; core = t.strip(); trail = t[len(lead) + len(core):]
        if not core: out += t; continue
        if k == "code":
            fence = "``" if "`" in core else "`"
            seg = f"{fence}{core}{fence}"
            if in_table: seg = seg.replace("|", "\\|")
        elif k == "bold": seg = f"**{esc(core, in_table)}**"
        else: seg = esc(core, in_table)
        out += lead + seg + trail
    return out

DICT = {w.strip().lower() for w in open("/usr/share/dict/words")}
def is_word(w):
    w = w.lower()
    return w in DICT or (w.endswith("s") and w[:-1] in DICT) or (w.endswith("es") and w[:-2] in DICT)

def glue(a_text, b_text, identifier_ctx):
    """Separator when joining a wrapped line: '' for a mid-word break, ' ' otherwise,
    None = drop the line-break hyphen ('MAINTE-' + 'NANCE' -> 'MAINTENANCE')."""
    if a_text.endswith((" ", "/", "_")) or b_text.startswith(" "): return ""
    m = re.search(r"([A-Za-z]+)-$", a_text); n = re.match(r"([A-Za-z]+)", b_text)
    if not m and re.search(r"\S-$", a_text): return ""
    if m:
        if n and is_word(m.group(1) + n.group(1)) and not is_word(m.group(1)) and len(m.group(1)) > 3: return None
        return ""                                               # 'non-' + 'certificate'
    m1 = re.search(r"([A-Za-z0-9]+)$", a_text); m2 = re.match(r"([A-Za-z0-9]+)", b_text)
    if m1 and m2:
        L, R = m1.group(1), m2.group(1)
        both_words = is_word(L) and is_word(R)  # 'Reject' + 'Overdrafts' is a UI label, not one token
        if (L + R) in VOCAB and (identifier_ctx or (not both_words and (NOT_AT_END[L] < 2 or NOT_AT_START[R] < 2))):
            return ""
        # a CamelCase identifier cut before a lowercase tail ('...IndividualCred' + 'itScoreUpdates')
        if re.fullmatch(r"[A-Z][A-Za-z0-9]{7,}", L) and re.search(r"[a-z][A-Z]", L) and R[:1].islower() \
                and not is_word(R) and not is_word(L) and NOT_AT_END[L] < 2 and NOT_AT_START[R] < 2:
            return ""
    return " "

def is_bullet_text(t): return t.startswith("•") or t.startswith(("- ", "– ", "▪"))

def join_lines(lines, limit_of, identifier_ctx=False, ctx="", with_meta=False):
    """lines: list of dicts(runs, x0, x1, size). Returns list of logical lines (runs),
    or (runs, first physical line) pairs with with_meta."""
    out, prev, firsts, cont_x = [], None, [], None
    for l in lines:
        t = runs_text(l["runs"]).strip()
        if not t: continue
        if prev is not None and not prev.get("tabular") and not l.get("tabular"):
            first_word = t.split(" ")[0]
            wrapped = prev["x1"] + text_width(" " + first_word, l["size"]) > limit_of(prev) - 4.0
            bullet = is_bullet_text(t) or re.match(r"(Note|Important|Notes):", t)
            aligned = cont_x is None or l["x0"] >= cont_x - 4   # a line that steps back left of the text starts something new
            if runs_text(out[-1]).rstrip().endswith(">") and t.startswith("<"): aligned = False   # XML lines set in prose
            if wrapped and not bullet and aligned:
                sep = glue(runs_text(out[-1]), runs_text(l["runs"]).lstrip(), identifier_ctx)
                if sep is None:   # drop the line-break hyphen
                    k, last = out[-1][-1]; out[-1][-1] = (k, last.rstrip()[:-1]); sep = ""
                    JOINS.append((ctx, "dehyphen", runs_text(out[-1])[-25:], t[:25]))
                elif sep == "" and not runs_text(out[-1]).endswith(" "):
                    JOINS.append((ctx, "prose-nospace", runs_text(out[-1])[-25:], t[:25]))
                first = l["runs"][0]
                out[-1] = out[-1] + [(first[0], sep + first[1].lstrip())] + l["runs"][1:]
                prev = l; continue
        out.append(list(l["runs"])); firsts.append(l)
        sp = l["spans"]
        cont_x = sp[1]["bbox"][0] if is_bullet_text(t) and len(sp) > 1 else l["x0"]
        prev = l
    return list(zip(out, firsts)) if with_meta else out

# ---------------------------------------------------------------- geometry
def cluster(vals, tol=1.5):
    out = []
    for v in sorted(vals):
        if out and v - out[-1][-1] <= tol: out[-1].append(v)
        else: out.append([v])
    return [sum(c) / len(c) for c in out]

def idx_of(v, bounds):
    return min(range(len(bounds)), key=lambda i: abs(bounds[i] - v))

def group_lines(spans, tol=2.5):
    lines = []
    for s in sorted(spans, key=lambda s: ((s["bbox"][1] + s["bbox"][3]) / 2, s["bbox"][0])):
        yc = (s["bbox"][1] + s["bbox"][3]) / 2
        if lines:
            L = lines[-1]
            ov = min(L["y1"], s["bbox"][3]) - max(L["y0"], s["bbox"][1])
            h = min(L["y1"] - L["y0"], s["bbox"][3] - s["bbox"][1])
            small = min([s["size"]] + [x["size"] for x in L["spans"]]) < 8.8 and not is_code(s)
            if abs(L["yc"] - yc) <= tol or (small and ov > 0.5 * h):  # superscripts (®) join the line
                L["spans"].append(s); L["y0"] = min(L["y0"], s["bbox"][1]); L["y1"] = max(L["y1"], s["bbox"][3]); continue
        lines.append({"yc": yc, "spans": [s], "y0": s["bbox"][1], "y1": s["bbox"][3]})
    for l in lines:
        l["spans"].sort(key=lambda s: s["bbox"][0])
        l["x0"] = l["spans"][0]["bbox"][0]; l["x1"] = max(s["bbox"][2] for s in l["spans"])
        l["y0"] = min(s["bbox"][1] for s in l["spans"]); l["y1"] = max(s["bbox"][3] for s in l["spans"])
        l["size"] = l["spans"][0]["size"]
        l["runs"] = spans_to_runs(l["spans"])
        gaps = [b["bbox"][0] - a["bbox"][2] for a, b in zip(l["spans"], l["spans"][1:])]
        l["tabular"] = bool(gaps) and max(gaps) > 40
    return lines

# ---------------------------------------------------------------- code
def code_text(line, origin=FLOW_LEFT):
    out = ""
    for s in line["spans"]:
        col = max(0, round((s["bbox"][0] - origin) / (s["size"] * 0.6)))
        t = s["text"]
        if len(out) < col: out += " " * (col - len(out))
        elif out and not out.endswith(" ") and not t.startswith(" "): out += " "
        out += t
    return out.rstrip()

def code_sep(ptxt, nxt, full, block=""):
    """Separator for a re-joined code wrap. A line that ends exactly at the last column (full) was cut
    without regard to spaces, so a dropped space is decided by the document's own vocabulary."""
    a, b = ptxt[-1], nxt[0]
    if a in "-_/=": return ""
    if re.match(r"[\w:.-]+=", nxt) and (a == '"' or re.search(r"<[\w:.-]+$", ptxt)) and not full:
        return " "                                              # next is an attribute: '<Description' + 'xmlns="..."'
    if re.search(r"</?[\w:.-]+$", ptxt): return ""              # cut inside a tag name ('</wsa:Act' + 'ion>')
    if re.search(r"https?://[^\s\"'<>]*$", ptxt) and not re.match(r"[\w:.-]+=", nxt):
        return ""                                               # cut inside a URL (no spaces in a URL)
    if nxt.startswith("/>"): return " " if " />" in block else ""                  # follow the block's own style
    if b == '"' and ptxt.count('"') % 2 == 1: return ""       # closing quote of the value                                   # 'oasis-' + 'open.org', 'IMMEDIATE_' + 'CHANGE'
    m1 = re.search(r"([A-Za-z0-9]+)$", ptxt); m2 = re.match(r"([A-Za-z0-9]+)", nxt)
    if m1 and m2:
        L, R = m1.group(1), m2.group(1)
        if is_word(L) and is_word(R) and len(L) > 1 and len(R) > 1: return " "    # 'balance' + 'on'
        if STANDALONE[L + R] > 0: return ""                    # 'AccountAdjustmentT' + 'ype', 'x' + 'mlns'
        if STANDALONE[L] >= 2 and STANDALONE[R] >= 2: return " "  # 'J' + 'DOE', 'or' + 'FSA', 'Operator' + '269'
        return "" if full else " "
    if a == '"' and b.isalpha(): return " "                  # next attribute
    if b == "(": return " "
    if b == "<": return ""
    return "" if full else " "

def code_block(lines, ctx):
    """lines: group_lines() output of consecutive Courier lines. Re-joins PDF right-margin wraps."""
    body, prev = [], None
    for l in lines:
        txt = code_text(l)
        if prev is not None:
            cw = l["size"] * 0.6
            at_margin = abs(l["x0"] - FLOW_LEFT) < 1.0
            ptxt = body[-1]
            # wraps cut mid-token end exactly at the last column (93 at 9pt): measured on the whole PDF
            full = (prev["x1"] - FLOW_LEFT) / cw >= int((CODE_RIGHT - FLOW_LEFT) / cw) - 0.3
            first_word = txt.strip().split(" ")[0]
            word_wrap = prev["x1"] + cw * (1 + len(first_word)) > CODE_RIGHT + cw * 0.5
            nxt0 = txt.strip()
            # only re-join when the break is inside XML: an open tag left unclosed, a closing tag
            # or an attribute on the continuation. Fixed-width text (credit reports) is never re-flowed.
            xml_wrap = ptxt.count("<") > ptxt.count(">") or "</" in nxt0 or re.match(r"^[\w:.-]+=", nxt0) \
                or nxt0.startswith(("/>", ">")) or ptxt.count('"') % 2 == 1 \
                or (full and not nxt0.startswith("<") and ">" in nxt0) \
                or (not nxt0.startswith("<") and '="' in ptxt and ">" in nxt0) \
                or (full and re.search(r"https?://\S+$", ptxt) and " " not in nxt0 and not nxt0.startswith("<"))
            in_value = ptxt.count('"') % 2 == 1 and "<" in ptxt     # cut inside an attribute value
            if at_margin and l["y0"] - prev["y1"] < 6 and not ptxt.rstrip().endswith(">") and (full or word_wrap or in_value) and xml_wrap:
                sep = code_sep(ptxt, nxt0, full, "\n".join(code_text(x) for x in lines))
                JOINS.append((ctx, "code-" + ("char" if full else "word"), ptxt[-30:], txt.strip()[:30]))
                body[-1] = ptxt + sep + txt.strip(); prev = l; continue
            # a column-0 line that does not start a tag, right after an unfinished tagged line inside an
            # indented block, is the tail of a source wrap ('</xsd:documenta' + 'tion>', 'x' + 'mlns:atp=')
            nxt = txt.strip()
            indented_prev = len(ptxt) - len(ptxt.lstrip()) > 0
            if at_margin and l["y0"] - prev["y1"] < 6 and not nxt.startswith("<") and "<" in ptxt \
                    and not ptxt.rstrip().endswith(">") and indented_prev and (ptxt.count("<") > ptxt.count(">") or "</" in nxt or ">" in nxt):
                m1 = re.search(r"([A-Za-z0-9]+)$", ptxt); m2 = re.match(r"([A-Za-z0-9]+)", nxt)
                tight = bool(m1 and m2 and STANDALONE[m1.group(1) + m2.group(1)] > 0
                             and (NOT_AT_END[m1.group(1)] < 2 or NOT_AT_START[m2.group(1)] < 2))
                if tight:  # only a token split in two; never re-flow fixed-width text (credit reports)
                    JOINS.append((ctx, "code-col0-char", ptxt[-30:], nxt[:30]))
                    body[-1] = ptxt + nxt; prev = l; continue
            if l["y0"] - prev["y1"] > 9: body.append("")
        body.append(txt); prev = l
    return "```xml\n" + "\n".join(body) + "\n```"

# ---------------------------------------------------------------- tables
def find_tables(page):
    cells = []
    for d in page.get_drawings():
        r = d["rect"]
        if d["type"] not in ("f", "fs") or not d.get("fill"): continue
        if tuple(round(c, 2) for c in d["fill"]) not in CELL_FILLS: continue
        if r.width < 4 or r.height < 4 or r.y0 < HEADER_MAX_Y - 2 or r.y1 > FOOTER_MIN_Y + 4: continue
        if any(abs(r.x0-c.x0)<.5 and abs(r.y0-c.y0)<.5 and abs(r.x1-c.x1)<.5 and abs(r.y1-c.y1)<.5 for c in cells): continue
        cells.append(pymupdf.Rect(r))
    # tables drawn only with line segments (FAQ white rows, a few others): take their lattice cells
    fills = list(cells)
    for t in page.find_tables(strategy="lines").tables:
        for c in t.cells:
            if not c: continue
            r = pymupdf.Rect(c)
            if r.width < 4 or r.height < 4: continue
            if any((r & f).get_area() > 0.8 * r.get_area() for f in fills): continue
            if not page.get_textbox(r).strip(): continue
            cells.append(r)
    parent = list(range(len(cells)))
    def f(i):
        while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for i in range(len(cells)):
        a = cells[i] + (-1.5, -1.5, 1.5, 1.5)
        for j in range(i + 1, len(cells)):
            if a.intersects(cells[j]): parent[f(i)] = f(j)
    groups = collections.defaultdict(list)
    for i, c in enumerate(cells): groups[f(i)].append(c)
    tables = []
    for g in groups.values():
        bbox = pymupdf.Rect(g[0])
        for c in g[1:]: bbox |= c
        tables.append({"bbox": bbox, "cells": g})
    return sorted(tables, key=lambda t: t["bbox"].y0)

def table_md(t, spans, ctx):
    xs = cluster([c.x0 for c in t["cells"]] + [t["bbox"].x1], tol=5)  # boundaries <5pt apart are one column
    ys = cluster([c.y0 for c in t["cells"]] + [t["bbox"].y1])
    ncol, nrow = len(xs) - 1, len(ys) - 1
    cellinfo = []
    for c in t["cells"]:
        r0, c0 = idx_of(c.y0, ys), idx_of(c.x0, xs)
        c1 = max(c0 + 1, idx_of(c.x1, xs))
        cellinfo.append([r0, c0, c1, c, []])
    orphans = []
    for s in spans:
        cx = s["bbox"][0] + 2; cy = (s["bbox"][1] + s["bbox"][3]) / 2
        hit = [ci for ci in cellinfo if ci[3].x0 - 1 <= cx <= ci[3].x1 + 1 and ci[3].y0 - 1 <= cy <= ci[3].y1 + 1]
        if hit: min(hit, key=lambda ci: ci[3].width * ci[3].height)[4].append(s)
        else: orphans.append(s)
    grid = [[None] * ncol for _ in range(nrow)]
    for r0, c0, c1, rect, sp in cellinfo:
        if grid[r0][c0] is not None and grid[r0][c0].get("spans"):
            grid[r0][c0]["spans"] += sp  # stacked duplicate cell: merge content
        else:
            grid[r0][c0] = {"rect": rect, "spans": sp}
        for cc in range(c0 + 1, c1):
            if grid[r0][cc] is None: grid[r0][cc] = {"merged": True}
    # a first-column cell drawn over two sub-rows (Type/Max/Description in the lower one) is one row
    for r in range(1, nrow):
        up = grid[r - 1][0]
        if grid[r][0] and grid[r][0].get("spans"): continue
        if not (up and up.get("rect") and up["rect"].y1 >= ys[r + 1] - 2): continue
        for j in range(ncol):
            c = grid[r][j]
            if not c or not c.get("spans"): continue
            u = grid[r - 1][j]
            if u and u.get("spans") is not None and not u.get("merged"): u["spans"] = u["spans"] + c["spans"]
            else: grid[r - 1][j] = {"rect": c["rect"], "spans": c["spans"]}
            grid[r][j] = None
    # nesting depth for first column from first-line x offset
    header_bold = all(all(is_bold(sp) for sp in c["spans"]) for c in grid[0] if c and c.get("spans")) and any(c and c.get("spans") for c in grid[0])
    offs = []
    for row in (grid[1:] if header_bold else grid):
        c = row[0]
        if c and c.get("spans"): offs.append(min(s["bbox"][0] for s in c["spans"]) - c["rect"].x0)
    # the header's own Element offset is level 0 when the header is repeated on a continued page
    h0 = grid[0][0] if header_bold else None
    base = (min(sp["bbox"][0] for sp in h0["spans"]) - h0["rect"].x0) if h0 and h0.get("spans") else None
    depth_bounds = cluster(offs + ([base] if base is not None else []), tol=3)
    if base is not None: depth_bounds = [b for b in depth_bounds if b >= base - 3]
    nest = len(depth_bounds) > 1
    levels = list(range(len(depth_bounds)))
    rel = [v - depth_bounds[0] for v in depth_bounds]
    if any(6 <= r <= 11 for r in rel) and any(19 <= r <= 24 for r in rel):
        # p. 613: half-step (~8.7pt) and full-step (21.5pt) children in one table are both one level down
        levels = [1 if 6 <= r <= 11 else round(r / 21.5) for r in rel]
    header_bold = all(all(is_bold(sp) for sp in c["spans"]) for c in grid[0] if c and c.get("spans")) and any(c and c.get("spans") for c in grid[0])
    rows = []
    for ri, row in enumerate(grid):
        vals = []
        for j, c in enumerate(row):
            if not c or c.get("merged") or not c.get("spans"): vals.append(""); continue
            lines = group_lines(c["spans"])
            is_header = ri == 0 and header_bold
            if len(lines) > 1 and (j == 0 or is_header):
                toks = [runs_text(l["runs"]).strip() for l in lines]
                joined = "".join(toks)
                ok = joined in VOCAB_W if is_header else (joined in VOCAB or joined in VOCAB_W)
                # element names (XSD) never contain spaces: single CamelCase fragments per line form one name
                camel = not is_header and j == 0 and all(re.fullmatch(r"[A-Z0-9][A-Za-z0-9_]*", t) for t in toks) \
                    and any(re.search(r"[a-z]", t) for t in toks)
                if all(t and " " not in t for t in toks) and (ok or camel):
                    JOINS.append((ctx, "identifier-cell" if ok else "identifier-camel", "|".join(toks), ""))
                    merged = dict(lines[0]); merged["runs"] = [(k, t.strip()) for l in lines for k, t in l["runs"]]
                    merged["x1"] = max(l["x1"] for l in lines); lines = [merged]
            limit = c["rect"].x1 - 3.5
            logical = join_lines(lines, lambda p: limit, identifier_ctx=(j == 0 and not is_header), ctx=ctx, with_meta=True)
            bxs = [f["x0"] for r, f in logical if is_bullet_text(runs_text(r).strip())]
            parts = []
            for r, f in logical:
                t = fmt(r, in_table=True).strip()
                if bxs and is_bullet_text(runs_text(r).strip()) and f["x0"] > min(bxs) + 6:
                    t = "&nbsp;&nbsp;&nbsp;&nbsp;" + t      # sub-bullet under the previous bullet
                parts.append(t)
            txt = "<br>".join(parts)
            if j == 0 and not is_header:
                off = lines[0]["x0"] - c["rect"].x0
                if nest: d = levels[idx_of(off, depth_bounds)]
                else:   # a page of only child rows (table continued from the previous page): Element
                        # text sits at 4pt (level 0) and +21.5pt per level, measured on the whole PDF
                    k = round((off - 4.2) / 21.5)
                    d = k if k > 0 and abs(off - 4.2 - 21.5 * k) <= 3.5 else 0
                if d: txt = "↳" * d + " " + txt
            vals.append(txt)
        rows.append(vals)
    keep = [j for j in range(ncol) if any(r[j] for r in rows)]
    rows = [[r[j] for j in keep] for r in rows if any(r[j] for j in keep)]
    if not rows: return "", orphans
    if not header_bold: rows = [[""] * len(rows[0])] + rows  # first PDF row is data, not a header
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * len(rows[0])]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out), orphans

def image_md(pno, i):
    f = OCR / f"p{pno+1}_{i}.md"
    return f.read_text().strip() if f.exists() else f"<!-- IMAGE p{pno+1}_{i}: NO TRANSCRIPTION -->"

def table_flow(t, spans, timgs, pno, ctx):
    """Row by row, cell by cell: text lines and images in vertical order (FAQ answers holding images)."""
    ys = cluster([c.y0 for c in t["cells"]] + [t["bbox"].y1])
    blocks = []
    for r in range(len(ys) - 1):
        top, bot = ys[r], ys[r + 1]
        row_spans = [s for s in spans if top - 1 <= (s["bbox"][1] + s["bbox"][3]) / 2 < bot - 1]
        row_imgs = [(i, im) for i, im in timgs if top - 1 <= (im["bbox"][1] + im["bbox"][3]) / 2 < bot - 1]
        label = [s for s in row_spans if s["bbox"][0] < 101]           # Q/A label column
        body = [s for s in row_spans if s["bbox"][0] >= 101]
        pieces = [(l["y0"], "text", l) for l in group_lines(body)] + [(im["bbox"][1], "img", i) for i, im in row_imgs]
        pieces.sort(key=lambda p: p[0])
        text_buf, first = [], True
        lab = fmt(spans_to_runs(sorted(label, key=lambda s: s["bbox"][0]))).strip()
        def flush():
            nonlocal first
            if not text_buf: return
            logical = join_lines(text_buf, lambda p: t["bbox"].x1 - 3.5, ctx=ctx)
            txt = "  \n".join(fmt(x).strip() for x in logical)
            blocks.append((f"**{lab}** " if first and lab else "") + txt); first = False; text_buf.clear()
        for _, kind, v in pieces:
            if kind == "text": text_buf.append(v)
            else: flush(); blocks.append(image_md(pno, v))
        flush()
        if first and lab: blocks.append(f"**{lab}**")
    return blocks

# ---------------------------------------------------------------- page
HIDDEN = {int(k): v for k, v in json.loads((OUT / "hidden_text.json").read_text()).items()}

def page_items(page):
    spans = []
    hidden = HIDDEN.get(page.number + 1, [])
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                if not s["text"].strip(): continue
                if s["bbox"][3] <= HEADER_MAX_Y + 2 or s["bbox"][1] >= FOOTER_MIN_Y: continue
                # text painted under an opaque fill is invisible in the PDF (out/hidden_text.json, hidden.py)
                if any(s["text"].strip() == h[0].strip() and abs(s["bbox"][0] - h[1][0]) < 1 and abs(s["bbox"][1] - h[1][1]) < 1.5 for h in hidden):
                    continue
                spans.append(s)
    # tiny images used as list bullets become a bullet glyph at their position
    for im in page.get_image_info():
        x0, y0, x1, y1 = im["bbox"]
        if 1 <= x1 - x0 <= 8 and 2 <= y1 - y0 <= 12 and HEADER_MAX_Y < y0 < FOOTER_MIN_Y:
            # align the bullet with the text line it introduces (first span to its right overlapping it)
            right = [t for t in spans if t["bbox"][0] > x1 and t["bbox"][0] - x1 < 40
                     and min(t["bbox"][3], y1) - max(t["bbox"][1], y0) > 0]
            by0, by1 = (min(right, key=lambda t: t["bbox"][0])["bbox"][1::2] if right else ((y0 + y1) / 2 - 5.5, (y0 + y1) / 2 + 5.5))
            spans.append({"text": "•", "font": "ArialMT", "size": 10.0, "color": 0, "flags": 0,
                          "bbox": (x0, by0, x1, by1), "synthetic": True})
    items, used = [], set()
    imgs = sorted([im for im in page.get_image_info() if im["bbox"][2] - im["bbox"][0] > 60 and im["bbox"][3] - im["bbox"][1] > 40],
                  key=lambda im: im["bbox"][1])
    in_table = set()
    for t in find_tables(page):
        if len(t["cells"]) == 1: continue  # a lone frame is not a table
        inside = [s for s in spans if t["bbox"].contains(pymupdf.Point(s["bbox"][0] + 2, (s["bbox"][1] + s["bbox"][3]) / 2))]
        used.update(id(s) for s in inside)
        timgs = [(i, im) for i, im in enumerate(imgs) if t["bbox"].contains(pymupdf.Point((im["bbox"][0] + im["bbox"][2]) / 2, (im["bbox"][1] + im["bbox"][3]) / 2))]
        if timgs:   # a table holding images is read row by row so text and images keep their order
            in_table.update(i for i, _ in timgs)
            items.append((t["bbox"].y0, "table_flow", (t, inside, timgs)))
        else:
            items.append((t["bbox"].y0, "table", (t, inside)))
    for i, im in enumerate(imgs):
        if i not in in_table: items.append((im["bbox"][1] + 0.01, "image", i))
    flow = group_lines([s for s in spans if id(s) not in used])
    items += [(y, "line", l) for y, l in two_column_lists(flow)]
    items.sort(key=lambda it: it[0])
    return items

def split_line(l, x):
    left = [s for s in l["spans"] if s["bbox"][0] < x]; right = [s for s in l["spans"] if s["bbox"][0] >= x]
    return [group_lines(part)[0] for part in (left, right) if part]

def two_column_lists(lines):
    """A bulleted list laid out in two columns reads column by column (left column first)."""
    def bullet_starts(l): return l["spans"][0]["text"].strip() == "•"
    expanded = []
    for l in lines:   # split rows that hold a left item and a right item
        cut = next((b["bbox"][0] for a, b in zip(l["spans"], l["spans"][1:])
                    if b["text"].strip() == "•" and b["bbox"][0] > 250 and b["bbox"][0] - a["bbox"][2] > 25), None)
        expanded += split_line(l, cut - 1) if cut else [l]
    expanded.sort(key=lambda l: (l["y0"], l["x0"]))
    out, i = [], 0
    while i < len(expanded):
        j = i
        while j < len(expanded) and (bullet_starts(expanded[j]) or (j > i and expanded[j]["x0"] > 75)):
            j += 1
        run = expanded[i:j]
        xs = [l["x0"] for l in run if bullet_starts(l)]
        if len(run) >= 2 and xs and min(xs) < 150 and max(xs) > 250:
            left = [l for l in run if l["x0"] < 250]; right = [l for l in run if l["x0"] >= 250]
            for l in right: l["col2"] = True
            base = run[0]["y0"]
            out += [(base + k * 0.001, l) for k, l in enumerate(left + right)]
            i = j
        else:
            out.append((expanded[i]["y0"], expanded[i])); i += 1
    return out

def heading_level(l, toc_here, pno, text):
    s = l["spans"][0]
    if not all(is_bold(x) for x in l["spans"]): return None
    if s["size"] >= 17: return 2
    if s["size"] >= 11.5:
        lvl = next((t[0] for t in toc_here if t[1].strip() == text), None)
        return lvl + 1 if lvl else 4
    if s["size"] >= 10.5: return 5
    if s["color"] == GRAY_LABEL and abs(s["size"] - 10) < .3: return 4 if (pno + 1) in CH4 else 5
    return None

def render_page(doc, pno, toc_here, state):
    out, pend_text, pend_code = [], [], []
    ctx = f"p{pno+1}"
    lst = {"idx": None, "stack": [], "text_x": None}   # open list item: out index, bullet x stack, text x
    def end_list(): lst.update(idx=None, stack=[], text_x=None)
    def flush_text():
        if not pend_text: return
        logical = join_lines(pend_text, lambda p: FLOW_RIGHT, ctx=ctx, with_meta=True)
        para = []
        def flush_para():
            if para: out.append("  \n".join(para)); para.clear()
        for runs, first in logical:
            t = fmt(runs).strip()
            if is_bullet_text(runs_text(runs).strip()):
                flush_para()
                bx = first["x0"]
                st = lst["stack"]
                if first.get("col2") and st and st[0] < 150: st[:] = [bx]   # second column = same level
                while st and bx < st[-1] - 6: st.pop()
                if not st or bx > st[-1] + 6: st.append(bx)
                depth = len(st) - 1
                body = re.sub(r"^(•|▪|-|–)\s*", "", t)
                sp = first["spans"]
                lst["text_x"] = sp[1]["bbox"][0] if len(sp) > 1 else bx + 10
                out.append("  " * depth + "- " + body); lst["idx"] = len(out) - 1
            elif lst["idx"] is not None and first["x0"] >= lst["text_x"] - 3 and not para:
                depth = len(lst["stack"]) - 1
                out[lst["idx"]] += "  \n" + "  " * (depth + 1) + t      # continuation inside the item
            else:
                end_list(); para.append(t)
        flush_para()
        pend_text.clear()
    def flush_code():
        if pend_code: out.append(code_block(pend_code, ctx)); pend_code.clear()
    for y, kind, payload in page_items(doc[pno]):
        if kind == "table":
            flush_text(); flush_code(); end_list()
            md, orphans = table_md(*payload, ctx=ctx)
            if md: out.append(md)
            if orphans: out.append(fmt(spans_to_runs(sorted(orphans, key=lambda s: (s["bbox"][1], s["bbox"][0])))))
            continue
        if kind == "table_flow":
            flush_text(); flush_code(); end_list()
            out.extend(table_flow(*payload, pno=pno, ctx=ctx))
            continue
        if kind == "image":
            flush_text(); flush_code(); end_list()
            f = OCR / f"p{pno+1}_{payload}.md"
            out.append(f.read_text().strip() if f.exists() else f"<!-- IMAGE p{pno+1}_{payload}: NO TRANSCRIPTION -->")
            continue
        l = payload
        if all(is_code(s) for s in l["spans"]):
            flush_text(); end_list(); pend_code.append(l); continue
        flush_code()
        text = runs_text(l["runs"]).strip()
        lvl = heading_level(l, toc_here, pno, text)
        if lvl:
            flush_text(); end_list()
            if text.startswith("Chapter 3"): state["chapter"] = 3
            elif text.startswith(("Chapter 4", "Appendix")): state["chapter"] = 9
            anchor = ""
            if lvl == 4 and (pno + 1) in CH4:
                anchor = f'<a id="type-{slug(text)}"></a>\n'; state["types"].append((text, pno + 1))
            elif state["chapter"] == 3 and any(t[1].strip() == text and t[0] == 3 for t in toc_here):
                anchor = f'<a id="msg-{slug(text)}"></a>\n'
            elif lvl <= 3:
                anchor = f'<a id="sec-{slug(text)}"></a>\n'
            out.append(anchor + "#" * lvl + " " + esc(text))
            continue
        # a new paragraph starts when vertical gap is large or indentation changes
        if pend_text:
            p = pend_text[-1]
            if l["y0"] - p["y1"] > l["size"] * 0.9: flush_text()
        pend_text.append(l)
    flush_text(); flush_code()
    return out

def printed_label(page):
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                if s["bbox"][1] > 698 and s["bbox"][0] > 500 and s["text"].strip(): return s["text"].strip()
    return ""

def build_vocab(doc):
    for p in doc:
        for w in re.findall(r"[A-Za-z0-9]+", p.get_text()):
            STANDALONE[w] += 1
    VOCAB.update(w for w in STANDALONE if len(w) >= 6)
    for p in doc:
        for line in p.get_text().split("\n"):
            toks = re.findall(r"[A-Za-z0-9]+", line)
            NOT_AT_END.update(toks[:-1]); NOT_AT_START.update(toks[1:])
    for p in doc:
        VOCAB_W.update(w for w in re.findall(r"\w+", p.get_text()) if "_" in w and len(w) >= 5)

def main(first=1, last=None):
    global CH3, CH4
    doc = pymupdf.open(pdf_path())
    CH3, CH4 = part(doc.get_toc(), doc.page_count, "Chapter 3"), part(doc.get_toc(), doc.page_count, "Chapter 4")
    last = last or doc.page_count
    toc_by_page = collections.defaultdict(list)
    for lvl, title, pg in doc.get_toc(): toc_by_page[pg].append((lvl, title))
    build_vocab(doc)
    state = {"chapter": 3 if CH3.start < first < CH4.start else 0, "types": []}
    body, labels = [], {}
    for pno in range(first - 1, last):
        label = printed_label(doc[pno]); labels[pno + 1] = label
        body.append(f'<!-- page {pno+1} | printed {label} -->\n<a id="page-{label}"></a>' if label else f"<!-- page {pno+1} -->")
        body.extend(render_page(doc, pno, toc_by_page.get(pno + 1, []), state))
    out = OUT; out.mkdir(parents=True, exist_ok=True)
    (out / "body.md").write_text("\n\n".join(body) + "\n")
    imprint = re.search(r"Message Reference, Release (\S+), (.+?), (\S+-C)", doc[1].get_text())
    if not imprint: sys.exit("page 2: imprint line 'XP2 APEX Suite, Message Reference, Release X, <date>, <doc number>' not found")
    release = {"release": imprint.group(1), "date": re.sub(r",\s*", ", ", imprint.group(2)), "doc_number": imprint.group(3),
               "pages": doc.page_count}
    (out / "meta.json").write_text(json.dumps({"toc": doc.get_toc(), "types": state["types"], "labels": labels, "release": release}))
    (out / "joins.tsv").write_text("\n".join("\t".join(j) for j in JOINS) + "\n")

if __name__ == "__main__":
    main(*[int(x) for x in sys.argv[1:]])
