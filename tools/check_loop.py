#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 chibi-blue 每个 GIF 的「首尾帧闭环程度」。

对每个 GIF 取首帧与末帧，各自合成到黑底（lum * alpha/255 等价于 paste 到黑底），
算逐像素平均绝对差（0-255 三通道平均）。同时复核体积 / 帧数 / 尺寸 / 透明度。

用法：
  python tools/check_loop.py            # 校验 build/skins/chibi-blue
  python tools/check_loop.py --json out.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "skins" / "chibi-blue"
SPEEDS = ["slow", "normal", "fast"]
MAX_BYTES = 64000
CANVAS = 160
LIMIT = 8.0


def comp_arr(im: Image.Image) -> np.ndarray:
    """合成到黑底：lum * alpha/255。"""
    a = np.asarray(im.convert("RGBA"), dtype=np.float32)
    alpha = a[:, :, 3:4] / 255.0
    return a[:, :, :3] * alpha


def frame_gap(path: Path) -> tuple[float, int, bytes, int]:
    im = Image.open(path)
    n = getattr(im, "n_frames", 1)
    sz = im.size
    data_bytes = path.stat().st_size
    im.seek(0)
    fa = comp_arr(im)
    im.seek(n - 1)
    fb = comp_arr(im)
    mean = float(np.abs(fa - fb).mean())
    return mean, n, data_bytes, sz


def check_one(path: Path) -> dict:
    mean, n, data_bytes, sz = frame_gap(path)
    im = Image.open(path)
    dur = set()
    transp = im.info.get("transparency")
    has_tp = False
    for i in range(min(n, 4)):
        im.seek(i)
        dur.add(im.info.get("duration"))
        if im.mode == "P":
            has_tp = has_tp or (0 in im.tobytes())
    return {
        "file": path.name,
        "speed": path.parent.name,
        "gap": round(mean, 2),
        "frames": n,
        "bytes": data_bytes,
        "size": list(sz),
        "transparency": transp,
        "durations": sorted(d for d in dur if d is not None),
        "transparent_px": has_tp,
    }


def main() -> int:
    rows = []
    for s in SPEEDS:
        d = OUT / s
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.gif")):
            rows.append(check_one(p))

    if not rows:
        print("没有找到 GIF: %s" % OUT)
        return 2

    bad = [r for r in rows if r["gap"] >= LIMIT]
    print("%-24s %-7s %5s %6s %7s %6s %5s %s"
          % ("file", "speed", "gap", "frames", "bytes", "KB", "size", "ok"))
    print("-" * 78)
    for r in rows:
        fails = []
        if r["gap"] >= LIMIT:
            fails.append("loop")
        if r["bytes"] > MAX_BYTES:
            fails.append("bytes")
        if tuple(r["size"]) != (CANVAS, CANVAS):
            fails.append("size")
        if r["transparency"] != 0:
            fails.append("transp")
        if not r["transparent_px"]:
            fails.append("no-tp-px")
        if not (6 <= r["frames"] <= 16):
            fails.append("frames")
        print("%-24s %-7s %5.1f %6d %7d %6.1f %5d %s"
              % (r["file"], r["speed"], r["gap"], r["frames"], r["bytes"],
                 r["bytes"] / 1024.0, r["size"][0], ",".join(fails) if fails else "PASS"))

    # 三档一致性：同一文件三档帧数必须一致（体积可因 duration 相同而相同）
    by_file = {}
    for r in rows:
        by_file.setdefault(r["file"], []).append(r)
    inconsistent = [f for f, rs in by_file.items() if len({r["frames"] for r in rs}) > 1]

    print("-" * 78)
    print("文件 %d 个，总体积 %d B（%.1f KB），最大 %.1f KB"
          % (len(rows), sum(r["bytes"] for r in rows),
             sum(r["bytes"] for r in rows) / 1024.0,
             max(r["bytes"] for r in rows) / 1024.0))
    print("首尾 gap: min %.2f / mean %.2f / max %.2f，超限(>=%.1f) %d 个"
          % (min(r["gap"] for r in rows), sum(r["gap"] for r in rows) / len(rows),
             max(r["gap"] for r in rows), LIMIT, len(bad)))
    if bad:
        print("超限: " + ", ".join("%s(%.1f)" % (r["file"], r["gap"]) for r in sorted(bad, key=lambda r: -r["gap"])))
    if inconsistent:
        print("三档帧数不一致: " + ", ".join(inconsistent))

    if "--json" in sys.argv:
        dst = Path(sys.argv[sys.argv.index("--json") + 1])
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print("JSON -> %s" % dst)

    return 0 if not bad and not inconsistent else 1


if __name__ == "__main__":
    sys.exit(main())
