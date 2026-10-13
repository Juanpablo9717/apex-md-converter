"""Readability pass over the assembled Markdown, whitespace-only:
1. merge_page_splits: a ```xml block that the PDF continued on the next page (only page markers between the two
   fences) becomes one block; the page markers it spanned are moved right after the closing fence.
2. reindent_xml: every ```xml block is re-indented 4 spaces per tag depth; an opening tag that declares two or more
   namespaces (xmlns) and is longer than 100 chars gets one attribute per line. Characters other than whitespace never change.
"""
import re

SEP_LINE = re.compile(r'^(\s*|<!-- page \d+ \| printed \S* -->|<a id="page-[^"]+"></a>)$')

def merge_page_splits(md):
    lines = md.split("\n")
    out, moved, in_code, i = [], [], False, 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("```"):
            if in_code and l == "```":
                j = i + 1
                while j < len(lines) and SEP_LINE.match(lines[j]): j += 1
                seps = lines[i + 1:j]
                if j < len(lines) and lines[j] == "```xml" and any(s.startswith("<!-- page") for s in seps):
                    moved += [s for s in seps if s.strip()]
                    i = j + 1; continue                       # stay inside the block
                out.append(l); in_code = False
                if moved: out += [""] + moved; moved = []
                i += 1; continue
            in_code = True
        out.append(l); i += 1
    return "\n".join(out)

TOKEN = re.compile(r'<!--.*?-->|<!\[CDATA\[.*?\]\]>|<\?.*?\?>|<!.*?>|</|<(?=[A-Za-z_])|"[^"]*"|\'[^\']*\'|/>|>', re.S)

def _depth_walk(lines):
    """Yield (stripped line, indent) with raw depth (can go negative for fragments)."""
    depth, in_tag = 0, None          # in_tag: 'open' | 'close' while inside <...> spanning lines
    res = []
    for raw in lines:
        s = raw.strip()
        if not s: res.append((s, None)); continue
        if in_tag: ind = depth + 1
        elif s.startswith("</"): ind = depth - 1
        else: ind = depth
        for m in TOKEN.finditer(s):
            t = m.group()
            if t[0] in "\"'":
                continue                                   # quoted (only meaningful inside a tag)
            if t.startswith(("<!--", "<![CDATA[", "<?", "<!")) and len(t) > 1 and t != "</": continue
            if t == "</": in_tag = "close"
            elif t == "<": in_tag = "open"
            elif t == "/>" and in_tag: in_tag = None
            elif t == ">" and in_tag:
                depth += 1 if in_tag == "open" else -1
                in_tag = None
        res.append((s, ind))
    return res

def _split_attrs(s, ind):
    """'<tag a="1" xmlns:b="2">rest' -> tag line + one attribute per line (only whitespace between attributes changes)."""
    if len(s) <= 100 or len(re.findall(r"\sxmlns[:=]", s)) < 2 or not s.startswith("<") or s.startswith(("</", "<?", "<!")): return [(s, ind)]
    parts, cur, q, end = [], "", None, None
    for k, ch in enumerate(s):
        if q:
            cur += ch
            if ch == q: q = None
            continue
        if ch in "\"'": q = ch; cur += ch; continue
        if ch == ">":
            end = k - 1 if cur.endswith("/") else k        # s[end:] is '>' or '/>' plus whatever follows
            cur = cur[:end - k] if end < k else cur
            break
        if ch.isspace():
            if cur: parts.append(cur); cur = ""
            continue
        cur += ch
    if end is None or len(parts) < 2: return [(s, ind)]
    parts.append(cur + s[end:])
    # as Prettier (VS Code) prints it: first attribute on the tag line, the rest one per line, '>' on the last one
    return [(parts[0] + " " + parts[1], ind)] + [(p, ind + 1) for p in parts[2:]]

def reindent_block(text):
    walked = _depth_walk(text.split("\n"))
    inds = [i for _, i in walked if i is not None]
    base = min(inds) if inds else 0
    out = []
    for s, ind in walked:
        if ind is None: continue                           # blank lines inside a block: whitespace only
        for t, i in _split_attrs(s, ind - base): out.append("    " * i + t)
    return "\n".join(out)

def reindent_xml(md):
    return re.sub(r"^```xml\n(.*?)\n```$", lambda m: "```xml\n" + reindent_block(m.group(1)) + "\n```", md, flags=re.M | re.S)

def nonspace(s): return re.sub(r"\s+", "", s)

if __name__ == "__main__":
    src = '<a xmlns:x="http://example.com/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" xmlns:y="http://example.com/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb">\n<b>\n   <c x="1>2">t u</c>\n<d/>\n</b>\n</a>'
    got = reindent_block(src)
    assert got == ('<a xmlns:x="http://example.com/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"\n'
                   '    xmlns:y="http://example.com/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb">\n'
                   '    <b>\n        <c x="1>2">t u</c>\n        <d/>\n    </b>\n</a>'), got
    sc = '<e xmlns:x="http://example.com/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" xmlns:y="http://example.com/bbbbbbbbbbbbbbbbbbbbbbbbb"/>'
    assert reindent_block(sc) == '<e xmlns:x="http://example.com/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"\n    xmlns:y="http://example.com/bbbbbbbbbbbbbbbbbbbbbbbbb"/>', reindent_block(sc)
    assert reindent_block("    </s:sequence>\n  </s:complexType>") == "    </s:sequence>\n</s:complexType>"
    md = "x\n```xml\n<a>\n```\n\n<!-- page 2 | printed 1 -->\n<a id=\"page-1\"></a>\n\n```xml\n</a>\n```\ny"
    assert merge_page_splits(md) == "x\n```xml\n<a>\n</a>\n```\n\n<!-- page 2 | printed 1 -->\n<a id=\"page-1\"></a>\ny", merge_page_splits(md)
    print("ok")
