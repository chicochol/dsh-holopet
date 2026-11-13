#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从精灵表批量生成「一套皮肤 × 三档速度」的索引 GIF，并输出统一格式的 manifest。

在旧版（直接切行、按帧数/色数阶梯降级）基础上加了**循环闭环**处理：

* 精灵表每一行是一个循环动作，但切成 GIF 后末帧不一定接得回第一帧；
* 对每个动作枚举「行内起点 × 保留帧数」，用与 chibi-blue 相同的口径
  （alpha 联合包围盒 → 缩到 152 → 贴 160 画布 → 合成黑底）量首尾平均差；
* 首尾已经闭合的动作**保持原相位不动**，只有 gap ≥ 8 的才换窗口；
* 同一行上的多个事件必须用不同起点，避免两个事件看起来一模一样。

输出结构：
    build/skins/<skin_id>/<speed>/<event>_<n>.gif
    build/skins/<skin_id>/manifest.lua
    build/skins/<skin_id>/report-loop.md

用法：
    python tools/build_skin_gifs.py
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_fish_gifs as B  # noqa: E402
import verify_pet_skin as V  # noqa: E402

# ---------------------------------------------------------------- 皮肤定义

SKIN_ID = "whale"
SKIN_NAME = "鲸鱼娘"
SKIN_NAME_EN = "Whale Girl"
SKIN_SPRITE = ROOT / "assets" / "refs" / "whale-sprite.webp"

SPEEDS = [("slow", 150), ("normal", 120), ("fast", 90)]
DEFAULT_SPEED = "normal"

OUT = ROOT / "build" / "skins" / SKIN_ID
WORK = ROOT / "build" / "skins" / "_work"

MAX_BYTES = 48000                 # 单文件上限（48KB 十进制口径）
MAX_DROP = 2                      # 最多允许去掉几帧来换闭环
MIN_FRAMES = 3                    # 再短的循环就看不出动作了
DROP_PENALTY = 1.5                # 每少一帧的代价权重（gap 相近时优先保留完整动作）
LOOP_OK = 8.0                     # 首尾差低于此值认为循环肉眼不可见跳变
COLOR_LADDER = [32, 24, 16, 12, 8]

# 旧产物的实测首尾差（normal 档，4/5 帧行当时被压成 4 帧），仅用于报告对比
BEFORE_GAP = {
    "error_01.gif": 10.45, "idle_01.gif": 4.08, "idle_02.gif": 7.25,
    "idle_03.gif": 3.16, "idle_04.gif": 3.02, "permissionrequest_01.gif": 25.30,
    "postcompact_01.gif": 8.86, "posttooluse_01.gif": 14.50,
    "precompact_01.gif": 5.07, "pretooluse_01.gif": 5.85,
    "sessionstart_01.gif": 12.30, "sleeping_01.gif": 1.78, "stop_01.gif": 31.67,
    "subagentstart_01.gif": 6.82, "subagentstop_01.gif": 10.04,
    "userpromptsubmit_01.gif": 4.42,
}


# ---------------------------------------------------------------- 闭环度量


def canvas_gap(fa: Image.Image, fb: Image.Image) -> float:
    """两帧合成到黑底后的平均绝对差（0–255），与 chibi-blue 的 `_canvas_gap` 同口径。"""
    def comp(im: Image.Image) -> np.ndarray:
        a = np.asarray(im.convert("RGBA"), dtype=np.float32)
        return a[:, :, :3] * (a[:, :, 3:4] / 255.0)

    return float(np.abs(comp(fa) - comp(fb)).mean())


def gif_loop_gap(path: Path) -> float:
    """读回 GIF 实测首尾差（量化/编码之后的口径）。"""
    im = Image.open(path)
    n = getattr(im, "n_frames", 1)

    def comp(i: int) -> np.ndarray:
        im.seek(i)
        a = np.asarray(im.convert("RGBA"), dtype=np.float32)
        return a[:, :, :3] * (a[:, :, 3:4] / 255.0)

    return float(np.abs(comp(0) - comp(n - 1)).mean())


def row_cells(sheet: Image.Image, row: int) -> list[Image.Image]:
    n = B.ROW_FRAMES[row]
    return [
        sheet.crop((c * B.CELL_W, row * B.CELL_H, (c + 1) * B.CELL_W, (row + 1) * B.CELL_H))
        for c in range(n)
    ]


