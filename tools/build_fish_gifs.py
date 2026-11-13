#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 whale-sprite.webp 精灵表切成 HoloCubic / LVGL 能播放的索引 GIF。

硬指标：
  * 输出画布 160x160，角色居中；同一 GIF 内所有帧先求联合包围盒再裁切，
    因此动画不会抖动。
  * 每个 GIF <= 16 帧（本素材每行 4-8 帧，无需抽帧）。
  * 调色板 <= 32 色，保留透明索引（transparency），disposal=2。
  * 单文件 <= 48KB，超出时依次降色、再抽帧，并把最终参数写进 report.md。

用法：直接运行本文件，可重复执行（会覆盖旧产物）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PIL import Image

# ---------------------------------------------------------------- 路径与常量

ROOT = Path(__file__).resolve().parent.parent
SPRITE = ROOT / "assets" / "refs" / "whale-sprite.webp"
OUT_DIR = ROOT / "build" / "fish-assets"
GIF_DIR = OUT_DIR / "status"
MANIFEST = OUT_DIR / "manifest.lua"
REPORT = OUT_DIR / "report.md"

CELL_W, CELL_H = 192, 208
COLS = 8
ROW_FRAMES = [6, 8, 8, 4, 5, 8, 6, 6, 6]  # 每行真实帧数，行尾空格子不要取

CANVAS = 160
PAD = 4              # 内容区四周留白，避免角色贴边
ALPHA_CUT = 128      # 缩放后 alpha 二值化阈值
BBOX_ALPHA = 8       # 求包围盒时忽略极淡边缘噪点

MAX_FRAMES = 16
MAX_COLORS = 32
MAX_BYTES = 48000
DURATION = 90

URL_PREFIX = "/sd/apps/dsh_fish/assets/whale/status/"

# (事件名, 精灵表行, 每个变体的行内起始帧)
EVENT_SPECS = [
    ("Idle", 0, [0, 1, 2, 3]),          # 呼吸，4 个相位轮转
    ("UserPromptSubmit", 0, [4]),       # 收到指令，安静的呼吸相位
    ("PreToolUse", 1, [0]),             # 开始干活（走动）
    ("PostToolUse", 2, [0]),            # 干完一件（走动）
    ("PermissionRequest", 4, [0]),      # 请求确认（举手欢呼）
    ("Error", 3, [0]),                  # 出错（短促站立）
    ("Stop", 4, [1]),                   # 完成（欢呼的另一相位）
    ("SessionStart", 4, [3]),           # 唤醒（欢呼的另一相位）
    ("SubagentStart", 1, [2]),          # 分派子任务（走动）
    ("SubagentStop", 2, [3]),           # 回收子任务（走动）
    ("PreCompact", 5, [0]),             # 整理上下文（悬浮）
    ("PostCompact", 5, [4]),            # 压缩完成（悬浮另一相位）
    ("Sleeping", 6, [0]),               # 休眠（安静站立）
]

COLOR_LADDER = [32, 24, 16, 12, 8]


# ---------------------------------------------------------------- 图像处理


def load_sheet() -> Image.Image:
    if not SPRITE.is_file():
        raise SystemExit("找不到精灵表: %s" % SPRITE)
    sheet = Image.open(SPRITE).convert("RGBA")
    expect = (CELL_W * COLS, CELL_H * len(ROW_FRAMES))
    if sheet.size != expect:
        raise SystemExit("精灵表尺寸 %s != 预期 %s" % (sheet.size, expect))
    return sheet


def extract_frames(sheet: Image.Image, row: int, start: int) -> list[Image.Image]:
    """取该行真实帧数，从 start 开始循环轮转，返回 RGBA 帧列表。"""
    n = ROW_FRAMES[row]
    cells = [
        sheet.crop((c * CELL_W, row * CELL_H, (c + 1) * CELL_W, (row + 1) * CELL_H))
        for c in range(n)
    ]
    return [cells[(start + i) % n] for i in range(n)]


def union_bbox(frames: list[Image.Image]) -> tuple[int, int, int, int]:
    box = None
    for f in frames:
        alpha = f.getchannel("A").point(lambda v: 255 if v >= BBOX_ALPHA else 0)
        b = alpha.getbbox()
        if not b:
            continue
        box = b if box is None else (
            min(box[0], b[0]), min(box[1], b[1]),
            max(box[2], b[2]), max(box[3], b[3]),
        )
    if box is None:
        raise SystemExit("帧全透明，无法裁切")
    return box


