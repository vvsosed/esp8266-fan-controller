"""Turn board.html into the GitHub wiki page: Board-Layout.md plus the two views as self-contained SVGs.

Usage: python3 wiki.py <checkout of esp8266-fan-controller.wiki.git>

The wiki renders Markdown and strips inline SVG, styles and scripts, so the drawings become images
(each SVG gets the page's stylesheet embedded, since the bare SVGs draw black without it) and the
per-net show-hide toggles are left out. Run page.py first; this reads its output.
"""
import re
import sys
from html.parser import HTMLParser

SRC = "board.html"
PAGE = "Board-Layout.md"
VIEWS = {"top view": ("board-top.svg", "Top side: parts"), "back view": ("board-back.svg", "Back side: chains and wires")}
VOID = {"br", "img", "meta", "link", "hr"}


def esc(s):
    """Escape Markdown punctuation in running text (not in code)."""
    return re.sub(r"([*_\[\]<|\\])", r"\\\1", s)


class ToMarkdown(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []       # finished Markdown blocks, in order
        self.buf = None        # inline text being collected, or None
        self.skip = 0          # > 0 while inside a subtree that is dropped
        self.lists = []        # open lists: "ul" or "ol", with the item count
        self.table = None      # rows of the table being collected
        self.row = None
        self.cell = None
        self.code = 0
        self.quote = False     # inside <div class="warn">
        self.legend = None     # legend items being collected
        self.href = None
        self.block_tag = None

    # --- helpers ---
    def text(self):
        return re.sub(r"\s+", " ", "".join(self.buf)).strip()

    def emit(self, s, item=False):
        if s:
            self.blocks.append((s, item))

    # --- tags ---
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "").split()
        if self.skip:
            if tag not in VOID:
                self.skip += 1
            return
        if tag in ("style", "script", "h1") or (tag == "div" and "nets" in cls):
            self.skip = 1
            return
        if tag == "svg":
            name, caption = VIEWS[a["aria-label"]]
            self.emit(f"![{caption}]({name})")
            self.skip = 1
            return
        if tag == "div" and "legend" in cls:
            self.legend, self.legend_depth = [], 0
            return
        if self.legend is not None and tag == "span":   # an item is the outer span; the inner one is its colour swatch
            if self.legend_depth == 0:
                self.buf = []
            self.legend_depth += 1
            return
        if tag == "div" and "eyebrow" in cls:
            self.buf = []
            self.block_tag = "eyebrow"
            return
        if tag == "div" and "warn" in cls:
            self.quote = True
            return
        if tag in ("h2", "h3", "p"):
            self.buf = []
            self.block_tag = tag
            return
        if tag in ("ul", "ol"):
            self.lists.append([tag, 0])
            return
        if tag == "li":
            self.lists[-1][1] += 1
            self.buf = []
            self.block_tag = "li"
            return
        if tag == "table":
            self.table = []
            return
        if tag == "tr":
            self.row = []
            return
        if tag in ("th", "td"):
            self.buf = []
            return
        if self.buf is None:
            return
        if tag in ("b", "strong"):
            self.buf.append("**")
        elif tag in ("i", "em"):
            self.buf.append("*")
        elif tag == "code":
            self.buf.append("`")
            self.code += 1
        elif tag == "a":
            self.buf.append("[")
            self.href = a.get("href", "")
        elif tag == "br":
            self.buf.append("<br>" if self.table is not None else "\n")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.skip:
            if tag not in VOID:
                self.skip -= 1
            return
        if tag == "div" and self.legend is not None and self.buf is None:
            self.emit("*Legend: " + " · ".join(self.legend) + "*")
            self.legend = None
            return
        if self.legend is not None and tag == "span":
            self.legend_depth -= 1
            if self.legend_depth == 0:
                t = self.text()
                if t:
                    self.legend.append(t)
                self.buf = None
            return
        if tag == "div" and self.quote:
            self.quote = False
            return
        if tag == "div" and self.block_tag == "eyebrow":
            self.emit("*" + self.text() + "*")
            self.buf = None
            self.block_tag = None
            return
        if tag in ("h2", "h3"):
            self.emit(("## " if tag == "h2" else "### ") + self.text())
            self.buf = None
            return
        if tag == "p":
            t = self.text()
            if not t.startswith("Click a wire"):   # the toggles don't exist on the wiki
                self.emit("> " + t if self.quote else t)
            self.buf = None
            return
        if tag == "li":
            kind, n = self.lists[-1]
            self.emit(("- " if kind == "ul" else f"{n}. ") + self.text(), item=True)
            self.buf = None
            return
        if tag in ("ul", "ol"):
            self.lists.pop()
            return
        if tag in ("th", "td"):
            self.row.append(self.text())
            self.buf = None
            return
        if tag == "tr":
            self.table.append(self.row)
            self.row = None
            return
        if tag == "table":
            head, *body = self.table
            lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
            lines += ["| " + " | ".join(r) + " |" for r in body]
            self.emit("\n".join(lines))
            self.table = None
            return
        if self.buf is None:
            return
        if tag in ("b", "strong"):
            self.buf.append("**")
        elif tag in ("i", "em"):
            self.buf.append("*")
        elif tag == "code":
            self.buf.append("`")
            self.code -= 1
        elif tag == "a":
            self.buf.append(f"]({self.href})")

    def handle_data(self, data):
        if self.skip or self.buf is None:
            return
        self.buf.append(data if self.code else esc(data))

    def markdown(self):
        out, prev_item = [], False
        for s, item in self.blocks:
            out.append(("\n" if item and prev_item else "\n\n") + s)
            prev_item = item
        return "".join(out).strip() + "\n"


def main(outdir):
    html = open(SRC, encoding="utf-8").read()
    css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    for label, (name, _) in VIEWS.items():
        m = re.search(rf'(<svg [^>]*aria-label="{label}"[^>]*>)(.*?)(</svg>)', html, re.S)
        svg = m.group(1) + "<style><![CDATA[" + css + "]]></style>" + m.group(2) + m.group(3)
        open(f"{outdir}/{name}", "w", encoding="utf-8").write(svg)
    p = ToMarkdown()
    p.feed(html)
    note = ("*Generated from `docs/board/board.html` by `docs/board/wiki.py`: edit `data.py` in the repository, "
            "not this page. The [interactive version](https://vvsosed.github.io/esp8266-fan-controller/board/board.html) "
            "hides and shows the wires and chains per net, or one wire at a time.*")
    open(f"{outdir}/{PAGE}", "w", encoding="utf-8").write(note + "\n\n" + p.markdown())
    print(PAGE, len(p.blocks), "blocks;", ", ".join(n for n, _ in VIEWS.values()))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
