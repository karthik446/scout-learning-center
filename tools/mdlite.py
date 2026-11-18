#!/usr/bin/env python3
"""mdlite: the Markdown subset the AI engineering track is written in, rendered to HTML (standard library only).

Supported: ATX headings (# to ######, exactly one #), paragraphs, **strong**, *emphasis*, `code spans`, [links](dest)
whose destination is https:// or a relative target the caller resolves, `-` and `1.` lists nested by indentation (one
line per item), ``` fences with a language (`mermaid` renders as <pre class="mermaid">, every other language as a code
block the shipped highlighter styles when it knows the language and leaves plain otherwise), > blockquotes holding
paragraphs and lists, | tables | with a |---| separator row, --- rules, and backslash escapes of punctuation.

Everything else raises MdliteError instead of rendering something other than what was written: raw HTML and
entities, images, reference links, autolinks and bare URLs in prose, _underscore emphasis_, indented code, setext
headings, hard line breaks, table alignment colons, nested blockquotes, continuation lines of list items, tabs, an
unmatched delimiter. All text is HTML-escaped; code points above U+00FF are written as numeric character references
(the glyph policy of build.py allows Latin-1 and a few typographic marks only).

    render(text, link=resolver, code_langs=HLJS_LANGS) -> Rendered

`link(dest)` receives every destination that is not https:// (relative paths and #fragments) and returns the href to
write, or raises MdliteError for one it does not know.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Callable, Mapping


class MdliteError(Exception):
    pass


PUNCT = set("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")
FENCE = re.compile(r"^```([A-Za-z0-9_+-]*)\s*$")
FENCE_CLOSE = re.compile(r"^```\s*$")
ATX = re.compile(r"^(#{1,6})[ ]+(.*?)\s*$")
HR = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})\s*$")
LIST = re.compile(r"^( *)(-|\d{1,3}\.) +(\S.*)$")
LIST_EMPTY = re.compile(r"^( *)(-|\d{1,3}\.)\s*$")
SEPARATOR_CELL = re.compile(r"^:?-+:?$")
ENTITY = re.compile(r"&(?:#\d+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);")
BARE_URL = re.compile(r"(?i)\b(?:https?|ftp)://")
UNDERSCORE_EMPHASIS = re.compile(r"(?<!\w)_{1,2}[^\s_][^_]*?_{1,2}(?!\w)")
SLUG_DROP = re.compile(r"[^\w\- ]")


def esc(s: str) -> str:
    """HTML-escape; code points above U+00FF become numeric references."""
    out = html.escape(s, quote=True)
    if out.isascii():
        return out
    return "".join(c if ord(c) < 0x100 else f"&#x{ord(c):X};" for c in out)


@dataclass
class Block:
    kind: str   # heading, p, code, mermaid, quote, list, table, hr
    html: str


@dataclass
class Rendered:
    blocks: list[Block]
    title: str | None                        # text of the one `#` heading, None when there is none
    headings: list[tuple[int, str, str]]     # (level, id, text) in document order
    links: list[str]                         # every link destination as written
    langs: list[str]                         # fence languages in order of first use

    @property
    def html(self) -> str:
        return "\n".join(b.html for b in self.blocks)

    @property
    def mermaid(self) -> bool:
        return "mermaid" in self.langs


class _Parser:
    def __init__(self, link: Callable[[str], str], code_langs: Mapping[str, str]) -> None:
        self.link = link
        self.code_langs = code_langs
        self.headings: list[tuple[int, str, str]] = []
        self.slugs: dict[str, int] = {}
        self.links: list[str] = []
        self.langs: list[str] = []
        self.title: str | None = None
        self.line = 0   # the source line being read, for messages

    def fail(self, msg: str) -> MdliteError:
        return MdliteError(f"line {self.line}: {msg}")

    # --- blocks -----------------------------------------------------------------------------------------------------
    @staticmethod
    def starts_block(l: str) -> bool:
        return bool(FENCE.match(l) or ATX.match(l) or l.startswith((">", "|")) or HR.match(l) or LIST.match(l))

    def blocks(self, lines: list[str], first_line: int, *, in_quote: bool = False) -> list[Block]:
        out: list[Block] = []
        para: list[str] = []
        i = 0

        def flush() -> None:
            if para:
                self.line = first_line + i - len(para)   # the paragraph's first line, for messages
                out.append(Block("p", f"<p>{self.inline(chr(10).join(para))}</p>"))
                para.clear()

        while i < len(lines):
            l = lines[i]
            self.line = first_line + i
            if "\t" in l:
                raise self.fail("tab character")
            if l.strip() == "":
                flush()
                i += 1
                continue
            m = FENCE.match(l)
            if m:
                flush()
                lang = m.group(1) or "text"
                j = i + 1
                while j < len(lines) and not FENCE_CLOSE.match(lines[j]):
                    j += 1
                if j >= len(lines):
                    raise self.fail("code fence is never closed")
                out.append(self.code(lang, "\n".join(lines[i + 1:j])))
                i = j + 1
                continue
            m = ATX.match(l)
            if m:
                flush()
                out.append(self.heading(len(m.group(1)), m.group(2)))
                i += 1
                continue
            if l.startswith(">"):
                flush()
                if in_quote:
                    raise self.fail("nested blockquote")
                j = i
                inner: list[str] = []
                while j < len(lines) and lines[j].startswith(">"):
                    inner.append(lines[j][2:] if lines[j].startswith("> ") else lines[j][1:])
                    j += 1
                if j < len(lines) and lines[j].strip() and not self.starts_block(lines[j]):
                    self.line = first_line + j
                    raise self.fail("continuation line of a blockquote without '>'")
                body = self.blocks(inner, first_line + i, in_quote=True)
                out.append(Block("quote", "<blockquote>\n" + "\n".join(b.html for b in body) + "\n</blockquote>"))
                i = j
                continue
            if l.startswith("|"):
                if para:
                    raise self.fail("a table needs a blank line before it")
                j = i
                while j < len(lines) and lines[j].startswith("|"):
                    j += 1
                out.append(self.table(lines[i:j]))
                i = j
                continue
            if HR.match(l):
                if para:
                    raise self.fail("a rule right after text (setext heading or rule: write a blank line first)")
                out.append(Block("hr", "<hr>"))
                i += 1
                continue
            m = LIST.match(l)
            if m:
                if para and m.group(2) not in ("-", "1."):
                    raise self.fail("an ordered list that does not start at 1 cannot follow text without a blank line")
                flush()
                j = i
                rows: list[tuple[int, str, str]] = []
                while j < len(lines) and LIST.match(lines[j]):
                    mm = LIST.match(lines[j])
                    self.line = first_line + j
                    rows.append((len(mm.group(1)), mm.group(2), self.breaks(mm.group(3))))
                    j += 1
                if j < len(lines) and lines[j].strip() and not self.starts_block(lines[j]):
                    self.line = first_line + j
                    raise self.fail("continuation line of a list item (one line per item)")
                self.line = first_line + i
                out.append(Block("list", self.list_tree(rows)))
                i = j
                continue
            if LIST_EMPTY.match(l):
                raise self.fail("empty list item")
            if l.startswith("#"):
                raise self.fail("'#' without a space is not a heading")
            if l.startswith("    "):
                raise self.fail("indented code block (use a ``` fence)")
            para.append(self.breaks(l).strip())
            i += 1
        flush()
        return out

    def breaks(self, l: str) -> str:
        if l.endswith("  ") or l.endswith("\\"):
            raise self.fail("hard line break")
        return l

    def code(self, lang: str, body: str) -> Block:
        if lang not in self.langs:
            self.langs.append(lang)
        if lang == "mermaid":
            return Block("mermaid", f'<div class="mermaid-wrap"><pre class="mermaid">{esc(body)}</pre></div>')
        cls = self.code_langs.get(lang.lower(), "plaintext")
        return Block("code", f'<span class="code-lang">{esc(lang)}</span>'
                             f'<pre><code class="language-{cls}" data-lang="{esc(cls)}">{esc(body)}</code></pre>')

    def heading(self, level: int, text: str) -> Block:
        inner = self.inline(text)
        plain = html.unescape(re.sub(r"<[^>]+>", "", inner))
        if level == 1:
            if self.title is not None:
                raise self.fail("a second '#' heading")
            self.title = plain
        slug = SLUG_DROP.sub("", plain.lower()).replace(" ", "-")
        n = self.slugs.get(slug, 0)
        self.slugs[slug] = n + 1
        ident = slug if n == 0 else f"{slug}-{n}"
        self.headings.append((level, ident, plain))
        return Block("heading", f'<h{level} id="{esc(ident)}">{inner}</h{level}>')

    def split_row(self, l: str) -> list[str]:
        l = l.rstrip()
        if not l.endswith("|") or l.endswith("\\|"):
            raise self.fail("table row does not end with '|'")
        cells: list[str] = []
        cur: list[str] = []
        k = 0
        while k < len(l):
            c = l[k]
            if c == "\\" and k + 1 < len(l) and l[k + 1] == "|":
                cur.append("|")
                k += 2
                continue
            if c == "|":
                cells.append("".join(cur).strip())
                cur = []
            else:
                cur.append(c)
            k += 1
        return cells[1:]   # the text before the first '|' is empty (the row starts with it); the last '|' closes the row

    def table(self, rows: list[str]) -> Block:
        if len(rows) < 2:
            raise self.fail("table without a separator row")
        head = self.split_row(rows[0])
        self.line += 1
        sep = self.split_row(rows[1])
        if len(sep) != len(head) or not all(SEPARATOR_CELL.match(c) for c in sep):
            raise self.fail("table separator row does not match the header")
        if any(":" in c for c in sep):
            raise self.fail("table alignment colons are not supported")
        heads = [self.inline(c) for c in head]
        cols = [SLUG_DROP.sub("", html.unescape(re.sub(r"<[^>]+>", "", h)).lower()).replace(" ", "-") for h in heads]
        body: list[str] = []
        for k, r in enumerate(rows[2:], 2):
            self.line += 1
            cells = self.split_row(r)
            if len(cells) != len(head):
                raise self.fail(f"table row has {len(cells)} cells, the header {len(head)} (an unescaped '|' inside a cell?)")
            body.append("<tr>" + "".join(f'<td data-col="{esc(col)}">{self.inline(c)}</td>' for col, c in zip(cols, cells)) + "</tr>")
        thead = "".join(f'<th scope="col">{h}</th>' for h in heads)
        return Block("table", '<div class="table-scroll" role="region" tabindex="0" aria-label="Table"><table>'
                              f"<thead><tr>{thead}</tr></thead><tbody>{''.join(body)}</tbody></table></div>")

    def list_tree(self, rows: list[tuple[int, str, str]]) -> str:
        root: dict = {"kind": None, "indent": -1, "items": [], "start": 1}
        stack = [root]
        for indent, marker, text in rows:
            kind = "ol" if marker[0].isdigit() else "ul"
            popped = False
            while len(stack) > 1 and indent < stack[-1]["indent"]:
                stack.pop()
                popped = True
            top = stack[-1]
            if indent > top["indent"]:
                if popped or (top is root and root["items"]):
                    raise self.fail("list indentation does not match an open list")
                node = {"kind": kind, "indent": indent, "items": [], "start": int(marker[:-1]) if kind == "ol" else 1}
                if top is root:
                    root["items"].append(node)
                else:
                    top["items"][-1]["children"].append(node)
                stack.append(node)
                top = node
            elif indent != top["indent"]:
                raise self.fail("list indentation does not match an open list")
            if top["kind"] != kind:
                raise self.fail("list marker changes inside one list")
            top["items"].append({"text": text, "children": []})

        def render(node: dict) -> str:
            tag = node["kind"]
            start = f' start="{node["start"]}"' if tag == "ol" and node["start"] != 1 else ""
            items = "".join(f"<li>{self.inline(it['text'])}{''.join(render(ch) for ch in it['children'])}</li>" for it in node["items"])
            return f"<{tag}{start}>{items}</{tag}>"

        return render(root["items"][0])

    # --- inlines ----------------------------------------------------------------------------------------------------
    def text(self, s: str) -> str:
        if BARE_URL.search(s):
            raise self.fail(f"bare URL in prose: {s.strip()[:60]!r} (write it as a [link](url) or in a code span)")
        if UNDERSCORE_EMPHASIS.search(s):
            raise self.fail("underscore emphasis is not supported (use * and **)")
        return esc(s)

    def inline(self, s: str) -> str:
        out, i = self.parse_inline(s, 0, None, False)
        return out

    def parse_inline(self, s: str, i: int, closer: str | None, in_link: bool) -> tuple[str, int]:
        out: list[str] = []
        buf: list[str] = []

        def flush() -> None:
            if buf:
                out.append(self.text("".join(buf)))
                buf.clear()

        n = len(s)
        while i < n:
            c = s[i]
            if c == "\\" and i + 1 < n and s[i + 1] in PUNCT:
                buf.append(s[i + 1])
                i += 2
                continue
            if c == "`":
                k = i
                while k < n and s[k] == "`":
                    k += 1
                run = k - i
                j = k
                while True:
                    j = s.find("`" * run, j)
                    if j < 0:
                        raise self.fail("unmatched backtick")
                    e = j + run
                    if e < n and s[e] == "`":
                        while e < n and s[e] == "`":
                            e += 1
                        j = e
                        continue
                    break
                content = s[k:j].replace("\n", " ")
                if len(content) > 2 and content[0] == " " and content[-1] == " " and content.strip():
                    content = content[1:-1]
                flush()
                out.append(f"<code>{esc(content)}</code>")
                i = j + run
                continue
            if closer and s.startswith(closer, i) and self.can_close(s, i, closer):
                flush()
                return "".join(out), i + len(closer)
            if s.startswith("***", i):
                raise self.fail("a run of three asterisks")
            if s.startswith("**", i) and self.can_open(s, i, 2):
                flush()
                inner, i = self.parse_inline(s, i + 2, "**", in_link)
                out.append(f"<strong>{inner}</strong>")
                continue
            if c == "*" and self.can_open(s, i, 1):
                flush()
                inner, i = self.parse_inline(s, i + 1, "*", in_link)
                out.append(f"<em>{inner}</em>")
                continue
            if c == "!" and i + 1 < n and s[i + 1] == "[":
                raise self.fail("images are not supported")
            if c == "[":
                if in_link:
                    raise self.fail("a link inside a link")
                inner, j = self.parse_inline(s, i + 1, "]", True)
                if j < n and s[j] == "(":
                    dest, j = self.destination(s, j + 1)
                    flush()
                    out.append(self.anchor(dest, inner))
                    i = j
                    continue
                if j < n and s[j] == "[":
                    raise self.fail("reference-style links are not supported")
                flush()
                out.append("[" + inner + "]")
                i = j
                continue
            if c == "<" and i + 1 < n and (s[i + 1].isalpha() or s[i + 1] in "/!?"):
                raise self.fail(f"raw HTML or autolink: {s[i:i + 20]!r}")
            if c == "&" and ENTITY.match(s, i):
                raise self.fail(f"HTML entity {ENTITY.match(s, i).group(0)!r} (write the character itself)")
            buf.append(c)
            i += 1
        if closer:
            raise self.fail(f"unmatched {closer!r}")
        flush()
        return "".join(out), i

    @staticmethod
    def can_open(s: str, i: int, run: int) -> bool:
        j = i + run
        return j < len(s) and not s[j].isspace() and s[j] != "*" and (i == 0 or not s[i - 1].isalnum() or run == 1)

    @staticmethod
    def can_close(s: str, i: int, closer: str) -> bool:
        if closer == "]":
            return True
        if i == 0 or s[i - 1].isspace():
            return False
        return closer != "*" or not s.startswith("**", i) or (i + 2 < len(s) and s[i + 2] == "*")

    def destination(self, s: str, i: int) -> tuple[str, int]:
        depth = 0
        j = i
        while j < len(s):
            c = s[j]
            if c == "(":
                depth += 1
            elif c == ")":
                if depth == 0:
                    break
                depth -= 1
            elif c.isspace():
                raise self.fail("link destination with a space or a title")
            j += 1
        else:
            raise self.fail("link destination is never closed")
        dest = s[i:j]
        if not dest:
            raise self.fail("empty link destination")
        return dest, j + 1

    def anchor(self, dest: str, inner: str) -> str:
        self.links.append(dest)
        if dest.startswith("https://"):
            return f'<a href="{esc(dest)}" target="_blank" rel="noopener noreferrer">{inner}</a>'
        if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", dest):
            raise self.fail(f"link {dest!r}: only https:// and relative destinations are allowed")
        return f'<a href="{esc(self.link(dest))}">{inner}</a>'


def render(text: str, *, link: Callable[[str], str], code_langs: Mapping[str, str] | None = None) -> Rendered:
    if "\r" in text:
        raise MdliteError("line 0: carriage return")
    p = _Parser(link, code_langs or {})
    blocks = p.blocks(text.split("\n"), 1)
    return Rendered(blocks, p.title, p.headings, p.links, p.langs)
