#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""独立自检：不依赖构建脚本，直接解析 GIF 字节流 + Pillow 读回，验证 chibi-blue 皮肤。

检查项：
  1. 目录里 16 个事件文件 x 3 档都在，manifest.lua 与实际文件一致；
  2. 每个 GIF：逻辑屏幕 160x160、帧数 > 1、单文件 <= 40000 字节；
  3. 图形控制扩展：disposal=2、透明标志位开、透明索引=0、delay 与档位一致；
  4. 帧数、像素内容在三档之间完全一致（只有 delay 不同）；
  5. 每帧色数 <= 32，首帧存在透明像素（索引 0）。

用法：python tools/verify_pet_skin.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SKIN = ROOT / "build" / "skins" / "chibi-blue"
SPEEDS = {"slow": 150, "normal": 120, "fast": 90}
MAX_BYTES = 64000

EXPECTED_EVENTS = {
    "Idle": ["idle_01.gif", "idle_02.gif", "idle_03.gif", "idle_04.gif"],
    "UserPromptSubmit": ["userpromptsubmit.gif"],
    "PreToolUse": ["pretooluse.gif"],
    "PostToolUse": ["posttooluse.gif"],
    "PermissionRequest": ["permissionrequest.gif"],
    "Error": ["error.gif"],
    "Stop": ["stop.gif"],
    "SessionStart": ["sessionstart.gif"],
    "SubagentStart": ["subagentstart.gif"],
    "SubagentStop": ["subagentstop.gif"],
    "PreCompact": ["precompact.gif"],
    "PostCompact": ["postcompact.gif"],
    "Sleeping": ["sleeping.gif"],
}


def parse_gif_blocks(data: bytes) -> dict:
    """最简 GIF 解析：返回逻辑屏幕尺寸与每帧图形控制扩展信息。"""
    assert data[:6] in (b"GIF87a", b"GIF89a"), "不是 GIF"
    width = int.from_bytes(data[6:8], "little")
    height = int.from_bytes(data[8:10], "little")
    packed = data[10]
    pos = 13
    if packed & 0x80:                       # 全局色表
        pos += 3 * (2 ** ((packed & 0x07) + 1))

    frames = []
    gce = None
    while pos < len(data):
        block = data[pos]
        pos += 1
        if block == 0x3B:                   # trailer
            break
        if block == 0x21:                   # 扩展
            label = data[pos]
            pos += 1
            if label == 0xF9:
                size = data[pos]
                sub = data[pos + 1: pos + 1 + size]
                packed_gce = sub[0]
                gce = {
                    "disposal": (packed_gce >> 2) & 0x07,
                    "transparent": bool(packed_gce & 0x01),
                    "delay_cs": int.from_bytes(sub[1:3], "little"),
                    "transparent_index": sub[3],
                }
                pos += 1 + size
                pos += 1                    # 子块终止符 0x00
            else:
                while pos < len(data) and data[pos]:
                    pos += data[pos] + 1
                pos += 1
        elif block == 0x2C:                 # 图像描述符
            pos += 8                        # left/top/width/height
            img_packed = data[pos]
            pos += 1
            if img_packed & 0x80:
                pos += 3 * (2 ** ((img_packed & 0x07) + 1))
            pos += 1                        # LZW 最小码长
            while pos < len(data) and data[pos]:
                pos += data[pos] + 1
            pos += 1
            frames.append(dict(gce or {"disposal": 0, "transparent": False,
                                       "delay_cs": 0, "transparent_index": 0}))
        else:
            raise ValueError("未知块 0x%02X @%d" % (block, pos - 1))
    return {"width": width, "height": height, "frames": frames}


def check_one(path: Path, speed: str) -> dict:
    want_delay = SPEEDS[speed] // 10
    data = path.read_bytes()
    info = parse_gif_blocks(data)
    im = Image.open(path)
    transparency = im.info.get("transparency")     # 必须在 seek 之前取
    n = im.n_frames
    colors, transparent_px = 0, False
    for i in range(n):
        im.seek(i)
        colors = max(colors, len(im.getcolors(maxcolors=256) or []))
        if i == 0 and im.mode == "P":
            transparent_px = 0 in im.tobytes()
    problems = []
    if info["width"] != 160 or info["height"] != 160:
        problems.append("逻辑屏幕 %dx%d" % (info["width"], info["height"]))
    if len(info["frames"]) != n:
        problems.append("块解析帧数 %d != Pillow %d" % (len(info["frames"]), n))
    if n <= 1:
        problems.append("帧数 %d" % n)
    if len(data) > MAX_BYTES:
        problems.append("体积 %d" % len(data))
    if colors > 32:
        problems.append("色数 %d" % colors)
    if not transparent_px:
        problems.append("首帧无透明像素")
    if im.info.get("transparency", transparency) != 0 or transparency != 0:
        problems.append("transparency=%r" % transparency)
    for i, f in enumerate(info["frames"]):
        if f["disposal"] != 2:
            problems.append("第%d帧 disposal=%d" % (i, f["disposal"]))
        if not f["transparent"] or f["transparent_index"] != 0:
            problems.append("第%d帧透明标志/索引 %r" % (i, f))
        if f["delay_cs"] != want_delay:
            problems.append("第%d帧 delay=%dcs 应为 %d" % (i, f["delay_cs"], want_delay))
    return {"path": path, "n": n, "bytes": len(data), "colors": colors,
            "problems": problems, "frames": info["frames"]}