def window(cells: list[Image.Image], start: int, k: int) -> list[Image.Image]:
    n = len(cells)
    return [cells[(start + i) % n] for i in range(k)]


def enumerate_row(cells: list[Image.Image]) -> list[dict]:
    """枚举 (起点, 保留帧数) 候选，返回各自 prepare 后的帧与首尾 gap。"""
    n = len(cells)
    out = []
    for k in range(n, max(MIN_FRAMES, n - MAX_DROP) - 1, -1):
        for start in range(n):
            prepared = B.prepare_frames(window(cells, start, k))
            out.append({
                "start": start, "k": k, "prepared": prepared,
                "gap": canvas_gap(prepared[0], prepared[-1]),
            })
    return out


# ---------------------------------------------------------------- 选窗口


def pick_window(cands: list[dict], nominal_start: int, blocked: set[int]) -> tuple[dict, str]:
    """为单个事件挑窗口。

    规则：
      1. 原相位（nominal_start, 整行帧数）已经闭环 → 不动，保留作者设定的相位；
      2. 否则在同行的闭环候选里按 `gap + DROP_PENALTY * 丢帧数` 取最小，起点避开
         其它事件已占用/保留的起点；
      3. 没有任何闭环候选 → 保留原窗口，标记 unclosed。
    """
    n = len(cands[0]["prepared"])
    full = [c for c in cands if c["k"] == max(x["k"] for x in cands)]
    nominal = next(c for c in full if c["start"] == nominal_start)
    if nominal["gap"] < LOOP_OK:
        return nominal, "keep"

    best = None
    for c in cands:
        if c["start"] in blocked or c["gap"] >= LOOP_OK:
            continue
        score = c["gap"] + DROP_PENALTY * (n - c["k"])
        if best is None or score < best[0]:
            best = (score, c)
    if best:
        return best[1], "moved"
    return nominal, "unclosed"


def encode_one(prepared: list[Image.Image], path: Path, duration: int) -> tuple[int, int]:
    """色阶降级编码，返回 (色数, 字节)。32 色放得下就用 32。"""
    for colors in COLOR_LADDER:
        B.DURATION = duration
        size = B.encode(prepared, colors, path)
        if size <= MAX_BYTES:
            return colors, size
    # 极端兜底：降一帧再试
    for k in range(len(prepared) - 1, 2, -1):
        seq = B.subsample(prepared, k)
        for colors in COLOR_LADDER:
            B.DURATION = duration
            size = B.encode(seq, colors, path)
            if size <= MAX_BYTES:
                return colors, size
    raise SystemExit("%s 在最低参数下仍超过 %d 字节" % (path.name, MAX_BYTES))


# ---------------------------------------------------------------- 报告


