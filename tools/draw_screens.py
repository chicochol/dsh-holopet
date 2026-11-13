# -*- coding: utf-8 -*-
"""HoloCubic 320x240 四状态效果图"""
import os
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(__file__), "..", "docs", "img")
os.makedirs(OUT, exist_ok=True)

W, H = 1840, 1700
BG = "#F6F7F9"
INK = "#1B2430"
MUTED = "#5A6472"

F_N = "C:/Windows/Fonts/msyh.ttc"
F_B = "C:/Windows/Fonts/msyhbd.ttc"
F_M = "C:/Windows/Fonts/consola.ttf"

# 屏幕配色（深色，贴近 holopet 观感）
SCR_BG = "#0E1B16"
SCR_TOP = "#13241C"
SCR_FG = "#E6F7EE"
SCR_DIM = "#7E9C8C"
SCR_LINE = "#1E3A2E"


def font(size, bold=False):
    return ImageFont.truetype(F_B if bold else F_N, size)


def mono(size):
    return ImageFont.truetype(F_M, size)


img = Image.new("RGB", (W, H), BG)
D = ImageDraw.Draw(img)


def text(xy, s, size=20, color=INK, bold=False, anchor="la"):
    D.text(xy, s, font=font(size, bold), fill=color, anchor=anchor)


def mt(xy, s, size=16, color=MUTED, anchor="la"):
    D.text(xy, s, font=mono(size), fill=color, anchor=anchor)


def pet(d, cx, cy, R, mood, col, shade):
    """画一只示意角色"""
    # 影子
    d.ellipse((cx - R * 0.9, cy + R * 0.86, cx + R * 0.9, cy + R * 1.12), fill="#0A1410")
    # 脚
    for sx in (-1, 1):
        d.ellipse((cx + sx * R * 0.42 - R * 0.2, cy + R * 0.72,
                   cx + sx * R * 0.42 + R * 0.2, cy + R * 0.98), fill=shade)
    # 身体
    d.ellipse((cx - R, cy - R * 0.92, cx + R, cy + R * 0.92), fill=col)
    # 肚皮
    d.ellipse((cx - R * 0.6, cy - R * 0.12, cx + R * 0.6, cy + R * 0.86), fill="#FFE6CE")
    # 犄角
    for sx in (-1, 1):
        d.line((cx + sx * R * 0.40, cy - R * 0.74, cx + sx * R * 0.56, cy - R * 0.98),
               fill=shade, width=max(3, int(R * 0.09)))
        d.ellipse((cx + sx * R * 0.56 - R * 0.09, cy - R * 0.98 - R * 0.09,
                   cx + sx * R * 0.62 + R * 0.11, cy - R * 1.12 + R * 0.11), fill=shade)
    # 眼睛
    for sx in (-1, 1):
        ex = cx + sx * R * 0.34
        ey = cy - R * 0.22
        if mood == "idle":
            d.arc((ex - R * 0.2, ey - R * 0.16, ex + R * 0.2, ey + R * 0.18),
                  200, 340, fill="#24170E", width=max(3, int(R * 0.07)))
        else:
            d.ellipse((ex - R * 0.21, ey - R * 0.21, ex + R * 0.21, ey + R * 0.21), fill="#FFFFFF")
            off = {"thinking": -R * 0.07, "working": R * 0.05, "done": 0}.get(mood, 0)
            d.ellipse((ex - R * 0.115 + sx * R * 0.03, ey - R * 0.115 + off,
                       ex + R * 0.115 + sx * R * 0.03, ey + R * 0.115 + off), fill="#1B2430")
            d.ellipse((ex - R * 0.06 + sx * R * 0.06, ey - R * 0.09 + off,
                       ex - R * 0.005 + sx * R * 0.06, ey - R * 0.035 + off), fill="#FFFFFF")
    # 嘴
    if mood == "done":
        d.chord((cx - R * 0.28, cy + R * 0.1, cx + R * 0.28, cy + R * 0.52), 0, 180, fill="#24170E")
    else:
        d.arc((cx - R * 0.22, cy + R * 0.12, cx + R * 0.22, cy + R * 0.42),
              20, 160, fill="#24170E", width=max(3, int(R * 0.065)))
    # 状态附件
    if mood == "thinking":
        for i, rr in enumerate((R * 0.15, R * 0.11, R * 0.075)):
            by = cy - R * 0.95 - i * R * 0.26
            d.ellipse((cx + R * 0.72 - rr, by - rr, cx + R * 0.72 + rr, by + rr),
                      fill="#8FB8FF")
    elif mood == "working":
        # 手里的工具
        d.rounded_rectangle((cx + R * 0.62, cy + R * 0.02, cx + R * 0.98, cy + R * 0.42),
                            radius=int(R * 0.06), fill="#C8D3E0")
        d.rectangle((cx + R * 0.74, cy + R * 0.36, cx + R * 0.86, cy + R * 0.72), fill="#8A6A50")
    elif mood == "done":
        for sx, sy in ((-0.95, -0.55), (0.98, -0.35), (0.72, -0.9)):
            sx_x, sy_y = cx + R * sx, cy + R * sy
            r2 = R * 0.1
            d.line((sx_x - r2, sy_y, sx_x + r2, sy_y), fill="#FFD666", width=max(2, int(R * 0.05)))
            d.line((sx_x, sy_y - r2, sx_x, sy_y + r2), fill="#FFD666", width=max(2, int(R * 0.05)))