def first_frame_bytes(path: Path) -> bytes:
    im = Image.open(path)
    im.seek(0)
    return im.convert("RGBA").tobytes()


def main() -> int:
    if not SKIN.is_dir():
        print("找不到目录", SKIN)
        return 2
    problems_total = 0
    files = []
    for speed in SPEEDS:
        d = SKIN / speed
        got = sorted(p.name for p in d.glob("*.gif"))
        want = sorted(f for fs in EXPECTED_EVENTS.values() for f in fs)
        if got != want:
            print("[%s] 文件集合不一致：缺 %s / 多 %s"
                  % (speed, sorted(set(want) - set(got)), sorted(set(got) - set(want))))
            problems_total += 1
        for name in want:
            p = d / name
            if not p.is_file():
                continue
            r = check_one(p, speed)
            files.append((speed, name, r))
            if r["problems"]:
                problems_total += 1
                print("[FAIL] %s/%s  %s" % (speed, name, "; ".join(r["problems"][:6])))

    # 三档帧内容必须一致
    by_name: dict[str, dict] = {}
    for speed, name, r in files:
        by_name.setdefault(name, {})[speed] = r
    for name, per in by_name.items():
        counts = {s: r["n"] for s, r in per.items()}
        if len(set(counts.values())) != 1:
            print("[FAIL] %s 三档帧数不一致 %s" % (name, counts))
            problems_total += 1
            continue
        base = per["normal"]["path"]
        base_bytes = first_frame_bytes(base)
        for s in ("slow", "fast"):
            if first_frame_bytes(per[s]["path"]) != base_bytes:
                print("[FAIL] %s %s 档首帧像素与 normal 不同" % (name, s))
                problems_total += 1
        for s, r in per.items():
            if r["colors"] != per["normal"]["colors"] or r["n"] != per["normal"]["n"]:
                print("[FAIL] %s %s 档色数/帧数与 normal 不同" % (name, s))
                problems_total += 1

    # manifest 一致性
    man = (SKIN / "manifest.lua").read_text(encoding="utf-8")
    m_events = dict(re.findall(r'\["(\w+)"\]\s*=\s*\{([^}]*)\}', man))
    if set(m_events) != set(EXPECTED_EVENTS):
        print("[FAIL] manifest 事件集合不符:", sorted(set(m_events) ^ set(EXPECTED_EVENTS)))
        problems_total += 1
    for ev, body in m_events.items():
        names = re.findall(r'"([^"]+\.gif)"', body)
        if names != EXPECTED_EVENTS.get(ev):
            print("[FAIL] manifest %s 文件列表 %s" % (ev, names))
            problems_total += 1
        for name in names:
            for speed in SPEEDS:
                if not (SKIN / speed / name).is_file():
                    print("[FAIL] manifest 引用了不存在的 %s/%s" % (speed, name))
                    problems_total += 1
    for key in ('id = "chibi-blue"', "speeds = { slow = 150, normal = 120, fast = 90 }",
                'default_speed = "normal"', "weather = {}"):
        if key not in man:
            print("[FAIL] manifest 缺少:", key)
            problems_total += 1

    total = sum(r["bytes"] for _, _, r in files)
    print("\n文件 %d 个，合计 %d B（%.1f KB），最大 %d B（%.1f KB）"
          % (len(files), total, total / 1024.0,
             max(r["bytes"] for _, _, r in files), max(r["bytes"] for _, _, r in files) / 1024.0))
    for s in SPEEDS:
        sub = [r for sp, _, r in files if sp == s]
        print("  %-6s %2d 个  %6d B  (%.1f KB)"
              % (s, len(sub), sum(x["bytes"] for x in sub), sum(x["bytes"] for x in sub) / 1024.0))
    print("问题数：%d" % problems_total)
    return 0 if problems_total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