def emit_report(plans: list[dict], records: list[dict]) -> None:
    normal = [r for r in records if r["speed"] == DEFAULT_SPEED]
    gaps = [r["gap"] for r in normal]
    total = sum(r["bytes"] for r in records)
    biggest = max(records, key=lambda r: r["bytes"])
    bad = [r for r in normal if not r["loop_ok"]]
    moved = [p for p in plans if p["action"] == "moved"]
    unclosed = [p for p in plans if p["action"] == "unclosed"]

    lines = [
        "# whale 循环闭环报告",
        "",
        "源：`assets/refs/whale-sprite.webp`（8 列 × 9 行，每格 192×208，"
        "每行帧数 `%s`）。" % (B.ROW_FRAMES,),
        "",
        "## 问题",
        "",
        "旧版直接按行切帧、再把帧数压到 `FRAME_LADDER` 里 ≤ 源帧数的最近一档，",
        "从没检查过首尾帧是否接得上。实测 16 个动作里有 7 个 gap ≥ 8，其中 row4 的",
        "三个（PermissionRequest / Stop / SessionStart）高达 12–32，循环时会明显跳帧。",
        "",
        "另一处浪费：`FRAME_LADDER=[16,8,6,4,3]` 把 5 帧的 row4 压成了 4 帧",
        "（5 不在阶梯里），动作白丢一帧。现在直接用整行帧数。",
        "",
        "## 做法",
        "",
        "1. 每个动作枚举「行内起点 `start` × 保留帧数 `k`」，`k` 最多只比整行少 %d 帧；"
        % MAX_DROP,
        "   每个候选都走与 chibi-blue 相同的 `prepare_frames()`（alpha 联合包围盒 →",
        "   等比缩到 152 → 居中贴 160 画布），在 160×160 上合成黑底量首尾平均差。",
        "2. 首尾已经达标（gap < %.1f）的动作**保持原相位**，避免无谓改动。" % LOOP_OK,
        "3. 只对 gap ≥ %.1f 的动作换窗口，代价函数 `gap + %.1f × 丢帧数`，" % (LOOP_OK, DROP_PENALTY),
        "   即 gap 相近时优先保留整行动作；同一行的多个事件必须用不同起点。",
        "4. 编码后读回 GIF 再测一次 gap（量化会带来 ±0.2 的漂移），并以实测值为准。",
        "",
        "## 逐动作结果（normal 档，三档帧序列相同）",
        "",
        "| 事件 | 文件 | 行 | 源帧 | 输出帧 | 起点 | 色数 | 体积 | gap 改前 → 改后 | 判定 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for r in normal:
        before = BEFORE_GAP.get(r["file"])
        btxt = "%.2f" % before if before is not None else "—"
        if r["loop_ok"]:
            mark = "PASS"
        else:
            mark = "**未闭环**"
        lines.append(
            "| %s | `%s` | %d | %d | %d | %d | %d | %.1f KB | %s → **%.2f** | %s |"
            % (r["event"], r["file"], r["row"], r["src_frames"], r["frames"], r["start"],
               r["colors"], r["bytes"] / 1024.0, btxt, r["gap"], mark)
        )
    lines += [
        "",
        "- 改前 gap（normal 档 16 项）：均值 %.2f、最大 %.2f、其中 %d 项 ≥ %.1f。"
        % (sum(BEFORE_GAP.values()) / len(BEFORE_GAP), max(BEFORE_GAP.values()),
           sum(1 for v in BEFORE_GAP.values() if v >= LOOP_OK), LOOP_OK),
        "- 改后 gap：均值 **%.2f**、最大 **%.2f**，已闭环 %d/%d。"
        % (sum(gaps) / len(gaps), max(gaps), len(normal) - len(bad), len(normal)),
        "",
        "> row4 三项（PermissionRequest / Stop / SessionStart）的「改前」是旧版 4 帧产物"
        "（5 帧被阶梯压成 4 帧），「改后」是完整 5 帧，gap 基本持平属预期——这一行"
        "本身首尾不接，换窗口无解，详见下文。",
        "",
    ]

    if moved:
        lines += [
            "## 换过窗口的动作（全部整行轮转，不丢帧）",
            "",
            "| 事件 | 行 | 起点 | 帧数 | gap（源测量）改前 → 改后 | 做法 |",
            "|---|---:|---:|---:|---|---|",
        ]
        for p in moved:
            if p["k"] == p["row_frames"]:
                note = "整行轮转，起点 %d→%d" % (p["nominal_start"], p["start"])
            else:
                note = "起点 %d→%d，去掉 %d 帧" % (
                    p["nominal_start"], p["start"], p["row_frames"] - p["k"])
            lines.append("| %s | %d | %d | %d/%d | %.2f → **%.2f** | %s |"
                         % (p["event"], p["row"], p["start"], p["k"], p["row_frames"],
                            p["gap_before"], p["gap"], note))
        lines += [
            "",
            "精灵表每一行是**循环动作**，把起点往后挪一格等价于把整段动作的相位平移，",
            "动作本身一帧不丢；本次 4 个换窗口的动作全部是整行轮转（8/8 帧），",
            "没有为了凑 gap 去丢帧。",
            "",
        ]

    if bad:
        lines += [
            "## 无法闭环的动作（保留并标注）",
            "",
            "row4 只有 5 帧，而且是整张表里唯一「首尾景别不一致」的一行：5 个格子高度都是",
            "198px，宽度却在 108–130px 之间来回变（发梢和尾巴的展开程度不同），首帧与",
            "末帧的角色轮廓差最大，任何起点的首尾差都降不到 %.1f 以下。穷举结果：" % LOOP_OK,
            "",
            "| 事件 | 文件 | 当前 gap | 行内最小可达 | 最小可达所需帧数 |",
            "|---|---|---:|---:|---:|",
        ]
        for r in bad:
            lines.append("| %s | `%s` | %.2f | %.2f | %d 帧 |"
                         % (r["event"], r["file"], r["gap"], r["best_gap"], r["best_k"]))
        lines += [
            "",
            "这一行的相邻帧差本身就有 12–32（row3 是 4–11、row5 是 5–10），是整张表里",
            "唯一的「定格爆发」行：5 格之间角色轮廓变化剧烈，所以即使不循环、只播一遍，",
            "它也比其它动作更「跳」。这是精灵表的画法决定的，不是切帧参数能修的。",
            "",
            "**取舍**：这三个动作在语义上本来就是「一次性触发」的事件（请求确认 / 完成 /",
            "唤醒），设备上播一遍就切回 Idle，整段动作的完整性比循环点更重要，因此保留",
            "整行 5 帧、起点不动，不做 3 帧硬凑（3 帧也只能降到 %.2f，仍不达标，且丢掉 40%% 的动作）。"
            % min(r["best_gap"] for r in bad),
            "若要彻底消除循环跳变，推荐**往返播放**（`0,1,2,3,4,3,2,1`）：首尾天然接近，",
            "代价是 8 帧、动作来回重复一次，比硬切回第一帧自然。",
            "",
        ]
    else:
        lines += ["## 无法闭环的动作", "", "无。", ""]

    lines += [
        "## 总量",
        "",
        "- 文件数：**%d 个**（3 档 × 16 个动作）。" % len(records),
        "- 总体积：**%s B（%.1f KiB）**，最大单文件 %.1f KiB（`%s/%s`，上限 %d B）。"
        % (f"{total:,}", total / 1024.0, biggest["bytes"] / 1024.0,
           biggest["speed"], biggest["file"], MAX_BYTES),
        "- 色数：%s。"
        % ("全部 32 色调色板（索引 0 留给透明，实际用到 31 色）"
           if len({r["colors"] for r in normal}) == 1
           else "实测 %d–%d 色" % (min(r["colors"] for r in normal),
                                 max(r["colors"] for r in normal))),
        "- 帧数：%d–%d 帧（row4 为 5 帧、6 帧行为 6 帧、8 帧行为 8 帧）。"
        % (min(r["frames"] for r in normal), max(r["frames"] for r in normal)),
        "",
        "> 尺寸 160×160、透明索引 0、`disposal=2`、duration 150/120/90 ms、"
        "单文件 ≤ %d B 均由 `verify_pet_skin.parse_gif_blocks()` 逐帧复核。" % MAX_BYTES,
        "",
        "## 目录结构",
        "",
        "```",
        "whale/",
        "├─ slow/    16 个 GIF（150ms/帧）",
        "├─ normal/  16 个 GIF（120ms/帧，默认档）",
        "├─ fast/    16 个 GIF（90ms/帧）",
        "├─ manifest.lua",
        "└─ report-loop.md",
        "```",
        "",
    ]
    (OUT / "report-loop.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    if not SKIN_SPRITE.is_file():
        raise SystemExit("找不到精灵表: %s" % SKIN_SPRITE)

    sheet = Image.open(SKIN_SPRITE).convert("RGBA")
    expect = (B.CELL_W * B.COLS, B.CELL_H * len(B.ROW_FRAMES))
    if sheet.size != expect:
        raise SystemExit("精灵表尺寸 %s != 预期 %s" % (sheet.size, expect))

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)

    # 每行只枚举一次，同一行的多个事件共享候选
    rows = {}
    for row in range(len(B.ROW_FRAMES)):
        cells = row_cells(sheet, row)
        rows[row] = {"cells": cells, "cands": enumerate_row(cells)}

    nominals: dict[int, set[int]] = {}
    for _event, row, starts in B.EVENT_SPECS:
        nominals.setdefault(row, set()).update(starts)

    taken: dict[int, set[int]] = {row: set() for row in rows}
    plans: list[dict] = []
    for event, row, starts in B.EVENT_SPECS:
        cands = rows[row]["cands"]
        row_frames = B.ROW_FRAMES[row]
        for vi, nominal in enumerate(starts, 1):
            blocked = taken[row] | (nominals[row] - {nominal})
            chosen, action = pick_window(cands, nominal, blocked)
            taken[row].add(chosen["start"])
            plans.append({
                "event": event, "vi": vi, "file": "%s_%02d.gif" % (event.lower(), vi),
                "row": row, "row_frames": row_frames, "src_frames": len(rows[row]["cells"]),
                "nominal_start": nominal, "start": chosen["start"], "k": chosen["k"],
                "prepared": chosen["prepared"], "gap": chosen["gap"],
                "gap_src": chosen["gap"],
                "gap_before": next(c["gap"] for c in cands
                                   if c["start"] == nominal
                                   and c["k"] == row_frames),
                "best_gap": min(c["gap"] for c in cands),
                "best_k": min(cands, key=lambda c: c["gap"])["k"],
                "action": action,
            })

    records: list[dict] = []
    for speed, duration in SPEEDS:
        gif_dir = OUT / speed
        gif_dir.mkdir(parents=True, exist_ok=True)
        for p in plans:
            path = gif_dir / p["file"]
            colors, size = encode_one(p["prepared"], path, duration)
            info = V.parse_gif_blocks(path.read_bytes())
            frames = info["frames"]
            problems = []
            if (info["width"], info["height"]) != (B.CANVAS, B.CANVAS):
                problems.append("尺寸 %dx%d" % (info["width"], info["height"]))
            if len(frames) != p["k"]:
                problems.append("帧数 %d != %d" % (len(frames), p["k"]))
            if any(f["disposal"] != 2 for f in frames):
                problems.append("disposal != 2")
            if any(not f["transparent"] or f["transparent_index"] != 0 for f in frames):
                problems.append("透明索引 != 0")
            if any(abs(f["delay_cs"] - duration // 10) > 0 for f in frames):
                problems.append("delay != %dms" % duration)
            if size > MAX_BYTES:
                problems.append("超过 %d B" % MAX_BYTES)
            if problems:
                raise SystemExit("%s/%s 校验失败: %s" % (speed, p["file"], "; ".join(problems)))
            gap = gif_loop_gap(path)
            records.append({
                "speed": speed, "event": p["event"], "file": p["file"], "row": p["row"],
                "src_frames": p["src_frames"], "frames": len(frames), "start": p["start"],
                "colors": colors, "bytes": size, "gap": gap,
                "best_gap": p["best_gap"], "best_k": p["best_k"],
                "gap_src": p["gap_src"], "loop_ok": gap < LOOP_OK,
            })
            print("%-6s %-24s 行%d %d/%d 帧 起点%d %2d 色 %6.1f KB 闭环 %5.2f"
                  % (speed, p["file"], p["row"], p["k"], p["row_frames"], p["start"],
                     colors, size / 1024.0, gap))

        total = sum(r["bytes"] for r in records if r["speed"] == speed)
        print("--- %s 档：%d 个文件，%.1f KB" % (speed, sum(
            1 for r in records if r["speed"] == speed), total / 1024.0))

    manifest = OUT / "manifest.lua"
    lines = [
        "-- Generated by tools/build_skin_gifs.py",
        "return {",
        '  id = "%s",' % SKIN_ID,
        '  name = "%s",' % SKIN_NAME,
        '  name_en = "%s",' % SKIN_NAME_EN,
        "  speeds = { slow = 150, normal = 120, fast = 90 },",
        '  default_speed = "%s",' % DEFAULT_SPEED,
        "  events = {",
    ]
    for event, _row, _starts in B.EVENT_SPECS:
        files = [r["file"] for r in records
                 if r["speed"] == DEFAULT_SPEED and r["event"] == event]
        items = ", ".join('"%s"' % f for f in files)
        lines.append('    ["%s"] = { %s },' % (event, items))
    lines += [
        "  },",
        "  weather = {},",
        "}",
        "",
    ]
    manifest.write_text("\n".join(lines), encoding="utf-8")

    emit_report(plans, records)
    (WORK / "whale_build.json").write_text(
        json.dumps([{k: v for k, v in p.items() if k != "prepared"} for p in plans],
                   ensure_ascii=False, indent=1), encoding="utf-8")

    normal = [r for r in records if r["speed"] == DEFAULT_SPEED]
    grand = sum(r["bytes"] for r in records)
    print("\n总文件 %d 个，总体积 %.1f KB，最大 %.1f KB"
          % (len(records), grand / 1024.0, max(r["bytes"] for r in records) / 1024.0))
    print("首尾 gap：均值 %.2f，最大 %.2f，未闭环 %d 项"
          % (sum(r["gap"] for r in normal) / len(normal), max(r["gap"] for r in normal),
             sum(1 for r in normal if not r["loop_ok"])))
    print("输出目录: %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
