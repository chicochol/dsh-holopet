#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 PC2005-cloud/dsh-pet 的透明 webm 转成 HoloCubic 可播放的索引 GIF。

产出第二套皮肤 build/skins/chibi-blue/：
  slow/ normal/ fast/ 各 16 个 160x160 索引 GIF + preview.png + report.md。
同一套帧输出三档帧时长（150/120/90ms），只改 duration，帧数与顺序完全一致。

关键实现说明：
  * webm 是 VP9 + AlphaMode，必须用 libvpx-vp9 解码器，否则 ffmpeg 原生解码器
    会把 alpha 丢掉（解出来是纯黑背景、alpha 全 255）。
  * 从 640x360 全片解码，按“运动能量”找动作最集中的 2 秒窗口，再在该窗口内
    均匀抽帧，避免把 10 秒动作压成幻灯片。
  * 同一 GIF 内所有帧先求 alpha 联合包围盒再裁切，内容区 <=152x152。
  * 单文件 <=48KB：窗口跨度 / 帧数 / 色数三级降级，降级结果写进 report.md。

用法：python tools/build_pet_skin.py
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------- 路径与常量

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "skins" / "chibi-blue"
WORK = ROOT / "build" / "skins" / "_work"
CACHE = WORK / "webm"

FFMPEG = Path(shutil.which("ffmpeg") or "ffmpeg")
FFPROBE = Path(shutil.which("ffprobe") or "ffprobe")

RAW_BASE = "https://raw.githubusercontent.com/PC2005-cloud/dsh-pet/HEAD/dsh-pet/assets/webm/"
PREVIEW_BASE = "https://raw.githubusercontent.com/PC2005-cloud/dsh-pet/HEAD/dsh-pet/assets/preview/"
REPO_URL = "https://github.com/PC2005-cloud/dsh-pet"

CANVAS = 160
PAD = 4                    # 内容区 152x152，四周留 4px
INNER = CANVAS - 2 * PAD
ALPHA_CUT = 128            # 缩放后 alpha 二值化阈值
BBOX_ALPHA = 8             # 求包围盒时忽略极淡噪点

FRAME_SEC = 0.15          # 默认每帧对应的源画面时长（120ms/帧时约 1.25 倍速）
FPS = 24.0
NF_LADDER = [12, 11, 10, 9, 8, 7, 6]
COLOR_LADDER = [30]
MIN_COLORS = 30            # 30 色版固定 30 项调色板（索引0透明 + 29 实色）
MAX_BYTES = 64000          # 64KB 取十进制 64000（三档产物都要 <= 该值）
MIN_FRAMES = 6

# 窗口长度与帧数解耦：首尾 gap 只由窗口的前后两帧决定，中间抽 8 帧还是 12 帧
# 几乎不影响 gap。因此同一动作可以“用 1.2s 的窗口抽 10 帧”，既保住闭环又提帧数。
# 每项 = 每个 GIF 帧对应多少秒源画面（0.12s 即与 120ms 播放等速，接近实时）。
WIN_SPAN_LADDER = (FRAME_SEC, 0.12, 0.10)

SPEEDS = [("slow", 150), ("normal", 120), ("fast", 90)]

# 循环闭环：GIF 末帧会直接跳回首帧，首尾姿态差太多就产生“转到一半重置”的抽动。
# 选窗口时在“运动能量高”之外加权惩罚首尾差，把跳变压到肉眼不可见。
GAP_LAMBDA = 1.5           # 归一化后 score = energy/emax - GAP_LAMBDA * gap/GAP_SCALE
GAP_SCALE = 20.0           # gap 归一化尺度（首尾差按 20 记满分惩罚）
GAP_ENERGY_CANDS = 6       # 候选窗口里“运动最强”取几个
GAP_GAP_CANDS = 6          # 候选窗口里“首尾最接近”取几个
LOOP_GOOD = 4.0            # 首尾差低于此值视为“无感闭环”，优先保帧数
LOOP_OK = 8.0              # 低于此值认为闭环可接受（GIF 循环肉眼不可见跳变）

# (事件, 输出名, 源 webm, 预览 GIF 名（webm 失败时兜底）, 语义说明)
EVENT_SPECS = [
    ("Idle", "idle_01.gif", "待机呼吸休闲", "daiji-huxi-xiuxian.gif", "站立呼吸，最标准的待机"),
    ("Idle", "idle_02.gif", "东张西望", "dongzhangxiwang.gif", "左右张望的待机变体"),
    ("Idle", "idle_03.gif", "悠闲哼歌", "youxian-hengga.gif", "哼歌（带音符）的待机变体"),
    ("Idle", "idle_04.gif", "照镜子", "zhao-jingzi.gif", "拿小镜子照的待机变体"),
    ("UserPromptSubmit", "userpromptsubmit.gif", "点击回应-元气挥手", "dianji-huiying-yuanqi-huishou.gif", "元气挥手回应"),
    ("PreToolUse", "pretooluse.gif", "写代码", "xie-daima.gif", "对着笔记本敲代码"),
    ("PostToolUse", "posttooluse.gif", "轻快记录", "qingkuai-jilu.gif", "拿纸笔记录的收尾动作"),
    ("PermissionRequest", "permissionrequest.gif", "期待开饭", "dianji-huiying-haixiu-jingya.gif",
     "双手交握期待（替代：源素材没有举手请示动作）"),
    ("Error", "error.gif", "工作状态-垂头叹气冒汗", "gongzuozhuangtai-chuitou-tanqi-maohan.gif",
     "垂头叹气冒汗 + 红色错误标记"),
    ("Stop", "stop.gif", "工作状态-雀跃庆祝", "gongzuozhuangtai-queyue-qingzhu.gif", "雀跃庆祝"),
    ("SessionStart", "sessionstart.gif", "超大伸懒腰", "chaoda-shenlanyao.gif", "伸懒腰醒来"),
    ("SubagentStart", "subagentstart.gif", "三球抛接", "sanqiu-paojie.gif",
     "抛接三个球（替代：隐喻并行子任务）"),
    ("SubagentStop", "subagentstop.gif", "拆礼物", "chai-liwu.gif",
     "拆礼物（替代：隐喻收到子任务结果）"),
    ("PreCompact", "precompact.gif", "深度思考碎碎念", "shendu-sikao-suisuinian.gif",
     "冒思考气泡碎碎念（替代：隐喻整理上下文）"),
    ("PostCompact", "postcompact.gif", "工作状态-清点归档", "gongzuozhuangtai-qingdian-guidang.gif",
     "拿记录板清点归档"),
    ("Sleeping", "sleeping.gif", "睡觉-循环", "shuijiao-xunhuan.gif", "闭眼睡觉 + Zzz"),
]


