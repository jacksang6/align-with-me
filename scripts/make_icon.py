"""Generate the plugin icon: decision-tree branching on a dark rounded tile.

1024x1024, supersampled 4x then downscaled for smooth edges.
Output: .claude-plugin/icon.png
"""
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
SS = 4  # supersample factor
W = SIZE * SS

BG = (26, 29, 35, 255)        # dark tile
LINE = (235, 238, 243, 255)   # near-white branches
NODE = (235, 238, 243, 255)   # plain nodes
HILITE = (124, 92, 255, 255)  # highlighted top node (purple)
DIM = (120, 128, 140, 255)    # inactive branch

RADIUS = 224 * SS // 4 * 4 // 4  # ~224px corner radius at 1x


def rounded_tile(draw):
    draw.rounded_rectangle(
        [0, 0, W - 1, W - 1], radius=224 * SS // 4 * SS // SS * SS // 4 * 4, fill=BG
    )


def main():
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, W - 1, W - 1], radius=224 * SS, fill=BG)

    lw = 34 * SS  # branch stroke width

    # trunk: rises from bottom-center to the first fork
    fork_y = int(W * 0.60)
    top_y = int(W * 0.24)
    cx = W // 2
    root_y = int(W * 0.82)
    left_x = int(W * 0.30)
    right_x = int(W * 0.70)

    d.line([(cx, root_y), (cx, fork_y)], fill=LINE, width=lw)
    # two branches curve out from the fork
    d.arc([left_x, fork_y - (fork_y - top_y) // 2, cx, fork_y + (fork_y - top_y) // 2],
          start=270, end=360, fill=LINE, width=lw)
    d.arc([cx, fork_y - (fork_y - top_y) // 2, right_x, fork_y + (fork_y - top_y) // 2],
          start=180, end=270, fill=LINE, width=lw)
    # branch stubs rise to their nodes
    d.line([(left_x, fork_y), (left_x, int(W * 0.46))], fill=LINE, width=lw)
    d.line([(right_x, fork_y), (right_x, int(W * 0.46))], fill=LINE, width=lw)
    # trunk continues to the highlighted decision node
    d.line([(cx, fork_y), (cx, top_y + 44 * SS)], fill=LINE, width=lw)

    def node(x, y, r, fill, outline=None, ow=0):
        d.ellipse([x - r, y - r, x + r, y + r], fill=fill, outline=outline, width=ow)

    # plain nodes at branch ends
    nr = 30 * SS
    node(left_x, int(W * 0.44), nr, NODE)
    node(right_x, int(W * 0.44), nr, NODE)
    # highlighted decision node on top
    hr = 46 * SS
    node(cx, top_y, hr, HILITE, outline=(235, 238, 243, 255), ow=8 * SS)

    # root pad
    node(cx, root_y, 22 * SS, DIM)

    img = img.resize((SIZE, SIZE), Image.LANCZOS)
    out = Path(__file__).resolve().parent.parent / ".claude-plugin" / "icon.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"[OK] wrote {out} ({SIZE}x{SIZE})")


if __name__ == "__main__":
    main()
