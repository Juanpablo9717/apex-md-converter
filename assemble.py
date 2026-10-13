"""out/body.md + out/meta.json -> final single Markdown with an AI-oriented index on top.

- de-duplicates anchors (2nd occurrence -> <id>-2, ...)
- turns every `"Name" on page N` cross-reference (outside code) into a link to the type/message/section
  anchor when one with that name lives on printed page N, else to the page anchor
- builds: how-to-search, TOC, message index (from the PDF's own Message Summary table), messages by
  service group, type index, error-code index, FAQ question index
Writes out/final.md and out/assemble_report.json.
"""
import codeblocks, json, re, collections

from common import OUT, WORK, part

body = (OUT / "body.md").read_text()
meta = json.loads((OUT / "meta.json").read_text())
rel = meta["release"]
APP_B = part(meta["toc"], rel["pages"], "Appendix B")
APP_C = part(meta["toc"], rel["pages"], "Appendix C")
# release-specific verification summary for the header, written after the audits of that release
VERIFIED = (WORK / "header_verification.md").read_text().strip() if (WORK / "header_verification.md").exists() else \
    "> Verification: see the conversion kit (apex-md-converter) report for this release."
labels = {int(k): v for k, v in meta["labels"].items()}
slug = lambda s: re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")
report = {}

# ---------------------------------------------------------------- pass 1: anchors, page tracking
lines = body.split("\n")
seen = collections.Counter()
anchors = {}            # id -> dict(text, phys, printed, kind)
cur_phys, cur_printed = 0, ""
pending_anchor = None
group = None
cur_msg = None; want_group = False
toc_l2 = {t[2]: t[1] for t in meta["toc"] if t[0] == 2}
msg_groups = {}
for i, l in enumerate(lines):
    m = re.match(r"<!-- page (\d+)(?: \| printed (\S*))? -->", l)
    if m:
        cur_phys, cur_printed = int(m.group(1)), m.group(2) or ""; continue
    m = re.fullmatch(r'<a id="([^"]+)"></a>', l)
    if m and not m.group(1).startswith("page-"):
        aid = m.group(1); seen[aid] += 1
        if seen[aid] > 1:
            aid = f"{aid}-{seen[aid]}"; lines[i] = f'<a id="{aid}"></a>'
        pending_anchor = aid; continue
    if pending_anchor and l.startswith("#"):
        text = re.sub(r"^#+ ", "", l).replace("\\", "")
        kind = pending_anchor.split("-")[0]
        if kind == "sec" and text in toc_l2.values(): group = text
        anchors[pending_anchor] = {"text": text, "phys": cur_phys, "printed": cur_printed, "kind": kind,
                                   "group": group if kind == "msg" else None}
        pending_anchor = None
        if kind == "msg": cur_msg = aid_last = list(anchors)[-1]
        continue
    if re.match(r"^##### Service (Group|Class)\s*$", l):
        want_group = True; continue
    if want_group and l.strip() and cur_msg:
        anchors[cur_msg]["svc"] = l.strip().replace("\\", ""); want_group = False
report["anchors"] = len(anchors)
report["dedup_suffixed"] = {k: v for k, v in seen.items() if v > 1}
page_anchor = set(labels.values())

by_name_page = collections.defaultdict(list)
for aid, a in anchors.items():
    by_name_page[(slug(a["text"]), a["printed"])].append(aid)

# ---------------------------------------------------------------- pass 2: links outside code
_sec = re.split(r"^<!-- page \d+ \| printed (\S*) -->$", body, flags=re.M)
PAGE_TEXT = {_sec[k]: _sec[k + 1].replace("\\", "") for k in range(1, len(_sec), 2)}
REF = re.compile(r'(?<!\[)"([^"\n]{1,120}?)" on page (\d+)')
in_code = False
linked = collections.Counter()
def link(m):
    name, page = m.group(1), m.group(2)
    cands = by_name_page.get((slug(name.replace("\\", "")), page), [])
    if cands: target, how = cands[0], "anchor"
    elif page in page_anchor and re.sub(r"\s*\(continued\)$", "", name.replace("\\", "").strip()) in PAGE_TEXT.get(page, ""):
        target, how = f"page-{page}", "page"     # the named thing is on that page, just not as a heading
    else:
        linked["unresolved"] += 1; return m.group(0)
    linked[how] += 1
    return f'[{m.group(0)}](#{target})'
