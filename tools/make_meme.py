#!/usr/bin/env python3
"""为 B 页左下角生成缩略版素材（96x92 容器里用）。

B 页角色格子只有 96x92，主素材是 160x160，直接放进去会被裁掉大半。
这里把**每个动作**（不只 Idle）等比缩到 88x88，保持透明背景、保留帧延时，
设备端优先用 meme/ 目录的小图，没有就回退全尺寸。

注意：RGBA 直接 convert("P") 会丢掉 alpha，透明区变成不透明色块，
播放时就会出现「白底/黑底来回闪」的观感。这里整段动画共用一张调色板，
0 号索引专门留给透明色。
"""

import os
import re
from pathlib import Path
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKINS = os.path.join(ROOT, "build", "dsh_fish", "assets", "skins")
SPEEDS = ("slow", "normal", "fast")
SIZE = 88
COLORS = 32
ALPHA_CUT = 128


def shrink(src, dst, size=SIZE, colors=COLORS):
    im = Image.open(src)
    n = getattr(im, "n_frames", 1)
    duration = im.info.get("duration", 120)

    frames = []
    for i in range(n):
        im.seek(i)
        f = im.convert("RGBA")
        f.thumbnail((size, size), Image.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.paste(f, ((size - f.width) // 2, (size - f.height) // 2), f)
        frames.append(canvas)

    pixels = []
    for f in frames:
        for y in range(0, size, 2):
            for x in range(0, size, 2):
                r, g, b, a = f.getpixel((x, y))
                if a >= ALPHA_CUT:
                    pixels.append(bytes((r, g, b)))
    if not pixels:
        pixels = [b"\x00\x00\x00"]
    strip = Image.frombytes("RGB", (len(pixels), 1), b"".join(pixels))
    palette_img = strip.quantize(
        colors=colors - 1, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
    )

    out = []
    for f in frames:
        alpha = f.getchannel("A").point(lambda v: 255 if v >= ALPHA_CUT else 0)
        solid = Image.new("RGBA", (size, size), (0, 0, 0, 255))
        solid.paste(f, (0, 0), alpha)
        p = solid.convert("RGB").quantize(palette=palette_img, dither=Image.Dither.NONE)
        p = p.point(lambda v: min(colors - 1, v + 1))
        base = palette_img.getpalette()[: (colors - 1) * 3]
        base = base + [0, 0, 0] * (colors - 1 - len(base) // 3)
        p.putpalette([0, 0, 0] + base)
        transparent = alpha.point(lambda v: 255 if v == 0 else 0)
        p.paste(0, mask=transparent)
        out.append(p)

    os.makedirs(os.path.dirname(dst), exist_ok=True)
    out[0].save(
        dst,
        save_all=True,
        append_images=out[1:],
        duration=duration,
        loop=0,
        disposal=2,
        transparency=0,
        optimize=True,
    )
    return n, os.path.getsize(dst)


def check(path):
    im = Image.open(path)
    im.seek(0)
    rgba = im.convert("RGBA")
    return [rgba.getpixel(p)[3] for p in ((0, 0), (im.width - 1, 0), (0, im.height - 1), (im.width - 1, im.height - 1))]


def all_variants(skin_dir):
    """manifest 里所有事件引用到的 GIF（去重，保持首次出现顺序）。"""
    manifest = skin_dir / "manifest.lua"
    if not manifest.exists():
        return []
    txt = manifest.read_text(encoding="utf-8")
    names, seen = [], set()
    for body in re.findall(r'\[\s*"[A-Za-z]+"\s*\]\s*=\s*\{([^}]*)\}', txt):
        for fn in re.findall(r'"([^"]+\.gif)"', body):
            if fn not in seen:
                seen.add(fn)
                names.append(fn)
    return names


def main():
    total = 0
    bad = 0
    for skin in sorted(os.listdir(SKINS)):
        skin_dir = Path(SKINS) / skin
        if not skin_dir.is_dir():
            continue
        names = all_variants(skin_dir)
        if not names:
            continue
        for speed in SPEEDS:
            for fn in names:
                src = skin_dir / speed / fn
                if not src.exists():
                    continue
                dst = skin_dir / "meme" / speed / fn
                n, size = shrink(str(src), str(dst))
                corners = check(str(dst))
                total += 1
                ok = all(c == 0 for c in corners)
                if not ok:
                    bad += 1
                print(f"{skin}/{speed}/{fn}  {n}f  {size/1024:5.1f}KB  {SIZE}x{SIZE}{'' if ok else '  !! 四角不透明 ' + str(corners)}")
    print(f"\nmeme thumbs: {total} 个，四角异常 {bad} 个")


if __name__ == "__main__":
    main()