def prepare_frames(frames: list[Image.Image]) -> list[Image.Image]:
    """统一裁切 -> 等比缩放 -> 居中放到 160x160 透明画布。"""
    box = union_bbox(frames)
    cropped = [f.crop(box) for f in frames]
    w, h = cropped[0].size
    inner = CANVAS - 2 * PAD
    k = min(inner / float(w), inner / float(h))
    tw = max(1, int(round(w * k)))
    th = max(1, int(round(h * k)))
    ox, oy = (CANVAS - tw) // 2, (CANVAS - th) // 2

    out = []
    for f in cropped:
        alpha = f.getchannel("A").point(lambda v: 255 if v >= ALPHA_CUT else 0)
        f = f.copy()
        f.putalpha(alpha)
        # RGBa 是预乘 alpha，缩放不会在透明边缘产生黑边
        small = f.convert("RGBa").resize((tw, th), Image.LANCZOS).convert("RGBA")
        alpha = small.getchannel("A").point(lambda v: 255 if v >= ALPHA_CUT else 0)
        small.putalpha(alpha)
        canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
        canvas.paste(small, (ox, oy), small)
        out.append(canvas)
    return out


def sample_pixels(frames: list[Image.Image]) -> list[bytes]:
    """收集所有非透明像素的 RGB，最多约 6 万个样本。"""
    pixels: list[bytes] = []
    for f in frames:
        raw = f.tobytes()
        for i in range(0, len(raw), 4):
            if raw[i + 3] >= ALPHA_CUT:
                pixels.append(raw[i:i + 3])
    if not pixels:
        pixels = [b"\x00\x00\x00"]
    step = max(1, len(pixels) // 60000)
    return pixels[::step]


def build_palette(frames: list[Image.Image], colors: int) -> Image.Image:
    """为整段动画建立统一调色板，预留 1 个索引给透明色。"""
    pixels = sample_pixels(frames)
    strip = Image.frombytes("RGB", (len(pixels), 1), b"".join(pixels))
    return strip.quantize(
        colors=colors - 1,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )


def to_indexed(f: Image.Image, palette_img: Image.Image, colors: int) -> Image.Image:
    """把一帧 RGBA 映射到统一调色板：0 号索引固定透明，实际颜色从 1 开始。"""
    alpha = f.getchannel("A").point(lambda v: 255 if v >= ALPHA_CUT else 0)

    solid = Image.new("RGBA", f.size, (0, 0, 0, 255))
    solid.paste(f, (0, 0), alpha)
    p = solid.convert("RGB").quantize(
        palette=palette_img, dither=Image.Dither.NONE
    )
    # quantize 只产出 0..colors-2，整体 +1 让 0 号空出来给透明色
    p = p.point(lambda v: min(colors - 1, v + 1))

    base = palette_img.getpalette()[: (colors - 1) * 3]
    base = base + [0, 0, 0] * (colors - 1 - len(base) // 3)
    p.putpalette([0, 0, 0] + base)

    transparent = alpha.point(lambda v: 255 if v == 0 else 0)
    p.paste(0, mask=transparent)
    return p


def subsample(frames: list[Image.Image], n: int) -> list[Image.Image]:
    if n >= len(frames):
        return frames
    return [frames[int(round(i * (len(frames) - 1) / float(n - 1)))] for i in range(n)]


def encode(frames: list[Image.Image], colors: int, path: Path) -> int:
    palette_img = build_palette(frames, colors)
    indexed = [to_indexed(f, palette_img, colors) for f in frames]
    indexed[0].save(
        path,
        save_all=True,
        append_images=indexed[1:],
        duration=DURATION,
        loop=0,
        disposal=2,
        transparency=0,
        optimize=True,
    )
    return os.path.getsize(path)


# ---------------------------------------------------------------- 校验与报告


def verify_gif(path: Path) -> dict:
    im = Image.open(path)
    n = getattr(im, "n_frames", 1)
    # 必须在 seek 之前读取：seek 会切换帧并可能替换 info
    transparency = im.info.get("transparency")
    duration = im.info.get("duration")
    max_colors = 0
    for i in range(n):
        im.seek(i)
        max_colors = max(max_colors, len(im.getcolors(maxcolors=256) or []))
    return {
        "path": path,
        "size": im.size,
        "frames": n,
        "transparency": transparency,
        "bytes": os.path.getsize(path),
        "duration": duration,
        "colors_used": max_colors,
    }


def emit_manifest(records: list[dict]) -> None:
    lines = [
        "-- Generated by tools/build_fish_gifs.py",
        "return {",
        "  events = {",
    ]
    for event, _row, _starts in EVENT_SPECS:
        files = [r for r in records if r["event"] == event]
        items = ", ".join('"%s%s"' % (URL_PREFIX, r["file"]) for r in files)
        lines.append('    ["%s"] = { %s },' % (event, items))
    lines += [
        "  },",
        "  weather = {},",
        "}",
        "",
    ]
    MANIFEST.write_text("\n".join(lines), encoding="utf-8")


def emit_report(records: list[dict]) -> None:
    total = sum(r["bytes"] for r in records)
    lines = [
        "# fish-assets 构建报告",
        "",
        "源图：`assets/refs/whale-sprite.webp`（1536x1872 RGBA，8 列 x 9 行，"
        "每格 192x208）。",
        "",
        "统一处理：同一 GIF 内所有帧先求 alpha 联合包围盒再裁切，然后等比缩放到 "
        "160x160 画布（内容区 %dx%d，四周留白 %dpx），角色居中。"
        "调色板为整段动画共享的统一调色板，量化上限 %d 色，透明索引固定为 0"
        "（与 holopet 参考素材一致，实际颜色占 1..N）；"
        "`optimize=True`、`loop=0`、`duration=90`、`disposal=2`。"
        % (CANVAS - 2 * PAD, CANVAS - 2 * PAD, PAD, MAX_COLORS),
        "",
        "## 每个 GIF",
        "",
        "| GIF | 事件 | 源帧（行/列 / 全局编号） | 输出帧数 | 实际色数 | 文件大小 | 状态 |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for r in records:
        ok = "OK" if r["bytes"] <= MAX_BYTES else "**超过 48KB**"
        lines.append(
            "| `%s` | %s | %s | %d | %d | %.1f KB | %s |"
            % (
                r["file"],
                r["event"],
                r["source_note"],
                r["n_frames"],
                r["verify"]["colors_used"],
                r["bytes"] / 1024.0,
                ok,
            )
        )
    lines += [
        "",
        "## 汇总",
        "",
        "- GIF 总数：**%d**" % len(records),
        "- 总体积：**%.1f KB**（%d 字节）" % (total / 1024.0, total),
        "- 单文件上限：48 KB；最大单文件：**%.1f KB**（`%s`）"
        % (
            max(r["bytes"] for r in records) / 1024.0,
            max(records, key=lambda r: r["bytes"])["file"],
        ),
        "- 全部文件 <= 48KB：**%s**"
        % ("是" if all(r["bytes"] <= MAX_BYTES for r in records) else "否"),
        "",
        "## 实际使用的抽帧 / 降色参数",
        "",
    ]
    changed = [r for r in records if r["n_frames"] != r["source_frames"] or r["colors"] != MAX_COLORS]
    if not changed:
        lines.append(
            "- 全部 GIF 使用完整帧数，量化调色板上限 %d 色，未触发降级。"
            % MAX_COLORS
        )
    else:
        for r in changed:
            lines.append(
                "- `%s`：源 %d 帧 -> %d 帧，%d 色。"
                % (r["file"], r["source_frames"], r["n_frames"], r["colors"])
            )
    lines += [
        "",
        "## 校验",
        "",
    ]
    for r in records:
        v = r["verify"]
        ok = (
            v["size"] == (CANVAS, CANVAS)
            and v["transparency"] is not None
            and v["bytes"] <= MAX_BYTES
        )
        lines.append(
            "- `%s`：%s，%d 帧，transparency=%s，%.1f KB -> %s"
            % (
                r["file"],
                "x".join(str(x) for x in v["size"]),
                v["frames"],
                v["transparency"],
                v["bytes"] / 1024.0,
                "PASS" if ok else "FAIL",
            )
        )
    lines.append("")
    REPORT.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------- 主流程


def main() -> int:
    sheet = load_sheet()
    GIF_DIR.mkdir(parents=True, exist_ok=True)
    for old in GIF_DIR.glob("*.gif"):
        old.unlink()

    records: list[dict] = []
    for event, row, starts in EVENT_SPECS:
        for vi, start in enumerate(starts, 1):
            base = extract_frames(sheet, row, start)
            prepared = prepare_frames(base)
            source_frames = len(base)
            source_cols = [(start + i) % source_frames for i in range(source_frames)]
            cmin, cmax = min(source_cols), max(source_cols)
            source_note = "r%d c%d-c%d (#%d-#%d)" % (
                row, cmin, cmax, row * COLS + cmin, row * COLS + cmax
            )
            if source_cols != sorted(source_cols):
                source_note += " (start c%d)" % start

            filename = "%s_%02d.gif" % (event.lower(), vi)
            path = GIF_DIR / filename

            frame_ladder = sorted(
                set([min(source_frames, MAX_FRAMES)] + [x for x in (8, 6, 4, 3) if x < source_frames]),
                reverse=True,
            )
            chosen = None
            for nframes in frame_ladder:
                seq = subsample(prepared, nframes)
                for colors in COLOR_LADDER:
                    size = encode(seq, colors, path)
                    if size <= MAX_BYTES:
                        chosen = (nframes, colors, size)
                        break
                if chosen:
                    break
            if not chosen:
                raise SystemExit("%s 在最低参数下仍超过 48KB" % filename)

            nframes, colors, size = chosen
            rec = {
                "event": event,
                "file": filename,
                "row": row,
                "source_start": start,
                "source_frames": source_frames,
                "source_note": source_note,
                "n_frames": nframes,
                "colors": colors,
                "bytes": size,
                "verify": verify_gif(path),
            }
            records.append(rec)
            print(
                "%-24s row %d c%-2d  %d->%d 帧  %2d 色  %6.1f KB"
                % (filename, row, start, source_frames, nframes, colors, size / 1024.0)
            )

    emit_manifest(records)
    emit_report(records)
    print("\n输出目录: %s" % OUT_DIR)
    print("GIF %d 个，总体积 %.1f KB" % (len(records), sum(r["bytes"] for r in records) / 1024.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