for i, l in enumerate(lines):
    if l.startswith("```"): in_code = not in_code; continue
    if in_code or l.startswith("<"): continue
    lines[i] = REF.sub(link, l)
report["links"] = dict(linked)
body = "\n".join(lines)

# ---------------------------------------------------------------- indexes
def ln(aid): return f"[{anchors[aid]['text']}](#{aid})"
def pg(p): return f"[p. {p}](#page-{p})" if p in page_anchor else f"p. {p}"

# message summary table (PDF pages 16-45) -> name, description, service, page
summary = []
sec = re.split(r"^<!-- page (\d+)[^>]*-->$", body, flags=re.M)
pages = {int(sec[k]): sec[k + 1] for k in range(1, len(sec), 2)}
for p in range(16, 46):
    for row in pages.get(p, "").split("\n"):
        if not row.startswith("| ") or row.startswith("| **"): continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", row)[1:-1]]
        if len(cells) == 4 and re.fullmatch(r"\d+", re.sub(r"\[|\]\(.*?\)", "", cells[3]) or "x"):
            summary.append(cells)
msg_by_name = collections.defaultdict(list)
for aid, a in anchors.items():
    if a["kind"] == "msg": msg_by_name[a["text"].replace(" (Retired)", "").strip()].append(aid)
idx = ["| Message | What it does (from the PDF's Message Summary) | APEX Service (Table 1) | Service Group (on the message's own page) | Page | Go to |", "|---|---|---|---|---|---|"]
unmatched = []
for name, desc, svc, page in summary:
    base = re.sub(r"\s*\(Retired\)", "", name).strip()
    targets = msg_by_name.get(base, [])
    pnum = re.sub(r"\[|\]\(.*?\)", "", page)
    if not targets:  # name broken in the PDF table (wrapped across pages, or a bare page number): resolve by page
        targets = [a for a, v in anchors.items() if v["kind"] == "msg" and v["printed"] == pnum and v["text"].startswith(base[:12])] \
            or [a for a, v in anchors.items() if v["kind"] == "msg" and v["printed"] == pnum]
        if targets: name = f"{name} (→ {anchors[targets[0]]['text']})"
        else: unmatched.append(name)
    go = " · ".join(f"[{anchors[t]['group'] or 'section'}](#{t})" for t in targets) or "—"
    own = " · ".join(dict.fromkeys(anchors[t].get("svc", "—") for t in targets)) or "—"
    if own != "—" and re.sub(r"\s", "", own) != re.sub(r"\s", "", svc): own = f"**{own}** (differs from Table 1)"
    idx.append(f"| {name} | {desc} | {svc} | {own} | {pg(page)} | {go} |")
report["summary_rows"] = len(summary); report["summary_unmatched"] = unmatched
in_summary = {re.sub(r"\s*\(Retired\)", "", r[0]).strip() for r in summary} | {m for m in re.findall(r"\(→ ([^)]+)\)", "\n".join(idx))}
extra_msgs = sorted(n for n in msg_by_name if n not in in_summary)
report["messages_not_in_summary"] = extra_msgs

groups = collections.defaultdict(list)
for aid, a in anchors.items():
    if a["kind"] == "msg": groups[a["group"]].append(aid)
by_group = []
for g, aids in groups.items():
    by_group.append(f"**{g}** ({len(aids)}): " + " · ".join(ln(a) for a in aids))

types = sorted((a["text"], aid) for aid, a in anchors.items() if a["kind"] == "type")
type_idx = " · ".join(f"[{t}](#{aid})" for t, aid in types)

errors = []
for p in APP_B:
    codes = re.findall(r"^\| (\d{5}) \|", pages.get(p, ""), flags=re.M)
    if codes: errors.append(f"| {codes[0]} – {codes[-1]} | {len(codes)} | {pg(labels[p])} |")
faq = []
for p in APP_C:
    for q, text in re.findall(r"^\| (Q\d+\.?) \| (.+?) \|$", pages.get(p, ""), flags=re.M):
        faq.append(f"- {q} {text} — {pg(labels[p])}")

toc = []
for lvl, title, phys in meta["toc"]:
    if lvl > 2: continue
    aid = f"sec-{slug(title)}"
    target = f"#{aid}" if aid in anchors else f"#page-{labels.get(phys, '')}"
    toc.append("  " * (lvl - 1) + f"- [{title}]({target}) — PDF page {phys}, printed {labels.get(phys, '')}")