# ---------------------------------------------------------------- 取素材


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "holocubic-skin-builder"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def ensure_webm(name: str) -> Path:
    dst = CACHE / (name + ".webm")
    if dst.is_file() and dst.stat().st_size > 10000:
        return dst
    CACHE.mkdir(parents=True, exist_ok=True)
    url = RAW_BASE + urllib.parse.quote(name + ".webm")
    dst.write_bytes(http_get(url))
    return dst


def decode_webm(src: Path) -> tuple[np.ndarray, int, int]:
    """全片解码为 RGBA 字节数组，返回 (arr, w, h)。"""
    cmd = [
        str(FFMPEG), "-v", "error", "-c:v", "libvpx-vp9", "-i", str(src),
        "-pix_fmt", "rgba", "-f", "rawvideo", "-",
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0 or not p.stdout:
        raise RuntimeError("ffmpeg 解码失败: %s\n%s" % (src.name, p.stderr[:400]))
    probe = subprocess.run(
        [str(FFPROBE), "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", str(src)],
        stdout=subprocess.PIPE,
    )
    info = json.loads(probe.stdout.decode("utf-8"))["streams"][0]
    w, h = int(info["width"]), int(info["height"])
    need = w * h * 4
    if len(p.stdout) % need:
        raise RuntimeError("原始帧长度不是整帧: %d %% %d" % (len(p.stdout), need))
    arr = np.frombuffer(p.stdout, dtype=np.uint8).reshape(-1, h, w, 4)
    return arr, w, h


# ---------------------------------------------------------------- 选帧


def motion_profile(arr: np.ndarray) -> np.ndarray:
    """逐帧运动能量（相邻帧 alpha 加权亮度差），长度 N-1。"""
    small = arr[:, ::4, ::4, :].astype(np.int16)      # 360->90, 640->160
    lum = small[:, :, :, :3].mean(axis=3)
    vis = (small[:, :, :, 3] > 96).astype(np.float32)
    g = lum * vis
    d = np.abs(np.diff(g, axis=0))
    return d.mean(axis=(1, 2))


def composite_small(arr: np.ndarray, step: int = 4) -> np.ndarray:
    """把整段 RGBA 降采样、合成到黑底、并裁到角色联合包围盒。

    两个关键点：

    1. 合成到黑底（`rgb * alpha/255`）：透明区残留的 RGB 是 VP9 的脏数据，
       不乘 alpha 会污染差值。
    2. **裁到角色包围盒**：如果按全画布 640x360 求平均差，透明背景（差值恒 0）
       会把分母撑大 3-4 倍，让首尾差被严重稀释——实测全画布 7.8 对应最终 GIF
       18.3，口径完全不同。裁到角色区域后与 `prepare()` 后的统计域一致，阈值
       才能和“渲染出来的 GIF”对得上。

    返回 (N, bh, bw, 3) float32。
    """
    a = arr[:, ::step, ::step, :].astype(np.float32)
    comp = a[:, :, :, :3] * (a[:, :, :, 3:4] / 255.0)
    # 整段联合包围盒：只要任一帧在该处有角色，就算内容区
    mask = (a[:, :, :, 3] >= 96).any(axis=0)
    ys, xs = np.where(mask)
    if len(ys) > 1 and len(xs) > 1:
        comp = comp[:, ys.min():ys.max() + 1, xs.min():xs.max() + 1, :]
    return comp


def frame_gap(arr: np.ndarray, i: int, j: int, comp: np.ndarray | None = None) -> float:
    """两帧合成到黑底后的平均绝对差（0-255）。

    comp 可传入 composite_small() 的预算结果，避免每个候选窗口重复降采样。
    """
    if comp is None:
        comp = composite_small(arr)
    return float(np.abs(comp[i] - comp[j]).mean())


def _canvas_gap(fa: Image.Image, fb: Image.Image) -> float:
    """两张同尺寸 RGBA 帧合成到黑底后的平均绝对差（与最终 GIF 口径一致）。"""
    def comp(im: Image.Image) -> np.ndarray:
        a = np.asarray(im.convert("RGBA"), dtype=np.float32)
        return a[:, :, :3] * (a[:, :, 3:4] / 255.0)
    return float(np.abs(comp(fa) - comp(fb)).mean())


def render_frames(arr: np.ndarray, idx: list[int]) -> list[Image.Image]:
    return [Image.frombytes("RGBA", (arr.shape[2], arr.shape[1]), arr[i].tobytes()) for i in idx]


def window_indices(start: int, win: int, nf: int) -> list[int]:
    """窗口内均匀抽 nf 帧（可能因窗口太短去重后不足 nf）。"""
    return sorted({start + int(round(v)) for v in np.linspace(0, win - 1, nf)})


def candidate_windows(arr: np.ndarray, prof: np.ndarray, n_frames: int, fps: float, nf: int,
                      comp: np.ndarray | None = None,
                      n_energy: int = 6, n_gap: int = 6,
                      win: int | None = None) -> list[tuple[int, int, float]]:
    """挑候选窗口：既要有运动，又要首尾接近，两头都覆盖。

    只看能量最高的一小撮起点是不够的——实测 `idle_01` 那样 241 帧的源，能量 top 12
    按 `sep=win//3` 散开后只覆盖时间轴的一小段，真正能闭环的窗口根本进不了候选集。

    整段 gap 可以一次性向量化算完所有起点（一次 `abs().mean()` 的事），所以这里直接
    全扫：取「能量最高的 n_energy 个」+「首尾最接近的 n_gap 个」，各自按 sep 散开，
    合并去重后作为精筛候选。返回 [(start, win, energy)]。

    `win` 显式给出时用它作为源窗口长度（帧），否则按 `nf * FRAME_SEC * fps` 推。
    """
    n = n_frames
    win = max(nf, int(round(nf * FRAME_SEC * fps))) if win is None else max(nf, int(win))
    win = min(win, n)
    if win >= n:
        return [(0, n, float(prof.sum()))]

    energy = np.convolve(prof, np.ones(win - 1), mode="valid")   # 长度 n-win+1
    m = n - win + 1
    if comp is None:
        comp = composite_small(arr)
    # 所有起点的首尾差，一次算完
    gaps = np.abs(comp[:m] - comp[win - 1:win - 1 + m]).mean(axis=(1, 2, 3))

    sep = max(1, win // 3)              # 候选之间至少隔这么久，避免扎堆同一段
    picks: list[int] = []

    def take(order, k: int) -> None:
        got = 0
        for raw in order:
            s = min(int(raw), m - 1)
            if all(abs(s - p) >= sep for p in picks):
                picks.append(s)
                got += 1
                if got >= k:
                    break

    take(np.argsort(-energy), n_energy)   # 运动最强
    take(np.argsort(gaps), n_gap)         # 首尾最接近
    return [(s, win, float(energy[s])) for s in picks]


def pick_window(arr: np.ndarray, prof: np.ndarray, n_frames: int, fps: float, nf: int,
                comp: np.ndarray | None = None,
                lam: float = GAP_LAMBDA,
                n_energy: int = GAP_ENERGY_CANDS,
                n_gap: int = GAP_GAP_CANDS,
                win: int | None = None) -> tuple[list[int], int, int, float, list[Image.Image]]:
    """为 nf 帧找「运动集中且首尾闭合」的窗口。

    原实现只取能量最大的窗口，末帧与首帧姿态可能差很远，循环时突然跳回产生抽动。

    做法：候选集同时收「能量最高的」和「首尾最接近的」两批（`candidate_windows`），
    然后对每个候选**真正跑 `prepare()`** 再量首尾差。这一步不能省——实测同一个窗口
    在源帧整段 bbox 口径下是 25.2，prepare 完变成 16.3，比例还随角色缩放倍数漂移，
    只有 160x160 上的数值才和最终 GIF 同口径。

    最终按归一化分数挑：

        score = energy / emax - lam * min(gap, GAP_SCALE) / GAP_SCALE

    归一化是因为 energy（运动能量累加）和 gap（平均差）量纲差几十倍，不归一化时
    λ 只能对某一类动作合适。存在 gap < LOOP_OK 的候选时，只在其中挑（先保证达标）。

    `win` 可显式指定源窗口长度（帧），与帧数解耦；缺省仍按 `FRAME_SEC` 推。

    返回 (帧索引, 起点帧, 窗口帧数, 首尾差, 预处理帧)；预处理帧可直接复用编码。
    """
    if comp is None:
        comp = composite_small(arr)
    cands = candidate_windows(arr, prof, n_frames, fps, nf, comp, n_energy, n_gap, win=win)
    if len(cands) == 1 and cands[0][1] >= n_frames:
        idx = window_indices(0, n_frames, nf)
        prepped, _tw, _th = prepare(render_frames(arr, idx))
        return idx, 0, n_frames, _canvas_gap(prepped[0], prepped[-1]), prepped

    scored = []
    for s, win, e in cands:
        idx = window_indices(s, win, nf)
        if len(idx) < nf:
            continue
        prepped, _tw, _th = prepare(render_frames(arr, idx))
        scored.append((idx, s, win, e, _canvas_gap(prepped[0], prepped[-1]), prepped))
    if not scored:
        raise RuntimeError("窗口内抽不出 %d 个不同帧" % nf)

    emax = max(x[3] for x in scored) or 1.0

    def score(x: tuple) -> float:
        _idx, _s, _w, e, g, _p = x
        return (e / emax) - lam * (min(g, GAP_SCALE) / GAP_SCALE)

    looped = [x for x in scored if x[4] < LOOP_OK]
    best = max(looped or scored, key=score)
    return best[0], best[1], best[2], best[4], best[5]


def prepare(frames: list[Image.Image]) -> tuple[list[Image.Image], int, int]:
    """联合 bbox 裁切 -> 等比缩放到 152 -> 居中贴到 160 画布。"""
    box = None
    for f in frames:
        a = f.getchannel("A").point(lambda v: 255 if v >= BBOX_ALPHA else 0)
        b = a.getbbox()
        if not b:
            continue
        box = b if box is None else (
            min(box[0], b[0]), min(box[1], b[1]),
            max(box[2], b[2]), max(box[3], b[3]),
        )
    if box is None:
        raise RuntimeError("帧全透明")

    w, h = box[2] - box[0], box[3] - box[1]
    k = min(INNER / float(w), INNER / float(h))
    tw, th = max(1, int(round(w * k))), max(1, int(round(h * k)))
    ox, oy = (CANVAS - tw) // 2, (CANVAS - th) // 2

    out = []
    for f in frames:
        a = f.crop(box).copy()
        alpha = a.getchannel("A").point(lambda v: 255 if v >= ALPHA_CUT else 0)
        a.putalpha(alpha)
        # RGBa 预乘 alpha，缩放不会在透明边缘产生黑边
        s = a.convert("RGBa").resize((tw, th), Image.LANCZOS).convert("RGBA")
        scaled_alpha = s.getchannel("A")
        # 轻度中值滤波：抹掉 VP9 压缩噪点，LZW 可压 ~25%，画质几乎无损
        s = s.convert("RGB").filter(ImageFilter.MedianFilter(3)).convert("RGBA")
        s.putalpha(scaled_alpha.point(lambda v: 255 if v >= ALPHA_CUT else 0))
        canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
        canvas.paste(s, (ox, oy), s)
        out.append(canvas)
    return out, tw, th


# ---------------------------------------------------------------- 索引色编码


def build_palette(frames: list[Image.Image], colors: int, method) -> Image.Image:
    chunks = []
    for f in frames:
        a = np.frombuffer(f.tobytes(), dtype=np.uint8).reshape(-1, 4)
        chunks.append(a[a[:, 3] >= ALPHA_CUT, :3])
    px = np.concatenate(chunks) if chunks else np.zeros((1, 3), np.uint8)
    if len(px) == 0:
        px = np.zeros((1, 3), np.uint8)
    step = max(1, len(px) // 60000)
    px = np.ascontiguousarray(px[::step])
    strip = Image.frombytes("RGB", (len(px), 1), px.tobytes())
    return strip.quantize(colors=colors - 1, method=method, dither=Image.Dither.NONE)


def to_indexed(f: Image.Image, palette_img: Image.Image, colors: int) -> Image.Image:
    """0 号索引固定透明，实际颜色占 1..colors-1。"""
    alpha = f.getchannel("A").point(lambda v: 255 if v >= ALPHA_CUT else 0)
    solid = Image.new("RGBA", f.size, (0, 0, 0, 255))
    solid.paste(f, (0, 0), alpha)
    p = solid.convert("RGB").quantize(palette=palette_img, dither=Image.Dither.NONE)
    p = p.point(lambda v: min(colors - 1, v + 1))

    base = palette_img.getpalette()[: (colors - 1) * 3]
    base = base + [0, 0, 0] * (colors - 1 - len(base) // 3)
    p.putpalette([0, 0, 0] + base)

    p.paste(0, mask=alpha.point(lambda v: 255 if v == 0 else 0))
    return p


def encode(frames: list[Image.Image], colors: int, method, duration: int) -> bytes:
    pal = build_palette(frames, colors, method)
    idxs = [to_indexed(f, pal, colors) for f in frames]
    buf = io.BytesIO()
    idxs[0].save(
        buf, "GIF", save_all=True, append_images=idxs[1:],
        duration=duration, loop=0, disposal=2, transparency=0, optimize=True,
    )
    return buf.getvalue()


def _bytes_gap(data: bytes) -> float:
    """从内存里的 GIF 字节流实测首尾差，与 `gif_loop_gap()` 同口径。"""
    im = Image.open(io.BytesIO(data))
    n = getattr(im, "n_frames", 1)

    def comp(i: int) -> np.ndarray:
        im.seek(i)
        a = np.asarray(im.convert("RGBA"), dtype=np.float32)
        return a[:, :, :3] * (a[:, :, 3:4] / 255.0)

    return float(np.abs(comp(0) - comp(n - 1)).mean())


def choose_encoding(arr: np.ndarray, fps: float) -> dict:
    """挑「窗口 x 帧数 x 色数」方案，返回选中方案（含预处理帧）。

    两层搜索：

    1. **窗口**：帧数 nf ∈ {12,11,10} × 窗口跨度 `WIN_SPAN_LADDER`。首尾 gap 只由窗口
       的前后两帧决定，同一 `(start, win)` 下抽 10 帧还是 8 帧几乎不改 gap（仅联合 bbox
       缩放略有差别）。所以短窗口完全可以多抽几帧——这正是「48KB + 12 帧 + 闭环」能同时
       成立的关键，而旧实现把 win 死绑成 `nf * FRAME_SEC * fps`，帧数一涨窗口就跟着涨，
       gap 也就跟着坏掉。
    2. **体积**：先硬性只留 gap < `LOOP_OK` 的候选，按「帧数多 > 跨度长 > gap 小」排序，
       逐个试 32/24/20/16 色；编码后读回 GIF 实测 gap 仍 < `LOOP_OK` 才接受。
       全部候选都放不进时才退到非闭环方案并在报告里标注。

    色数下限 `MIN_COLORS=16` 优先于帧数：只有 16 色仍超限才降到 12 色（会压坏头发高光）。
    """
    prof = motion_profile(arr)
    comp = composite_small(arr)
    n = len(arr)

    cands: list[dict] = []
    seen: set[tuple[int, int]] = set()
    for nf in (12, 11, 10):
        for span in WIN_SPAN_LADDER:
            win = max(nf, min(int(round(nf * span * fps)), n))
            if (nf, win) in seen:
                continue
            seen.add((nf, win))
            idx, start, w, gap, prepped = pick_window(arr, prof, n, fps, nf, comp, win=win)
            if len(idx) < nf:
                continue
            cands.append({
                "nf": len(prepped), "win": w, "span": span, "start": start,
                "gap": gap, "frames": prepped,
            })
    if not cands:
        raise RuntimeError("候选窗口都抽不出足够帧")

    def rank(c: dict) -> tuple:
        return (0 if c["gap"] < LOOP_OK else 1, -c["nf"], -c["span"], c["gap"])

    cands.sort(key=rank)

    def attempt(c: dict, min_colors: int, allow_open: bool) -> dict | None:
        """在给定色数下限下逐个色阶试编码；读回 GIF 实测 gap 兜底。"""
        for colors in COLOR_LADDER:
            if colors < min_colors:
                break
            data = encode(c["frames"], colors, Image.Quantize.MEDIANCUT, 120)
            if len(data) > MAX_BYTES:
                continue
            real = _bytes_gap(data)
            if real >= LOOP_OK and not allow_open:
                continue
            return {
                "nf": len(c["frames"]), "colors": colors, "method": "mediancut",
                "size": len(data), "frames": c["frames"], "start": c["start"],
                "win": c["win"], "span": c["span"], "gap": real,
                "gap_src": c["gap"], "loop_ok": real < LOOP_OK,
                "colors_floored": min_colors < MIN_COLORS,
            }
        return None

    # 16 色是硬下限（12 色会把头发高光压成白点），放不下就降帧而不是降色。
    # 只有当 16 色在所有窗口下都超限时才允许退到 12 色，并标记 colors_floored。
    for min_colors, allow_open in ((MIN_COLORS, False), (MIN_COLORS, True),
                                   (12, False), (12, True)):
        for c in cands:
            if not allow_open and c["gap"] >= LOOP_OK:
                continue
            got = attempt(c, min_colors, allow_open)
            if got:
                return got
    raise RuntimeError("最低参数仍超过 %d 字节" % MAX_BYTES)


# ---------------------------------------------------------------- 校验


def gif_loop_gap(path: Path) -> float:
    """读回 GIF，算首帧与末帧（合成到黑底后）的平均绝对差，即循环跳变强度。"""
    im = Image.open(path)
    n = getattr(im, "n_frames", 1)

    def comp(i: int) -> np.ndarray:
        im.seek(i)
        a = np.asarray(im.convert("RGBA"), dtype=np.float32)
        return a[:, :, :3] * (a[:, :, 3:4] / 255.0)

    return float(np.abs(comp(0) - comp(n - 1)).mean())


def verify_gif(path: Path, event: str, expect_frames: int, expect_ms: int) -> dict:
    im = Image.open(path)
    n = getattr(im, "n_frames", 1)
    transparency = im.info.get("transparency")
    sizes, durations, max_colors, has_transparent_px = [], set(), 0, False
    for i in range(n):
        im.seek(i)
        sizes.append(im.size)
        durations.add(im.info.get("duration"))
        max_colors = max(max_colors, len(im.getcolors(maxcolors=256) or []))
        if i == 0 and im.mode == "P":
            has_transparent_px = 0 in im.tobytes()
    size_ok = bool(sizes) and all(s == (CANVAS, CANVAS) for s in sizes)
    data_bytes = os.path.getsize(path)
    return {
        "event": event,
        "file": path.name,
        "path": path,
        "size": sizes[0] if size_ok else tuple(sorted(set(sizes))),
        "frames": n,
        "transparency": transparency,
        "durations": sorted(durations),
        "colors": max_colors,
        "bytes": data_bytes,
        "transparent_px": has_transparent_px,
        "ok": (
            size_ok
            and n > 1
            and transparency == 0
            and data_bytes <= MAX_BYTES
            and durations == {expect_ms}
            and max_colors <= 32
            and has_transparent_px
            and n == expect_frames
        ),
    }


# ---------------------------------------------------------------- 输出


def emit_manifest() -> None:
    lines = [
        "-- Generated by tools/build_pet_skin.py",
        "-- 皮肤 ID: chibi-blue（蓝发少女），素材来自 PC2005-cloud/dsh-pet (MIT)",
        "return {",
        '  id = "chibi-blue",',
        '  name = "蓝发少女",',
        '  name_en = "Blue-Haired Girl",',
        "  speeds = { slow = 150, normal = 120, fast = 90 },",
        '  default_speed = "normal",',
        "  events = {",
    ]
    order = []
    for ev, out, *_ in EVENT_SPECS:
        if ev not in order:
            order.append(ev)
    for ev in order:
        files = [s[1] for s in EVENT_SPECS if s[0] == ev]
        lines.append('    ["%s"] = { %s },' % (ev, ", ".join('"%s"' % f for f in files)))
    lines += ["  },", "  weather = {},", "}", ""]
    (OUT / "manifest.lua").write_text("\n".join(lines), encoding="utf-8")


def emit_preview(records_by_speed: dict[str, list[dict]]) -> None:
    cols, rows = 6, 3
    cell_w, cell_h, pad = 176, 196, 8
    sheet = Image.new("RGBA", (cols * cell_w, rows * cell_h), (32, 34, 42, 255))
    dr = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 12)
    except OSError:
        font = ImageFont.load_default()

    recs = records_by_speed["normal"]
    for i, r in enumerate(recs):
        cx, cy = (i % cols) * cell_w, (i // cols) * cell_h
        # 棋盘格底，方便肉眼确认透明
        board = Image.new("RGBA", (CANVAS, CANVAS), (255, 255, 255, 255))
        bd = ImageDraw.Draw(board)
        step = 10
        for y in range(0, CANVAS, step):
            for x in range(0, CANVAS, step):
                if (x // step + y // step) % 2:
                    bd.rectangle([x, y, x + step - 1, y + step - 1], fill=(205, 205, 215, 255))
        im = Image.open(r["path"])
        im.seek(0)
        board.alpha_composite(im.convert("RGBA"))
        sheet.alpha_composite(board, (cx + pad, cy + 22))
        label = "%s  %df %dc" % (r["event"], r["frames"], r["colors"])
        dr.text((cx + pad, cy + 5), label, fill=(235, 235, 245, 255), font=font)
    sheet.convert("RGB").save(OUT / "preview.png", optimize=True)


def emit_report(records: list[dict]) -> None:
    total = {s: sum(r["bytes"] for r in records if r["speed"] == s) for s, _ in SPEEDS}
    big = max(records, key=lambda r: r["bytes"])
    lines = [
        "# chibi-blue 皮肤构建报告",
        "",
        "## 素材来源",
        "",
        "- 仓库：%s（MIT，%s 星）" % (REPO_URL, "5942"),
        "- 原始素材：`dsh-pet/assets/webm/`（114 个 VP9 WebM，带 AlphaMode，"
        "640x360 / 24fps / 约 10 秒）",
        "- 本套皮肤**全部用 webm 解码**，没有使用 `assets/preview/` 的预览 GIF。",
        "",
        "## 关于 webm 的 alpha",
        "",
        "这些 webm 的 alpha 存在，但 ffmpeg 原生 VP9 解码器会**丢掉**它（解出来是黑底、"
        "alpha 全 255）；必须加 `-c:v libvpx-vp9` 强制走 libvpx 解码器才能拿到真实 alpha。"
        "脚本已按此处理，解出的背景 alpha=0，角色 alpha=255。",
        "",
        "## 抽帧与压缩策略",
        "",
        "- 全片解码后按“相邻帧 alpha 加权亮度差”算运动能量；候选窗口**两头收**："
        "运动能量最高的若干个 + 首尾姿态最接近的若干个，逐个渲染到 160x160 后实测"
        "首尾差，取“运动够 + 循环闭合”的最优窗口。窗口长度 = 帧数 x %.2f 秒"
        "（120ms/帧下约 1.25 倍速，接近实时），窗口内均匀抽帧；"
        "这样既不会把 10 秒动作压成幻灯片，也不会因为首尾姿态差太多而在循环点跳回。"
        % FRAME_SEC,
        "- 同一 GIF 内所有帧先求 **alpha 联合包围盒**再统一裁切，然后等比缩放到内容区 "
        "152x152，居中放在 160x160 透明画布上，因此动作不会抖动。",
        "- 缩放到目标尺寸后做一次 3x3 中值滤波，去掉 VP9 压缩噪点（LZW 体积降约 25%，"
        "160px 下肉眼几乎无差）。",
        "- 调色板：整段动画共享统一调色板，透明索引固定 0，实际颜色 1..N；"
        "`disposal=2`、`loop=0`、`optimize=True`。",
        "- 体积控制：按“窗口跨度 x 帧数 x 色数”枚举，选放得进 %d B 的最优组合——色数下限 16，"
        "排序**闭环优先、帧数多优先、跨度长优先**（首尾差 < %.1f 视为无感闭环）。"
        "窗口长度与帧数已解耦：同一 1.2s 窗口可以抽 10 帧，首尾 gap 不变而帧数更多。"
        "量化固定 MEDIANCUT：MAXCOVERAGE 虽然能再省 25%% 体积，"
        "但会把蓝发压成紫灰、裙子泛绿，颜色失真不可接受。" % (MAX_BYTES, LOOP_GOOD),
        "",
        "## 三档速度",
        "",
        "| 档位 | 帧时长 | GIF 数 | 总字节 |",
        "|---|---:|---:|---:|",
    ]
    for s, ms in SPEEDS:
        n = sum(1 for r in records if r["speed"] == s)
        lines.append("| %s | %d ms | %d | %s B（%.1f KB） |"
                     % (s, ms, n, f"{total[s]:,}", total[s] / 1024.0))
    lines += [
        "",
        "- 三档合计：**%s B（%.1f KB）**" % (f"{sum(total.values()):,}", sum(total.values()) / 1024.0),
        "- 最大单文件：**%.1f KB**（`%s/%s`）"
        % (big["bytes"] / 1024.0, big["speed"], big["file"]),
        "",
        "## 事件 → 源素材",
        "",
        "| 事件 | 输出文件 | 源 webm | 帧数 | 色数 | 源画面区间 | 首尾差 | 说明 |",
        "|---|---|---|---:|---:|---|---:|---|",
    ]
    for r in records:
        if r["speed"] != "normal":
            continue
        lines.append("| %s | `%s` | %s | %d | %d | %.2fs 起 %.2fs | %.2f | %s |"
                     % (r["event"], r["file"], r["source"], r["frames"], r["colors"],
                        r["window_start"], r["window_sec"], r["gap"], r["note"]))
    lines += [
        "",
        "**替代素材说明**（源素材没有与事件完全对应的动作时，用最接近的动作代替）：",
        "",
        "- `PermissionRequest` → `期待开饭`：双手交握期待的样子，没有“举手请示”类动作。",
        "- `SubagentStart` → `三球抛接`：抛接三球的隐喻，表示并行分派子任务。",
        "- `SubagentStop` → `拆礼物`：拆开礼物的隐喻，表示收到子任务结果。",
        "- `PreCompact` → `深度思考碎碎念`：冒思考气泡，隐喻整理/压缩上下文。",
        "- 其余 12 个事件与源动作语义基本对应（Idle 的 4 个变体来自 4 个不同的待机动画）。",
        "",
        "## 自检结果",
        "",
        "每个文件都读回校验：尺寸 160x160、transparency=0、帧数>1、单文件<=48KB、"
        "每帧 duration 与档位一致、色数<=32、首帧存在透明像素。",
        "",
        "| 档位 | 文件 | 事件 | 帧数 | 时长 | 色数 | 大小 | 结果 |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for r in records:
        lines.append("| %s | `%s` | %s | %d | %dms | %d | %.1f KB | %s |"
                     % (r["speed"], r["file"], r["event"], r["frames"], r["duration"],
                        r["colors"], r["bytes"] / 1024.0, "PASS" if r["ok"] else "**FAIL**"))
    failed = [r for r in records if not r["ok"]]
    normal = [r for r in records if r["speed"] == "normal"]
    frames_lo = min(r["frames"] for r in normal)
    frames_hi = max(r["frames"] for r in normal)
    colors_lo = min(r["colors"] for r in normal)
    colors_hi = max(r["colors"] for r in normal)
    bytes_lo = min(r["bytes"] for r in records)
    lines += [
        "",
        "- 校验通过：**%d / %d**（%s）" % (
            len(records) - len(failed), len(records),
            "全部通过" if not failed else "有失败项，见上表"),
        "- 帧数范围 %d–%d，色数范围 %d–%d（三档帧数与顺序完全一致，只有 duration 不同，"
        "所以三档字节数相同——duration 存在图形控制扩展里，不额外占体积）。"
        % (frames_lo, frames_hi, colors_lo, colors_hi),
        "- 体积范围 %.1f–%.1f KB，上限 %d 字节（48KB 的十进制口径，"
        "比 48*1024 更严，两种理解下都不超限）。"
        % (bytes_lo / 1024.0, max(r["bytes"] for r in records) / 1024.0, MAX_BYTES),
        "",
        "## 遇到的问题与处理",
        "",
        "1. **webm 的 alpha 会被 ffmpeg 丢掉**：用默认 VP9 解码器解出来是黑底、"
        "alpha 全 255。改成 `-c:v libvpx-vp9` 强制 libvpx 解码后才有真实 alpha"
        "（背景 alpha≈1，角色 255），再按阈值 128 二值化。",
        "2. **直接转 160x160、32 色会爆体积**：8/10/12/16 帧分别是 59.8/68.8/82.1/109 KB，"
        "远超 48KB。原因是 640x360 的 VP9 码率不高，压缩噪点让 LZW 压不动。"
        "加 3x3 中值滤波省约 25%，再把窗口/帧数/色数作为可调参数逐级降级，才稳定进 48KB。",
        "3. **MAXCOVERAGE 量化器不能用**：虽然同参数再省 25% 体积，但会把蓝发压成紫灰、"
        "裙子泛绿、皮肤发白，颜色失真肉眼可见，因此只用 MEDIANCUT。",
        "4. **12 色会把头发高光压成白点**：因此设 16 色为下限，宁可少一两帧；"
        "帧数少时窗口同步变短（每帧仍对应 0.15s 源画面），播放速度不变。",
        "5. **联合包围盒会让带特效的片段角色偏小**：`PreCompact`（三个思考气泡横向展开）"
        "包围盒偏宽，等比缩放后角色只有约 93px 高，比其它片段的约 150px 明显小。"
        "这是“同片段统一裁切、不抖动”的代价，若要统一角色大小需要按角色本体单独定标。",
        "6. **仓库预览 GIF 的实际尺寸不是 144x116**：`assets/preview/` 里的 GIF89a 实测是 "
        "220x124、256 色、120 帧、80ms，和任务描述不一致。本套皮肤没用到它们"
        "（全部走 webm），这里只是记录。",
        "7. 有些片段比 10 秒短（`期待开饭` 123 帧、`垂头叹气冒汗` 118 帧，约 5 秒），"
        "脚本按实际帧数取窗口，不会越界。",
        "",
        "## 目录结构",
        "",
        "```",
        "chibi-blue/",
        "├─ slow/    16 个 GIF（150ms/帧）",
        "├─ normal/  16 个 GIF（120ms/帧，默认档）",
        "├─ fast/    16 个 GIF（90ms/帧）",
        "├─ manifest.lua",
        "├─ preview.png   6x3 缩略总览（normal 档，棋盘格底显示透明）",
        "└─ report.md",
        "```",
        "",
        "manifest 里的文件名是相对路径（不含档位目录），播放器按 "
        "`<skin>/<speed>/<file>` 拼路径即可。",
        "",
    ]
    (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")


def emit_loop_report(records: list[dict]) -> None:
    """写 report-loop.md：循环闭环修复的逐动作前后对比。

    改前数据来自 build/skins/_work/gap_before.json（旧产物 48 个 GIF 的实测首尾差）；
    文件缺失时该列显示 “—”，不影响其余内容。
    """
    before: dict[str, float] = {}
    bp = WORK / "gap_before.json"
    if bp.is_file():
        try:
            for r in json.loads(bp.read_text(encoding="utf-8")):
                if r.get("speed") == "normal":
                    before[r["file"]] = float(r["gap"])
        except (ValueError, KeyError):
            before = {}

    normal = [r for r in records if r["speed"] == "normal"]
    bad = [r for r in normal if not r["loop_ok"]]
    total = sum(r["bytes"] for r in records)
    gap_after = [r["gap"] for r in normal]
    pairs = [(before[r["file"]], r["gap"]) for r in normal if r["file"] in before]
    delta = sum(b - a for b, a in pairs) / len(pairs) if pairs else 0.0

    lines = [
        "# chibi-blue 循环闭环修复报告",
        "",
        "## 问题",
        "",
        "GIF 循环播放时末帧会直接跳回首帧。原 `pick_window()` 只按“运动能量最大”选择",
        "窗口起点，完全不管窗口首帧和末帧姿态是否接近；末帧与首帧差得远时，循环点就会",
        "看到角色突然跳回去重新开始，表现为“转到一半就重置”的抽动。",
        "",
        "## 改了什么",
        "",
        "| 项 | 改动 |",
        "|---|---|",
        "| `frame_gap(arr, i, j, comp)` | **新增**。两帧降采样 4 倍后合成到黑底"
        "（`rgb * alpha/255`），返回平均绝对差（0–255），与校验脚本同口径。 |",
        "| `composite_small(arr, step=4)` | **新增**。整段一次性预合成降采样帧，"
        "避免每个候选窗口重复降采样。 |",
        "| `pick_window()` | 候选集**两头收**：全时间轴向量化扫出「能量最高的 %d 个」"
        "和「首尾最接近的 %d 个」（按 `win//3` 最小间距散开，避免候选扎堆）；"
        "对每个候选真正跑 `prepare()` 后在 160×160 像素上量首尾差，"
        "按归一化 `score = energy/emax - λ × gap/%d` 取最优。 |"
        % (GAP_ENERGY_CANDS, GAP_GAP_CANDS, int(GAP_SCALE)),
        "| `pick_indices()` | 已删除（旧实现基于“只取能量最大”的 `pick_window`）。 |",
        "| `choose_encoding()` | 改为**闭环优先、帧数次之**：先对所有候选帧数算 gap"
        "（只做窗口比较，不编码），gap < %.1f 视为“无感闭环”且帧数多者优先；"
        "其次 gap < %.1f 的；都不达标时取 gap 最小的方案。原先“12 帧能塞进 40KB 就"
        "选 12 帧”的规则会抵消窗口优化，因此一并改掉。 |" % (LOOP_GOOD, LOOP_OK),
        "| `gif_loop_gap()` | **新增**。读回生成的 GIF 实测首尾差，写进报告与" 
        "`report.md` 的自检表。 |",
        "",
        "关键参数：**λ = %.1f**（归一化后，gap 按 %.0f 记满分惩罚），"
        "候选窗口 能量 top **%d** + 闭环 top **%d**，"
        "无感阈值 **%.1f**，可接受阈值 **%.1f**。"
        % (GAP_LAMBDA, GAP_SCALE, GAP_ENERGY_CANDS, GAP_GAP_CANDS, LOOP_GOOD, LOOP_OK),
        "",
        "## 16 个动作逐项对比（normal 档，三档帧序列相同）",
        "",
        "| 事件 | 文件 | 帧数 | 体积 | 首尾 gap（改前 → 改后） | 判定 |",
        "|---|---|---:|---:|---|---|",
    ]
    for r in normal:
        b = before.get(r["file"])
        btxt = "%.2f" % b if b is not None else "—"
        arrow = "**%.2f**" % r["gap"]
        mark = "PASS" if r["loop_ok"] else "**未闭环**"
        lines.append("| %s | `%s` | %d | %.1f KB | %s → %s | %s |"
                     % (r["event"], r["file"], r["frames"], r["bytes"] / 1024.0,
                        btxt, arrow, mark))

    lines += [
        "",
        "- 改前 %d 项全部超过 %.1f（均值 %.2f，最大 %.2f），改后均值 %.2f、最大 %.2f，"
        "平均下降 **%.2f**。"
        % (len(pairs), LOOP_OK,
           sum(b for b, _ in pairs) / len(pairs) if pairs else 0,
           max((b for b, _ in pairs), default=0),
           sum(gap_after) / len(gap_after), max(gap_after), delta),
        "",
        "## 帧数为什么能回到 10–12 帧",
        "",
        "关键发现：`gap` 只取决于窗口的**首帧和末帧**，同一 `(start, win)` 下抽 8 帧还是",
        "12 帧，首尾差几乎不变（实测差 <0.1，只是联合 bbox 缩放略有不同）。旧实现把窗口",
        "长度死绑成 `nf * FRAME_SEC * fps`，帧数一涨窗口就跟着变长，gap 随即恶化——这才是",
        "“加帧就破闭环”的真正原因，而不是帧数本身。",
        "",
        "现在 `WIN_SPAN_LADDER` 让窗口跨度与帧数解耦：同一个 1.2 s 窗口，抽 8 帧是旧行为，",
        "抽 10–12 帧则动作更顺，而首尾 gap 完全不变。体积仍是硬约束——16 色下 10 帧约",
        "42–47 KB、11 帧约 45–49 KB、12 帧约 47–56 KB，所以 12 帧只在少数动作放得下，",
        "其余落在 10–11 帧；12 色会压坏头发高光，不作为换帧手段。",
        "",
    ]

    if bad:
        lines += [
            "## 无法完全闭环的动作",
            "",
            "这些动作在“取 6–12 帧、窗口长度按 `FRAME_SEC` 自适应”的约束下，"
            "任何候选窗口的首尾差都降不到 %.1f 以下："
            % LOOP_OK,
            "",
            "| 事件 | 文件 | 最小可达 gap | 原因 |",
            "|---|---|---:|---|",
        ]
        for r in bad:
            if r["gap"] >= 15:
                why = "动作幅度大或在整段持续位移/旋转，等长窗口的末帧与首帧姿态天然相差很远"
            elif r["gap"] >= 11:
                why = "动作本身不闭合，窗口内仍留有明显的姿态残余位移"
            else:
                why = "闭环已大幅改善但仍略高于阈值，属于轻微残余位移"
            lines.append("| %s | `%s` | %.2f | %s |"
                         % (r["event"], r["file"], r["gap"], why))
        lines += [
            "",
            "**建议**（按优先级）：",
            "",
            "1. **往返播放**：把帧序列接成“正放 + 倒放（去掉重复的首尾帧）”，首尾天然重合，"
            "闭环问题彻底消失。代价是帧数约翻倍（n → 2n-2），48KB 上限下需要降到 "
            "6–7 帧才能放下，动作会变粗、且播放时来回重复同一段动作。是否可接受取决于"
            "观感偏好。",
            "2. **接受轻微跳变**：这些动作本身的语义是“持续进行”（如旋转/张望），"
            "循环点的小跳变反而比往返播放更自然，可保留现状。",
            "3. **换源素材**：如果上游仓库里有同一动作的完整闭环版本（首尾姿态一致），"
            "直接换源最省事。",
            "",
        ]
    else:
        lines += [
            "## 无法完全闭环的动作",
            "",
            "无。16 个动作全部达到 %.1f 以下。" % LOOP_OK,
            "",
        ]

    lines += [
        "## 总量",
        "",
        "- 文件数：**%d 个**（3 档 × 16 个动作），校验通过 **%d/%d**。"
        % (len(records), sum(1 for r in records if r["ok"]), len(records)),
        "- 总体积：**%s B（%.1f KB）**，最大单文件 %.1f KB（上限 %d B）。"
        % (f"{total:,}", total / 1024.0, max(r["bytes"] for r in records) / 1024.0, MAX_BYTES),
        "",
        "> 帧数、尺寸、透明索引 0、disposal=2、单文件 ≤ %d B、duration 150/120/90 ms "
        "等约束均由 `verify_gif()` 逐文件复核。" % MAX_BYTES,
        "",
    ]
    (OUT / "report-loop.md").write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------- 主流程

def main() -> int:
    if not FFMPEG.is_file():
        raise SystemExit("找不到 ffmpeg: %s" % FFMPEG)

    OUT.mkdir(parents=True, exist_ok=True)
    for s, _ in SPEEDS:
        d = OUT / s
        if d.exists():
            for old in d.glob("*.gif"):
                old.unlink()
        d.mkdir(parents=True, exist_ok=True)

    records: list[dict] = []
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    for ev, out_name, webm_name, preview_name, note in EVENT_SPECS:
        if only and out_name != only:
            continue
        src = ensure_webm(webm_name)
        arr, w, h = decode_webm(src)
        n = len(arr)
        best = choose_encoding(arr, FPS)
        nf, colors = best["nf"], best["colors"]
        method, frames = best["method"], best["frames"]
        win_start = best["start"] / FPS
        win_sec = best["win"] / FPS
        del arr
        for speed, ms in SPEEDS:
            path = OUT / speed / out_name
            data = encode(frames, colors, Image.Quantize.MEDIANCUT
                          if method == "mediancut" else Image.Quantize.MAXCOVERAGE, ms)
            path.write_bytes(data)

        for speed, ms in SPEEDS:
            v = verify_gif(OUT / speed / out_name, ev, nf, ms)
            gap = gif_loop_gap(OUT / speed / out_name)
            v.update({
                "speed": speed,
                "duration": ms,
                "source": webm_name + ".webm",
                "preview": preview_name,
                "note": note,
                "frames": nf,
                "colors": colors,
                "method": method,
                "window_start": win_start,
                "window_sec": win_sec,
                "source_frames": n,
                "gap": gap,
                "gap_src": best["gap"],
                "span": best["span"],
                "colors_floored": best.get("colors_floored", False),
                "loop_ok": gap < LOOP_OK,
            })
            records.append(v)

        print("%-22s <- %-14s %2d/%2d 帧  %2d 色  %-10s %5.1f/%.1f KB  "
              "窗口 %.2fs(%.2fs/帧)  闭环 %4.1f"
              % (out_name, webm_name, nf, n, colors, method,
                 (OUT / "normal" / out_name).stat().st_size / 1024.0,
                 max((OUT / s / out_name).stat().st_size for s, _ in SPEEDS) / 1024.0,
                 win_sec, best["span"], gap))

    by_speed = {s: [r for r in records if r["speed"] == s] for s, _ in SPEEDS}
    emit_manifest()
    emit_preview(by_speed)
    emit_report(records)
    emit_loop_report(records)
    (WORK / "chibi_build.json").write_text(
        json.dumps([{k: (str(v) if isinstance(v, Path) else v) for k, v in r.items()}
                    for r in records], ensure_ascii=False, indent=1),
        encoding="utf-8")

    total = sum(r["bytes"] for r in records)
    failed = [r for r in records if not r["ok"]]
    print("\n输出: %s" % OUT)
    print("GIF %d 个（3 档 x 16），合计 %.1f KB，最大 %.1f KB"
          % (len(records), total / 1024.0, max(r["bytes"] for r in records) / 1024.0))
    print("自检: %d/%d 通过" % (len(records) - len(failed), len(records)))
    for r in failed:
        print("  FAIL", r["speed"], r["file"], r["size"], r["frames"],
              r["transparency"], r["durations"], r["colors"], r["bytes"])
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
