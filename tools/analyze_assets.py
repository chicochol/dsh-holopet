# -*- coding: utf-8 -*-
"""检查各路线素材的尺寸、帧数、透明通道情况。"""
import os
import glob
from PIL import Image

REF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "refs")


def alpha_stats(im):
    """返回 (透明像素占比, 是否四角透明)。"""
    rgba = im.convert("RGBA")
    a = rgba.split()[-1]
    hist = a.histogram()
    tot = sum(hist)
    trans = sum(hist[:8])
    w, h = rgba.size
    px = rgba.load()
    corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    return 100.0 * trans / tot, all(c[3] < 8 for c in corners)


def bbox_union(im, step=1):
    """所有帧的联合包围盒（去掉全透明边）。"""
    box = None
    n = getattr(im, "n_frames", 1)
    for i in range(0, n, step):
        im.seek(i)
        b = im.convert("RGBA").getbbox()
        if b:
            box = b if box is None else (
                min(box[0], b[0]), min(box[1], b[1]),
                max(box[2], b[2]), max(box[3], b[3]))
    return box


for f in sorted(glob.glob(os.path.join(REF, "*.gif"))):
    im = Image.open(f)
    pct, corner_ok = alpha_stats(im)
    b = bbox_union(im, step=max(1, getattr(im, "n_frames", 1) // 12))
    print("%-34s %-4s %dx%d frames=%-3d trans=%5.1f%% corners=%s bbox=%s"
          % (os.path.basename(f), im.format, im.size[0], im.size[1],
             getattr(im, "n_frames", 1), pct, "T" if corner_ok else "F", b))

for f, cw, ch, cols in [
        ("mjw-sprite.webp", 192, 208, 8),
        ("whale-sprite.webp", 192, 208, 8)]:
    im = Image.open(os.path.join(REF, f)).convert("RGBA")
    print("\n%s %dx%d -> cell %dx%d, grid %dx%d"
          % (f, im.size[0], im.size[1], cw, ch, cols, im.size[1] // ch))
    for idx in range(6):
        r, c = divmod(idx, cols)
        cell = im.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch))
        a = cell.split()[-1]
        hist = a.histogram()
        print("   frame%-2d trans=%5.1f%% bbox=%s"
              % (idx, 100.0 * sum(hist[:8]) / sum(hist), cell.getbbox()))