header = f"""# XP2 APEX Suite, Message Reference — Release {rel["release"]} ({rel["date"]})

> Markdown edition of the Fiserv PDF `APEX_Message_Reference_{rel["release"].replace(".", "_")}.pdf` ({rel["doc_number"]}, {rel["pages"]:,} pages).
> FISERV CONFIDENTIAL | Intended Only for XP2 Clients. Converted page by page; every PDF page is kept, in order.
{VERIFIED}

## How to find things in this file (read this first)

- **Size:** ~{len(body)//1_000_000} MB / ~{len(body.split()):,} words. Do not read it whole: search, then read the section.
- **Pages:** each PDF page starts with `<!-- page <pdf page> | printed <printed page> -->` and `<a id="page-<printed page>"></a>`.
  Cross-references in the text ("X" on page N) use the **printed** page number and are links.
- **Messages (Chapter 3):** `<a id="msg-<MessageName>"></a>` then `#### <MessageName>`. Search `id="msg-CashToClose"`.
  A message documented in several service groups has `msg-<Name>`, `msg-<Name>-2`, …
  Inside a message, subsections are `##### Description`, `##### Service Group`, `##### Action` (SOAP action URL),
  `##### Request Schema` / `##### Response Schema` (XSD), `##### Schema Elements` (field table), `##### Example Request XML`, `##### Example Response XML`
  (labels exactly as in the PDF; variants exist, e.g. `##### Service Class` instead of Service Group, "ExampleResponse XML", "Types").
  Several messages exist in numbered versions (e.g. LendingTermsUpdate, LendingTermsUpdate2008, LendingTermsUpdate2): fields differ per version.
- **Types (Chapter 4):** `<a id="type-<TypeName>"></a>` then `#### <TypeName>`: the XSD plus its Element/Type/Max/Description table.
- **Field tables:** columns Element | Type | Max | Description. `↳` marks nesting depth under the parent element
  (`↳` = child, `↳↳` = grandchild). `<br>` is a line break inside a cell.
  **Required request elements are in bold** (`**MemberId**`), as the PDF states. Type abbreviations, per the PDF's own legend
  (Chapter 3 intro, [printed page 4](#page-4)): Boolean B, Date DT, DateTime DtTm, Decimal Dec, Double D, Enumerated Enum,
  Integer Int, Long L, Short Sh, String Str (tables also use Lg, Dt and Type as written in the PDF).
- **XML/XSD:** fenced ```xml blocks. Lines the PDF wrapped at the page margin were re-joined, and a block the PDF continued
  on the next page is one block, so XML is whole. Blocks are re-indented 4 spaces per element level, as Prettier prints XML (opening tags with long
  `xmlns` lists get one attribute per line); only whitespace differs from the PDF.
  A block that spans pages belongs to the page where it starts; the page markers it spanned follow right after it.
- **Errors (Appendix B):** search the 5-digit code, e.g. `| 00686 |`.
- **Images:** content of images is transcribed in place, marked `<!-- image p<page>_<n> ... -->`.
- **Which page is a search hit on?** `awk -v L=<line> 'NR<=L && /^<!-- page /{{p=$0}} NR==L{{print p}}' <this file>`
  (the nearest `<!-- page` line above the hit).

## Table of contents

{chr(10).join(toc)}

## Message index (A–Z, from the PDF's "Table 1: APEX Messages")

{chr(10).join(idx)}

{"Messages documented in Chapter 3 but not listed in Table 1: " + ", ".join(f"[{n}](#{msg_by_name[n][0]})" for n in extra_msgs) if extra_msgs else ""}

## Messages by service group

{chr(10).join(f"- {g}" for g in by_group)}

## Type index (Chapter 4, A–Z)

{type_idx}

## Error code index (Appendix B)

| Codes | Count | Page |
|---|---|---|
{chr(10).join(errors)}

## FAQ index (Appendix C)

{chr(10).join(faq)}

---

"""
(OUT / "final_paged.md").write_text(header + body)      # before the whitespace-only pass; check_codeblocks.py compares
body = codeblocks.reindent_xml(codeblocks.merge_page_splits(body))
(OUT / "final.md").write_text(header + body)
(OUT / "assemble_report.json").write_text(json.dumps(report, indent=1))
print(json.dumps({k: (v if not isinstance(v, list) or len(v) < 15 else f"{len(v)} items") for k, v in report.items()}, indent=1))
