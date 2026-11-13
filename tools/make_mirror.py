#!/usr/bin/env python3
"""为皮肤生成水平镜像版待机素材。

角色在屏幕里左右走动，撞到边缘掉头时如果只改移动方向、不改朝向，看起来
就是"倒着走"。这里把 idles 的每一帧左右翻转，设备端朝左走时换用这套素材，
视觉上就是一次转身。

产物：build/dsh_fish/assets/skins/<id>/mirror/<speed>/idle_*.gif
"""

import os
import sys
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKINS = os.path.join(ROOT, "build", "dsh_fish", "assets", "skins")
SPEEDS = ("slow", "normal", "fast")


def mirror_gif(src, dst):
    im = Image.open(src)
    frames, durations = [], []
    n = getattr(im, "n_frames", 1)
    for i in range(n):
        im.seek(i)
        # P 模式直接翻转索引即可，调色板和透明索引都不受影响
        frame = im.copy()
        if frame.mode != "P":
            frame = frame.convert("P")
        frames.append(frame.transpose(Image.FLIP_LEFT_RIGHT))
        durations.append(im.info.get("duration", 120))
    if not frames:
        return 0
    trans = im.info.get("transparency", 0)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    frames[0].save(
        dst,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        disposal=2,
        transparency=trans,
        optimize=False,
    )
    return len(frames)


def main():
    total = 0
    skipped = []
    for skin in sorted(os.listdir(SKINS)):
        skin_dir = os.path.join(SKINS, skin)
        if not os.path.isdir(skin_dir):
            continue
        for speed in SPEEDS:
            src_dir = os.path.join(skin_dir, speed)
            if not os.path.isdir(src_dir):
                continue
            for name in sorted(os.listdir(src_dir)):
                if not (name.startswith("idle") and name.endswith(".gif")):
                    continue
                src = os.path.join(src_dir, name)
                dst = os.path.join(skin_dir, "mirror", speed, name)
                n = mirror_gif(src, dst)
                size = os.path.getsize(dst)
                total += 1
                print(f"{skin}/{speed}/{name}  {n}f  {size/1024:.1f}KB")
                if size > 48000:
                    skipped.append(f"{skin}/{speed}/{name}")
    print(f"\nmirrored {total} files")
    if skipped:
        print("over 48KB: " + ", ".join(skipped))


if __name__ == "__main__":
    main()
