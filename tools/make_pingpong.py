#!/usr/bin/env python3
"""把指定动作做成"来回播放"的 GIF（0,1,2,...,n-1,n-2,...,1）。

鲸鱼娘皮肤里 row4 的 5 帧行（PermissionRequest / Stop / SessionStart）首尾轮廓
差得远，无论怎么换窗口都闭不了环。把这几段改成往返播放后，末帧自然接回首帧，
循环点看不到跳变。

用法：
    python tools/make_pingpong.py stop_01.gif permissionrequest_01.gif sessionstart_01.gif
"""

import os
import sys
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = [
    ("whale", ("slow", "normal", "fast")),
]


def pingpong(src, dst):
    im = Image.open(src)
    n = getattr(im, "n_frames", 1)
    if n < 3:
        return n, 0
    frames, duration = [], im.info.get("duration", 120)
    for i in range(n):
        im.seek(i)
        frames.append(im.copy())
    order = list(range(n)) + list(range(n - 2, 0, -1))
    out = [frames[i] for i in order]
    trans = im.info.get("transparency", 0)
    out[0].save(
        dst,
        save_all=True,
        append_images=out[1:],
        duration=duration,
        loop=0,
        disposal=2,
        transparency=trans,
        optimize=False,
    )
    return n, len(out)


def main():
    names = sys.argv[1:]
    if not names:
        names = ["stop_01.gif", "permissionrequest_01.gif", "sessionstart_01.gif"]
    changed = 0
    for skin, speeds in SOURCES:
        for speed in speeds:
            d = os.path.join(ROOT, "build", "dsh_fish", "assets", "skins", skin, speed)
            for name in names:
                p = os.path.join(d, name)
                if not os.path.exists(p):
                    print(f"missing {p}")
                    continue
                before = os.path.getsize(p)
                src_n, out_n = pingpong(p, p)
                after = os.path.getsize(p)
                changed += 1
                print(f"{skin}/{speed}/{name}: {src_n}f -> {out_n}f, {before/1024:.1f}KB -> {after/1024:.1f}KB")
    print(f"\npingpong applied to {changed} files")


if __name__ == "__main__":
    main()
