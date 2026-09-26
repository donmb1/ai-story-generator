"""Rendert Bildschirme und Story-Seiten als Graustufen-PNG in Kindle-Auflösung.

Layout und Hit-Test nutzen dieselben Widget-Listen, damit Zeichnen und
Antippen nie auseinanderlaufen.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from .settings import BASE_DIR, settings

FONT_DIR = BASE_DIR / "fonts"
W, H = settings.screen_w, settings.screen_h
MARGIN = 64

INK = 0
GREY = 110
LIGHT = 200
PAPER = 255


@lru_cache(maxsize=64)
def ui_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "AtkinsonHyperlegible-Bold.ttf" if bold else "AtkinsonHyperlegible-Regular.ttf"
    return ImageFont.truetype(str(FONT_DIR / name), size)


@lru_cache(maxsize=32)
def book_font(size: int, weight: str = "Regular") -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT_DIR / "Literata.ttf"), size)
    f.set_variation_by_name(weight)
    return f


@dataclass
class Widget:
    kind: str  # button | text | title | small
    x: int
    y: int
    w: int
    h: int
    label: str = ""
    action: str | None = None
    primary: bool = False
    size: int = 40

    def hit(self, px: int, py: int) -> bool:
        # etwas großzügiger als gezeichnet, E-Ink-Touch ist ungenau
        pad = 10
        return self.action is not None and (
            self.x - pad <= px <= self.x + self.w + pad and self.y - pad <= py <= self.y + self.h + pad
        )


def fit_text(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> str:
    if font.getlength(text) <= max_w:
        return text
    while text and font.getlength(text + "…") > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


def wrap(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        words, line = para.split(), ""
        for word in words:
            cand = f"{line} {word}".strip()
            if font.getlength(cand) <= max_w or not line:
                line = cand
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def draw_widgets(widgets: list[Widget]) -> bytes:
    img = Image.new("L", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    for wd in widgets:
        if wd.kind == "button":
            radius = 18
            if wd.primary:
                d.rounded_rectangle((wd.x, wd.y, wd.x + wd.w, wd.y + wd.h), radius, fill=INK)
                color = PAPER
            else:
                d.rounded_rectangle((wd.x, wd.y, wd.x + wd.w, wd.y + wd.h), radius, outline=INK, width=4)
                color = INK
            font = ui_font(wd.size, bold=wd.primary)
            label = fit_text(wd.label, font, wd.w - 40)
            d.text((wd.x + wd.w / 2, wd.y + wd.h / 2), label, font=font, fill=color, anchor="mm")
        elif wd.kind == "title":
            font = ui_font(wd.size, bold=True)
            y = wd.y
            for line in wrap(wd.label, font, wd.w):
                d.text((wd.x, y), line, font=font, fill=INK)
                y += int(wd.size * 1.25)
        elif wd.kind == "text":
            font = ui_font(wd.size)
            y = wd.y
            for line in wrap(wd.label, font, wd.w):
                d.text((wd.x, y), line, font=font, fill=INK)
                y += int(wd.size * 1.35)
        elif wd.kind == "small":
            font = ui_font(wd.size)
            d.text((wd.x, wd.y), fit_text(wd.label, font, wd.w), font=font, fill=GREY)
        elif wd.kind == "rule":
            d.line((wd.x, wd.y, wd.x + wd.w, wd.y), fill=LIGHT, width=3)
    return to_png(img)


def to_png(img: Image.Image) -> bytes:
    # E-Ink kann 16 Graustufen – quantisieren spart Übertragung und Speicher
    img = img.point(lambda v: (v // 17) * 17)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


# ---------------------------------------------------------------- Layout-Bausteine

def header(breadcrumb: str, title: str) -> list[Widget]:
    out = []
    if breadcrumb:
        out.append(Widget("small", MARGIN, 56, W - 2 * MARGIN, 40, breadcrumb, size=32))
    # Lange Titel (z. B. Story-Titel im Menü): kleiner setzen, höchstens zwei Zeilen
    size = 64
    if len(wrap(title, ui_font(size, bold=True), W - 2 * MARGIN)) > 1:
        size = 48
        lines = wrap(title, ui_font(size, bold=True), W - 2 * MARGIN)
        if len(lines) > 2:
            title = lines[0] + " " + fit_text(lines[1], ui_font(size, bold=True), W - 2 * MARGIN - 60)
    out.append(Widget("title", MARGIN, 110, W - 2 * MARGIN, 140, title, size=size))
    out.append(Widget("rule", MARGIN, 250, W - 2 * MARGIN, 0))
    return out


def grid(items: list[tuple[str, str]], top: int = 290, cols: int = 2, row_h: int = 132, gap: int = 26) -> list[Widget]:
    col_w = (W - 2 * MARGIN - gap * (cols - 1)) // cols
    out = []
    for i, (label, action) in enumerate(items):
        r, c = divmod(i, cols)
        out.append(Widget("button", MARGIN + c * (col_w + gap), top + r * (row_h + gap), col_w, row_h, label, action, size=40))
    return out


def stack(items: list[tuple[str, str, bool]], top: int, h: int = 150, gap: int = 34) -> list[Widget]:
    return [
        Widget("button", MARGIN, top + i * (h + gap), W - 2 * MARGIN, h, label, action, primary, size=46)
        for i, (label, action, primary) in enumerate(items)
    ]


def footer(back: tuple[str, str] | None, page: int, pages: int, prev_action: str | None, next_action: str | None) -> list[Widget]:
    y, h = H - 190, 130
    out = []
    if back:
        out.append(Widget("button", MARGIN, y, 330, h, back[0], back[1], size=40))
    if pages > 1:
        out.append(Widget("small", W - MARGIN - 440 + 150, y + 45, 140, 40, f"{page + 1} / {pages}", size=34))
        if prev_action:
            out.append(Widget("button", W - MARGIN - 440, y, 130, h, "‹", prev_action, size=64))
        if next_action:
            out.append(Widget("button", W - MARGIN - 150, y, 150, h, "›", next_action, size=64))
    return out


# ---------------------------------------------------------------- Story-Seiten

@dataclass(frozen=True)
class PageStyle:
    size: int
    margin_x: int = 84
    top: int = 96
    bottom: int = 130

    @property
    def line_h(self) -> int:
        return int(self.size * 1.5)


def paginate(title: str, story: str, kids: bool) -> list[list[tuple[str, str]]]:
    """Liefert Seiten als Liste von (art, text)-Zeilen; art in title|tgap|line|gap."""
    st = PageStyle(size=46 if kids else 40)
    body = book_font(st.size)
    tfont = book_font(int(st.size * 1.55), "SemiBold")
    max_w = W - 2 * st.margin_x
    usable = H - st.top - st.bottom

    pages: list[list[tuple[str, str]]] = []
    page: list[tuple[str, str]] = []
    used = 0

    for line in wrap(title, tfont, max_w):
        page.append(("title", line))
        used += int(tfont.size * 1.3)
    page.append(("tgap", ""))
    used += st.line_h

    paragraphs = [p.strip() for p in story.split("\n\n") if p.strip()]
    for pi, para in enumerate(paragraphs):
        for line in wrap(para.replace("\n", " "), body, max_w):
            if used + st.line_h > usable:
                pages.append(page)
                page, used = [], 0
            page.append(("line", line))
            used += st.line_h
        if pi < len(paragraphs) - 1 and used + st.line_h // 2 <= usable and page:
            page.append(("gap", ""))
            used += st.line_h // 2
    if page:
        pages.append(page)
    return pages


def render_story_page(title: str, lines: list[tuple[str, str]], n: int, total: int, kids: bool) -> bytes:
    st = PageStyle(size=46 if kids else 40)
    body = book_font(st.size)
    tfont = book_font(int(st.size * 1.55), "SemiBold")
    img = Image.new("L", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    y = st.top
    for kind, text in lines:
        if kind == "title":
            d.text((st.margin_x, y), text, font=tfont, fill=INK)
            y += int(tfont.size * 1.3)
        elif kind == "line":
            d.text((st.margin_x, y), text, font=body, fill=INK)
            y += st.line_h
        elif kind == "tgap":
            y += st.line_h
        else:
            y += st.line_h // 2
    small = ui_font(30)
    d.text((W / 2, H - 70), f"{n} / {total}", font=small, fill=GREY, anchor="mm")
    if n == 1:
        d.text((W / 2, H - 30), "rechts tippen: weiter  ·  links: zurück  ·  oben: Menü", font=ui_font(24), fill=LIGHT - 40, anchor="mm")
    return to_png(img)
