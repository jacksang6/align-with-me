"""Render the logic tree and design tree (English, ASCII, terminal style) as PNGs.

These mirror the exact formats grill-tree produces: logic tree = ASCII tree in a
text fence; design tree = decision nodes with agreed marks. Dark terminal look.
Emoji drawn with Segoe UI Emoji; code with Consolas.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BG = (26, 29, 35)
TEXT = (235, 238, 243)
DIM = (120, 128, 140)
ACCENT = (124, 92, 255)
GREEN = (134, 216, 156)

MONO = r"C:\Windows\Fonts\consola.ttf"
MONO_B = r"C:\Windows\Fonts\consolab.ttf"
EMOJI = r"C:\Windows\Fonts\seguiemj.ttf"
EMOJI_CHARS = set("📌🎯🧮📤🧪✅🗄")


def is_emoji(ch):
    return ch in EMOJI_CHARS


LOGIC_TREE = """[Logic] blog publishing flow
│
├─ L1 open editor
│      🗄 load draft by article_id
│
├─ L2 typing
│    ├─ G1: idle >= 2s ?
│    │    ├─ yes -> L3 autosave
│    │    └─ no  -> keep typing
│
├─ L3 autosave draft
│      🗄 draft.content, draft.saved_at = now
│
├─ L4 click publish
│    ├─ G2: network ok ?
│    │    ├─ yes -> L5 do publish
│    │    └─ no  -> L6 failure banner
│
├─ L5 publish
│      🗄 article.status = public   <- D1
│
└─ L6 failure banner
       └─ user retries -> back to L4
"""

DESIGN_TREE = """[Design] blog publishing experience
│
├─ 📌 D1 article visibility ✅ agreed
│    🎯 Who sees a new article by default?
│    🧮 1. public on publish <- agreed
│       2. private first
│    📤 Output: visibility field, feeds L5
│    🧪 C1 (functional): published article is
│        public — verify: read article anon
│
├─ 📌 D2 autosave timing ✅ agreed
│    🎯 When do drafts autosave?
│    🧮 1. after 2s idle <- agreed
│    📤 Output: debounce constant, feeds L2/G1
│    🧪 C2 (logic): idle 2s -> draft written
│
└─ 📌 D3 publish failure notice ✅ agreed
     🎯 How to notify on network failure?
     🧮 1. top banner + retry <- agreed
     📤 Output: banner component, feeds L6
     🧪 C3 (qa): offline publish -> draft kept
"""


def draw_line(d, x, y, ln, fonts, color):
    f_reg, f_bold, f_emoji = fonts
    seg = None
    buf = ""
    cx = x
    for ch in ln:
        want = "emoji" if is_emoji(ch) else "text"
        if seg is None:
            seg = want
        if want != seg:
            font = f_emoji if seg == "emoji" else f_reg
            d.text((cx, y), buf, font=font, fill=color, embedded_color=(seg == "emoji"))
            cx += font.getlength(buf)
            buf = ch
            seg = want
        else:
            buf += ch
    if buf:
        font = f_emoji if seg == "emoji" else f_reg
        d.text((cx, y), buf, font=font, fill=color, embedded_color=(seg == "emoji"))


def render(name, text):
    lines = text.rstrip("\n").split("\n")
    fs = 26
    f_reg = ImageFont.truetype(MONO, fs)
    f_bold = ImageFont.truetype(MONO_B, fs)
    f_emoji = ImageFont.truetype(EMOJI, int(fs * 1.02))
    fonts = (f_reg, f_bold, f_emoji)
    line_h = 44
    pad = 48
    width = max(int(f_reg.getlength(ln)) for ln in lines) + pad * 2 + 80
    img = Image.new("RGB", (width, pad * 2 + line_h * len(lines)), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, img.width - 1, 14], radius=0, fill=ACCENT)
    y = pad
    for ln in lines:
        color = TEXT
        if "📌" in ln:
            color = GREEN
        elif ln.strip().startswith(("🗄", "🧪", "🧮", "📤")):
            color = DIM
        use_bold = ln.strip().startswith(("[Logic]", "[Design]")) or "📌 D" in ln
        font = f_bold if use_bold else f_reg
        draw_line(d, pad, y, ln, fonts, color)
        y += line_h
    out = Path(r"C:\Users\lenovo\repos\align-with-me\docs\images") / name
    img.save(out)
    print(f"[OK] {out}")


def main():
    render("logic-tree-en.png", LOGIC_TREE)
    render("decision-tree-en.png", DESIGN_TREE)


if __name__ == "__main__":
    main()
