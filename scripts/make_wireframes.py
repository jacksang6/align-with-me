"""Draw complex S1 wireframe variants for the demo UI round (v2).

Complex admin workspace partitions - 10+ labeled regions per variant,
like a project architecture diagram. 1200x800.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 800
BG = (245, 246, 248)
BOX = (217, 221, 228)
BOX_DARK = (205, 210, 219)
LINE = (150, 156, 165)
TEXT = (80, 86, 96)
SUB = (120, 126, 138)


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", size)


def small(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", size)


def base(title: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((40, 20), title, font=font(28), fill=(60, 66, 76))
    return img, d


def box(d, x, y, w, h, label="", lines=None, fill=BOX):
    d.rounded_rectangle([x, y, x + w, y + h], radius=8, outline=LINE, width=3, fill=fill)
    if label:
        d.text((x + 14, y + 10), label, font=font(24), fill=TEXT)
    if lines:
        ly = y + (52 if label else 14)
        for ln in lines:
            d.text((x + 14, ly), ln, font=small(20), fill=SUB)
            ly += 30


def skeleton_chrome(d):
    """Shared chrome: topbar + statusbar drawn by caller positions."""
    pass


def variant_a() -> Image.Image:
    """变体 A · 编辑器工作台：左章节树 / 中编辑器 / 右 大纲+评论抽屉"""
    img, d = base("变体 A · 编辑器工作台（双面板）")
    # top toolbar
    box(d, 40, 66, W - 80, 64, "顶部工具栏：标题 · 保存状态 · 协作头像", fill=BOX_DARK)
    # left nav tree
    box(d, 40, 146, 220, 560, "章节树", lines=["▾ 第 1 章  引言", "  · 1.1 背景", "  · 1.2 目标", "▸ 第 2 章  方案", "▸ 第 3 章  验收"])
    # main editor
    box(d, 276, 146, 500, 560, "正文编辑器", lines=["标题行（H1）", "段落文本流 ……", "图片占位 [img]", "代码块占位 ```", "引用块 >"])
    # right: outline
    box(d, 792, 146, 368, 260, "大纲面板", lines=["H1 引言", "  H2 背景", "  H2 目标", "H1 方案"])
    # right: comments drawer
    box(d, 792, 424, 368, 282, "评论抽屉", lines=["张三：这里加个例子？", "  ↳ 楼层 2 · 已解决", "李四：术语对齐 GLOSSARY", "  ↳ 待回复"])
    # statusbar
    box(d, 40, 722, W - 80, 56, "状态栏：字数 1830 · 已自动保存 2s 前 · 3 位协作者在线", fill=BOX_DARK)
    return img


def variant_b() -> Image.Image:
    """变体 B · 发布工作台：左导航 / 中编辑器 / 右元数据表单 + 标签选择"""
    img, d = base("变体 B · 发布工作台（元数据面板）")
    box(d, 40, 66, W - 80, 64, "顶部工具栏：草稿 / 发布 / 定时", fill=BOX_DARK)
    box(d, 40, 146, 220, 560, "草稿列表", lines=["· 发布功能草稿 ★", "· 上周复盘", "· skill 提纲"])
    box(d, 276, 146, 500, 560, "正文编辑器", lines=["标题行（H1）", "段落文本流 ……", "图片占位 [img]", "代码块占位 ```"])
    box(d, 792, 146, 368, 300, "元数据表单", lines=["可见性：公开 ▾", "分类：人工智能 ▾", "封面：上传 ▢", "专栏：选择 ▾"])
    box(d, 792, 464, 368, 242, "标签选择器", lines=["[AI编程] [ClaudeCode]", "[开源]  + 添加标签", "创作话题：搜索…"])
    box(d, 40, 722, W - 80, 56, "状态栏：冲突检测 · 版本 r3 · 自动保存开启", fill=BOX_DARK)
    return img


def variant_c() -> Image.Image:
    """变体 C · 仪表盘：KPI 卡行 / 双列表 / 活动流"""
    img, d = base("变体 C · 创作仪表盘（数据面板）")
    box(d, 40, 66, W - 80, 64, "顶部导航：工作台 / 内容 / 数据 / 设置", fill=BOX_DARK)
    for i, (t, v) in enumerate([("草稿", "6"), ("已发布", "23"), ("本周新增", "4"), ("待回复评论", "9")]):
        x = 40 + i * 285
        box(d, x, 146, 265, 110, t, lines=[v])
        d.text((x + 180, 168), v, font=font(44), fill=TEXT)
    box(d, 40, 276, 545, 300, "草稿列表", lines=["· 发布功能草稿  编辑中", "· 上周复盘  已停 3 天", "· skill 提纲  已停 1 周"])
    box(d, 615, 276, 545, 300, "发布队列", lines=["· 掘金  已排 20:00", "· 知乎  已发布 ✓", "· B站  待封面图", "· 小红书  待配图"])
    box(d, 40, 596, 1120, 120, "活动流", lines=["09:41 李四 评论了《发布功能》  ·  09:12 自动保存  ·  08:58 版本 r3 生成"])
    box(d, 40, 730, 1120, 48, "状态栏：数据同步正常", fill=BOX_DARK)
    return img


def main():
    out = Path(r"C:\Users\lenovo\repos\align-with-me\docs\images\wireframes")
    out.mkdir(parents=True, exist_ok=True)
    for name, fn in [("wf-a.png", variant_a), ("wf-b.png", variant_b), ("wf-c.png", variant_c)]:
        fn().save(out / name)
        print(f"[OK] {out / name}")


if __name__ == "__main__":
    main()
