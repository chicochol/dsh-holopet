# -*- coding: utf-8 -*-
"""把各路线素材压成设备能跑的 160×160 索引 GIF，并报告体积。

设备端 LVGL 的 GIF 解码器吃的是整帧解码，holopet 自己的素材单文件只有 3–21KB，
所以这里的目标是：160×160、≤24 帧、单文件进 30KB 以内。
"""
import os
import sys
from PIL import Image, ImageSequence

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, "..", "assets", "refs")
OUT = os.path.join(HERE, "..", "assets", "out")

SIZE = (160, 160)
MAX_FRAMES = 24
COLORS = 96


def load_gif(path):
    im = Image.open(path)
    return [f.convert("RGBA") for f in ImageSequence.Iterator(im)]


def load_sprite(path, idxs, cw=192, ch=208, cols=8):
    sheet = Image.open(path).convert("RGBA")
    out = []
    for i in idxs:
        r, c = divmod(i, cols)
        out.append(sheet.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch)))
    return out


def union_bbox(frames):
    box = None
    for f in frames:
        b = f.getbbox()
        if b:
            box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]),
                                         max(box[2], b[2]), max(box[3], b[3]))
    return box


def resample(frames, n):
    if len(frames) <= n:
        return frames
    step = len(frames) / float(n)
    return [frames[min(len(frames) - 1, int(i * step))] for i in range(n)]


def to_gif(frames, out, size=SIZE, max_frames=MAX_FRAMES, colors=COLORS):
    frames = resample(frames, max_frames)
    box = union_bbox(frames)
    frames = [f.crop(box) for f in frames]          # 统一裁切，避免抖动
    w, h = frames[0].size
    k = min(size[0] / w, size[1] / h)
    tw, th = max(1, int(w * k)), max(1, int(h * k))
    ox, oy = (size[0] - tw) // 2, (size[1] - th) // 2

    canvas = []
    for f in frames:
        small = f.resize((tw, th), Image.LANCZOS)
        base = Image.new("RGBA", size, (0, 0, 0, 0))
        base.paste(small, (ox, oy), small)
        canvas.append(base)

    # 二值化 alpha，再量化成 P；透明像素用索引 0
    pals = []
    for c in canvas:
        a = c.split()[-1].point(lambda v: 255 if v >= 128 else 0)
        c.putalpha(a)
        pal = c.quantize(colors=colors - 1, method=Image.Quantize.FASTOCTREE)
        pals.append(pal)

    pals[0].save(out, save_all=True, append_images=pals[1:], duration=90,
                 loop=0, disposal=2, transparency=0, optimize=True)
    return len(frames), os.path.getsize(out)


def main():
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    cases = [
        ("pc2005-chitoken.gif", lambda p: load_gif(p)),
        ("pc2005-beixiayitiao-zhamao.gif", lambda p: load_gif(p)),
        ("holopet-idle_01.gif", lambda p: load_gif(p)),
        ("whale-sprite.webp", lambda p: load_sprite(p, list(range(0, 8)) + list(range(8, 16)))),
        ("mjw-sprite.webp", lambda p: load_sprite(p, list(range(0, 7)) + list(range(8, 16)))),
    ]
    for name, loader in cases:
        src = os.path.join(REF, name)
        if not os.path.exists(src):
            print("skip", name)
            continue
        frames = loader(src)
        out = os.path.join(OUT, "small-" + name.replace(".webp", ".gif"))
        n, size = to_gif(frames, out)
        print("%-34s 帧 %3d -> %2d   体积 %7.1f KB   %s"
              % (name, len(frames), n, size / 1024.0, os.path.basename(out)))


if __name__ == "__main__":
    main()