def screen(ox, oy, state, label, accent):
    """在 (ox,oy) 画一块 800x600 的屏幕（对应真实 320x240）"""
    S = 800 / 320.0

    # 机身
    D.rounded_rectangle((ox - 26, oy - 26, ox + 800 + 26, oy + 600 + 26), radius=22, fill="#22282F")
    D.rounded_rectangle((ox, oy, ox + 800, oy + 600), radius=8, fill=SCR_BG)

    def P(x, y):
        return (ox + x * S, oy + y * S)

    # 顶栏
    D.rectangle((ox, oy, ox + 800, oy + 26 * S), fill=SCR_TOP)
    D.line((P(0, 26)[0], P(0, 26)[1], P(320, 26)[0], P(320, 26)[1]), fill=SCR_LINE, width=2)
    D.text(P(8, 7), "DSH", font=font(13, True), fill="#6EE7A8")
    D.text(P(44, 8), "holocubic", font=font(12), fill=SCR_DIM)
    D.ellipse((P(292, 9)[0], P(292, 9)[1], P(301, 18)[0], P(301, 18)[1]), fill=accent)
    D.text(P(305, 8), "12m", font=font(10), fill=SCR_DIM)

    # 动画区 160x160
    cx, cy = P(160, 110)
    R = 160 * S * 0.30
    mood = {"idle": "idle", "thinking": "thinking", "working": "working", "done": "done"}[state]
    col, shade = {"idle": ("#D98E4A", "#A9662F"),
                  "thinking": ("#E8934A", "#B06A2C"),
                  "working": ("#E07B3C", "#A85A26"),
                  "done": ("#F0A05A", "#B87434")}[state]
    pet(D, cx, cy, R, mood, col, shade)

    # 底栏
    D.text(P(10, 198), label, font=font(17, True), fill=SCR_FG)
    D.text(P(10, 220), {
        "idle": "上次 12 分钟前",
        "thinking": "deepseek · 上下文 42%",
        "working": "bash · 上下文 55%",
        "done": "本轮 12.4k tokens",
    }[state], font=font(10), fill=SCR_DIM)
    # 进度条
    D.rounded_rectangle(P(10, 232) + P(310, 238), radius=3, fill="#1C3329")
    frac = {"idle": 0.12, "thinking": 0.42, "working": 0.55, "done": 1.0}[state]
    D.rounded_rectangle(P(10, 232) + P(10 + 300 * frac, 238), radius=3, fill=accent)

    # 状态标签
    text((ox - 10, oy - 74), label, 24, INK, True)
    mt((ox + 132, oy - 64), state, 18, MUTED)


# ---------- 标题 ----------
text((60, 46), "HoloCubic 屏幕效果 · 320 × 240", 42, INK, True)
text((62, 104), "四状态并排（此处按 2.5 倍放大；角色为示意，实际用 GIF 逐帧动画）", 21, MUTED)

screen(80, 240, "idle", "待命", "#4ADE80")
screen(990, 240, "thinking", "思考中", "#60A5FA")
screen(80, 990, "working", "执行 bash", "#F59E0B")
screen(990, 990, "done", "完成", "#34D399")

text((60, 1650), "顶栏：项目名 · 在线点 · 会话计时　|　中间：160×160 动画区　|　底栏：状态 + 上下文占用条", 19, MUTED)

img.save(os.path.join(OUT, "screen-states.png"))
print("ok")
