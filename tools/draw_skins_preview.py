#!/usr/bin/env python3
"""生成两套皮肤的逐动作预览图（4 列 × 4 行，共 16 张）。"""

import os
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKINS = os.path.join(ROOT, "build", "dsh_fish", "assets", "skins")
OUT = os.path.join(ROOT, "docs", "img", "skins-preview.png")

ORDER = [
    ("idle_01", "Idle 1"), ("idle_02", "Idle 2"), ("idle_03", "Idle 3"), ("idle_04", "Idle 4"),
    ("userpromptsubmit", "UserPromptSubmit"), ("pretooluse", "PreToolUse"),
    ("posttooluse", "PostToolUse"), ("permissionrequest", "PermissionRequest"),
    ("error", "Error"), ("stop", "Stop"), ("sessionstart", "SessionStart"),
    ("subagentstart", "SubagentStart"), ("subagentstop", "SubagentStop"),
    ("precompact", "PreCompact"), ("postcompact", "PostCompact"), ("sleeping", "Sleeping"),
]


def find_file(skin_dir, key):
    for cand in (f"{key}.gif", f"{key}_01.gif"):
        p = os.path.join(skin_dir, cand)
        if os.path.exists(p):
            return p
    return None


def cache_stats(path):
    im = Image.open(path)
    n = getattr(im, "n_frames", 1)
    colors = len(im.convert("P").getcolors(256) or [])
    return n, colors, os.path.getsize(path)


def main():
    cell, pad, labelh = 168, 12, 46
    cols, rows = 4, 4
    panel_w = cols * (cell + pad) + pad
    panel_h = rows * (cell + labelh + pad) + pad + 34
    gap = 24
    W = panel_w * 2 + gap * 2 + 40
    H = panel_h + 146

    bg = "#111A17"
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    f_title = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 30)
    f_sub = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 17)
    f_cell = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 15)
    f_meta = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 13)

    d.text((20, 18), "两套皮肤 · 16 个动作逐帧预览", font=f_title, fill="#F2FBF6")
    d.text((20, 56), "每格是该动作的第 1 帧，右上角为帧数 / 色数 / 体积；均为 160x160 透明 GIF",
           font=f_sub, fill="#7E9C8C")

    for si, (skin, title, accent) in enumerate([
        ("whale", "鲸鱼娘 whale", "#4ADE80"),
        ("chibi-blue", "蓝发少女 chibi-blue", "#60A5FA"),
    ]):
        ox = 20 + si * (panel_w + gap)
        oy = 118
        d.text((ox + 4, oy - 34), title, font=f_title, fill=accent)
        for i, (key, name) in enumerate(ORDER):
            cx = ox + pad + (i % cols) * (cell + pad)
            cy = oy + pad + (i // cols) * (cell + labelh + pad)
            p = find_file(os.path.join(SKINS, skin, "slow"), key)
            if not p:
                d.text((cx, cy), "missing", font=f_cell, fill="#F87171")
                continue
            im = Image.open(p)
            frame = im.convert("RGBA")
            frame.thumbnail((cell, cell), Image.LANCZOS)
            fw, fh = frame.size
            # 棋盘格底，便于看透明区
            for by in range(0, cell, 12):
                for bx in range(0, cell, 12):
                    c = "#1A2620" if (bx // 12 + by // 12) % 2 == 0 else "#141D19"
                    d.rectangle((cx + bx, cy + by, cx + bx + 11, cy + by + 11), fill=c)
            img.paste(frame, (cx + (cell - fw) // 2, cy + (cell - fh) // 2), frame)
            d.rectangle((cx, cy, cx + cell - 1, cy + cell - 1), outline="#2A4034")
            n, colors, size = cache_stats(p)
            d.text((cx + 2, cy + cell + 3), name, font=f_cell, fill="#E6F7EE")
            meta = f"{n}f {colors}c {size/1024:.0f}K"
            d.text((cx + 2, cy + cell + 25), meta, font=f_meta, fill=accent)

    d.text((20, H - 48), "chibi-blue：10–12 帧、16–32 色、首尾差 mean 4.7 / max 7.5（全部闭环）",
           font=f_sub, fill="#7E9C8C")
    d.text((20, H - 24), "whale：13/16 闭环；PermissionRequest / Stop / SessionStart 三行已改成往返播放，循环点不再跳。",
           font=f_sub, fill="#7E9C8C")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    img.save(OUT)
    print(f"ok {OUT} {img.size}")


if __name__ == "__main__":
    main()

