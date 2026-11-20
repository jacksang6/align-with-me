"""Generate Xiaohongshu/Douyin card set (1080x1440, 3:4) for the launch post.

5 cards: cover / pain points / how it works / real console screenshot / install.
Fonts: Windows Microsoft YaHei (regular + bold), Consolas for code.
Output: docs/images/cards/card-1.png ... card-5.png
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1440
BG = (26, 29, 35)
PANEL = (36, 40, 49)
TEXT = (235, 238, 243)
DIM = (140, 148, 160)
ACCENT = (124, 92, 255)
ACCENT_SOFT = (124, 92, 255, 40)

FONT_DIR = Path(r"C:\Windows\Fonts")


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), size)


def bold(size: int) -> ImageFont.FreeTypeFont:
    return font("msyhbd.ttc", size)


def reg(size: int) -> ImageFont.FreeTypeFont:
    return font("msyh.ttc", size)


def mono(size: int) -> ImageFont.FreeTypeFont:
    return font("consola.ttf", size)


def base_card() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # subtle top accent bar
    d.rounded_rectangle([60, 70, 200, 82], radius=6, fill=ACCENT)
    # footer
    d.text((60, H - 90), "GitHub · jacksang6/align-with-me", font=reg(28), fill=DIM)
    d.text((W - 260, H - 90), "MIT 开源", font=reg(28), fill=DIM)
    return img


def wrap(text: str, f: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines: list[str] = []
    cur = ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        if f.getlength(cur + ch) > max_w:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def draw_wrapped(d: ImageDraw.ImageDraw, text: str, x: int, y: int, f, max_w: int, fill, spacing: int = 18) -> int:
    for line in wrap(text, f, max_w):
        d.text((x, y), line, font=f, fill=fill)
        y += f.size + spacing
    return y


def card1_cover() -> Image.Image:
    img = base_card()
    d = ImageDraw.Draw(img)
    y = 220
    d.text((60, y), "AI 编程", font=bold(40), fill=ACCENT)
    y += 80
    y = draw_wrapped(d, "你的 AI 总做错东西？", 60, y, bold(96), W - 120, TEXT, 8) + 20
    y = draw_wrapped(d, "问题不在它，在你没“烤”它", 60, y, bold(72), W - 120, TEXT, 8) + 40
    # decision tree motif: trunk + two branches + highlighted node
    cx = W // 2
    d.line([(cx, y + 40), (cx, y + 260)], fill=TEXT, width=10)
    d.line([(cx, y + 260), (cx - 180, y + 360)], fill=TEXT, width=10)
    d.line([(cx, y + 260), (cx + 180, y + 360)], fill=TEXT, width=10)
    d.ellipse([cx - 190, y + 340, cx - 170, y + 360], fill=TEXT)
    d.ellipse([cx + 170, y + 340, cx + 190, y + 360], fill=TEXT)
    d.ellipse([cx - 34, y + 6, cx + 34, y + 74], fill=ACCENT, outline=TEXT, width=4)
    # subtitle
    y2 = y + 430
    draw_wrapped(d, "grill-tree：写代码前，把你的需求拷问成决策树", 60, y2, reg(44), W - 120, DIM, 6)
    return img


def card2_pain() -> Image.Image:
    img = base_card()
    d = ImageDraw.Draw(img)
    d.text((60, 120), "真实场景", font=bold(44), fill=ACCENT)
    y = 210
    d.text((60, y), "同一句话丢给 AI：", font=reg(38), fill=TEXT)
    y += 90
    d.rounded_rectangle([60, y, W - 60, y + 110], radius=20, fill=PANEL)
    d.text((90, y + 32), "“帮我加文章发布功能，要能存草稿。”", font=reg(36), fill=TEXT)
    y += 170
    items = [
        ("你想要的草稿", "自动保存", "它做的", "手动 Ctrl+S"),
        ("你想的发布", "默认公开", "它做的", "默认私密 + 二次确认"),
        ("断网发布失败", "保住草稿", "它做的", "直接把草稿清空"),
    ]
    for a, aw, b, bw in items:
        d.rounded_rectangle([60, y, W - 60, y + 170], radius=20, fill=PANEL)
        d.text((90, y + 28), a, font=reg(34), fill=DIM)
        d.text((90, y + 78), aw, font=bold(40), fill=ACCENT)
        d.text((W // 2 + 30, y + 28), b, font=reg(34), fill=DIM)
        d.text((W // 2 + 30, y + 78), bw, font=bold(40), fill=TEXT)
        y += 200
    draw_wrapped(d, "每一处都要返工 —— 返工的时间，远超当初“多说两句”的成本。", 60, y + 20, reg(38), W - 120, DIM, 8)
    return img


def card3_how() -> Image.Image:
    img = base_card()
    d = ImageDraw.Draw(img)
    d.text((60, 120), "grill-tree 怎么做", font=bold(44), fill=ACCENT)
    y = 230
    steps = [
        ("1", "画成决策树", "每个决策分叉出下一层决策"),
        ("2", "一轮一轮问", "只问前提已确定的问题，不问没法答的"),
        ("3", "带推荐答案", "“建议 65% 选 A”+ 理由，你确认或改"),
        ("4", "问完为止", "没有“双方默认以为一致”的地方"),
    ]
    for n, t, s in steps:
        d.ellipse([60, y + 10, 132, y + 82], fill=ACCENT)
        w_txt = bold(44).getlength(n)
        d.text((96 - w_txt / 2, y + 22), n, font=bold(44), fill=(255, 255, 255))
        d.text((170, y), t, font=bold(46), fill=TEXT)
        d.text((170, y + 66), s, font=reg(34), fill=DIM)
        y += 170
    y += 20
    d.rounded_rectangle([60, y, W - 60, y + 130], radius=20, fill=PANEL)
    draw_wrapped(d, "UI 决策不走文字：起一个本地决策控制台，每个选项带真实渲染截图", 90, y + 28, reg(36), W - 200, TEXT, 6)
    return img


def card4_shot() -> Image.Image:
    img = base_card()
    d = ImageDraw.Draw(img)
    d.text((60, 120), "UI 决策控制台（真实运行截图）", font=bold(40), fill=ACCENT)
    shot = Image.open(Path(r"C:\Users\lenovo\repos\align-with-me\docs\images\decision-console.png"))
    # console shot is 2560x4062-ish tall; crop top 55% for the card
    ratio = (W - 120) / shot.width
    shot = shot.resize((W - 120, int(shot.height * ratio)), Image.LANCZOS)
    shot = shot.crop((0, 0, W - 120, min(shot.height, 1050)))
    frame_h = shot.height + 24
    d.rounded_rectangle([48, 210, W - 48, 210 + frame_h + 24], radius=24, fill=(15, 17, 21))
    img.paste(shot, (60, 222))
    draw_wrapped(d, "一卡一决策 · 选项按概率排序 · 键盘 1-9 选择", 60, 210 + frame_h + 60, reg(34), W - 120, DIM, 6)
    return img


def card5_install() -> Image.Image:
    img = base_card()
    d = ImageDraw.Draw(img)
    d.text((60, 140), "30 秒装起来", font=bold(56), fill=ACCENT)
    y = 300
    cmds = [
        ("1 · 先装依赖（Matt Pocock 的工程技能）", "npx skills add mattpocock/skills -a claude-code"),
        ("2 · 再装本仓库", "npx skills add jacksang6/align-with-me -a claude-code"),
        ("3 · 对 AI 说", "/align-with-me"),
    ]
    for label, cmd in cmds:
        d.text((60, y), label, font=reg(34), fill=DIM)
        y += 60
        lines = wrap(cmd, mono(38), W - 180)
        box_h = len(lines) * 58 + 44
        d.rounded_rectangle([60, y, W - 60, y + box_h], radius=20, fill=PANEL)
        ty = y + 22
        for ln in lines:
            d.text((90, ty), ln, font=mono(38), fill=(158, 206, 255))
            ty += 58
        y += box_h + 46
    draw_wrapped(d, "支持 Claude Code / Codex / Cursor 等 75+ agent，-a 换名字即可", 60, y, reg(36), W - 120, DIM, 6)
    return img


def main():
    out_dir = Path(r"C:\Users\lenovo\repos\align-with-me\docs\images\cards")
    out_dir.mkdir(parents=True, exist_ok=True)
    cards = [card1_cover(), card2_pain(), card3_how(), card4_shot(), card5_install()]
    for i, c in enumerate(cards, 1):
        p = out_dir / f"card-{i}.png"
        c.save(p)
        print(f"[OK] {p}")


if __name__ == "__main__":
    main()
