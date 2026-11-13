# -*- coding: utf-8 -*-
"""DSH -> HoloCubic 架构图 v2（自写插件路线），1680x1160"""
import os
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(__file__), "..", "docs", "img")
os.makedirs(OUT, exist_ok=True)

W, H = 1680, 1160
BG = "#F6F7F9"
INK = "#1B2430"
MUTED = "#5A6472"
LINE = "#D3DAE4"
ARROW = "#8494A8"

BLUE, BLUE_BG = "#2B5F9E", "#E9F1FA"
ORANGE, ORANGE_BG = "#BC5E28", "#FBEFE6"
GREEN, GREEN_BG = "#2C7A5B", "#E6F3ED"
PURPLE = "#6B4FA8"

F_N = "C:/Windows/Fonts/msyh.ttc"
F_B = "C:/Windows/Fonts/msyhbd.ttc"
F_M = "C:/Windows/Fonts/consola.ttf"


def font(size, bold=False):
    return ImageFont.truetype(F_B if bold else F_N, size)


def mono(size):
    return ImageFont.truetype(F_M, size)


img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)


def rr(box, r, fill=None, outline=None, width=2):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def text(xy, s, size=20, color=INK, bold=False, anchor="la"):
    d.text(xy, s, font=font(size, bold), fill=color, anchor=anchor)


def mt(xy, s, size=17, color=MUTED, anchor="la"):
    d.text(xy, s, font=mono(size), fill=color, anchor=anchor)


def cjk(s):
    return any("\u4e00" <= c <= "\u9fff" for c in s)


def smart(xy, s, size=15, color=INK, bold=False):
    """含中文用雅黑，纯 ASCII 用等宽"""
    if cjk(s):
        text(xy, s, size, color, bold)
    else:
        d.text(xy, s, font=mono(size), fill=color)


def arrow(p1, p2, color=ARROW, width=3, head=13):
    import math
    x1, y1 = p1
    x2, y2 = p2
    d.line([p1, p2], fill=color, width=width)
    a = math.atan2(y2 - y1, x2 - x1)
    d.polygon([
        (x2, y2),
        (x2 - head * math.cos(a - 0.42), y2 - head * math.sin(a - 0.42)),
        (x2 - head * math.cos(a + 0.42), y2 - head * math.sin(a + 0.42)),
    ], fill=color)


# ---------- 标题 ----------
text((60, 46), "DSH 状态监控 · HoloCubic 打通方案", 42, INK, True)
text((62, 104), "推荐架构：一个自写 DSH 插件当桥 · 局域网 SSE 直连 · 设备端零改造", 21, MUTED)

Y0, Y1 = 170, 900

# ================= 左：DSH =================
rr((60, Y0, 700, Y1), 18, "#FFFFFF", LINE, 2)
rr((60, Y0, 700, Y0 + 62), 18, BLUE)
rr((60, Y0 + 40, 700, Y0 + 62), 0, BLUE)
text((84, Y0 + 12), "①  DSH Desktop", 25, "#FFFFFF", True)
text((520, Y0 + 22), "Windows 本机", 17, "#D6E4F5")

# Web GUI
rr((88, Y0 + 86, 672, Y0 + 184), 12, BLUE_BG, BLUE, 2)
text((108, Y0 + 100), "Web GUI", 21, BLUE, True)
mt((108, Y0 + 130), "127.0.0.1:44945", 18, BLUE)
text((108, Y0 + 158), "浏览器专用 · 只绑回环 · 每次启动换端口", 15, "#8A5B2E")

# 事件总线
rr((88, Y0 + 196, 672, Y0 + 396), 12, "#FFFFFF", "#B9CBE3", 2)
text((108, Y0 + 210), "Cordis 事件总线", 21, INK, True)
text((320, Y0 + 216), "进程内对象，不是端口", 15, MUTED)
events = ["turn/start", "assistant/chunk", "tool/call", "tool/result", "approval/asked", "turn/end"]
for i, e in enumerate(events):
    cx = 108 + (i % 2) * 276
    cy = Y0 + 250 + (i // 2) * 36
    d.ellipse((cx, cy + 7, cx + 8, cy + 15), fill=PURPLE)
    mt((cx + 18, cy), e, 16, MUTED)
text((108, Y0 + 362), "另有 subagent/* · compaction/* · llm/retry", 15, MUTED)

# 插件
rr((88, Y0 + 416, 672, Y0 + 646), 12, ORANGE_BG, ORANGE, 2)
text((108, Y0 + 430), "dsh-holocubic 插件", 21, ORANGE, True)
text((420, Y0 + 436), "新写 · 约 150 行", 15, "#9A5B33")
rows = [("1", "ctx.on('session/event')", "订阅全部事件"),
        ("2", "折叠成 8 态 + 元数据", "项目 · 工具 · token"),
        ("3", "node:http 自建服务", "自己 listen，绕开 webServer")]
for i, (n, a, b) in enumerate(rows):
    cy = Y0 + 466 + i * 42
    d.ellipse((108, cy + 4, 136, cy + 32), fill=ORANGE)
    text((122, cy + 18), n, 16, "#FFFFFF", True, anchor="mm")
    smart((150, cy + 2), a, 15, INK)
    text((150, cy + 26), b, 14, MUTED)

rr((108, Y0 + 604, 372, Y0 + 634), 8, "#2B3442")
mt((124, Y0 + 612), "0.0.0.0:17890", 17, "#8BE8B0")

text((88, Y0 + 668), "官方 webServer 拒绝绑 0.0.0.0（怕暴露 RCE）", 15, "#8A5B2E")
text((88, Y0 + 696), "→ 插件自己 listen 是唯一干净的出口", 15, "#8A5B2E")

# ================= 右：设备 =================
rr((980, Y0, 1620, Y1), 18, "#FFFFFF", LINE, 2)
rr((980, Y0, 1620, Y0 + 62), 18, GREEN)
rr((980, Y0 + 40, 1620, Y0 + 62), 0, GREEN)
text((1004, Y0 + 12), "②  HoloCubic", 25, "#FFFFFF", True)
text((1440, Y0 + 22), "192.168.1.x", 17, "#CFE9DC")

# 设备外框 + 4:3 屏幕
DW, DH = 384, 288
DX, DY = 1108, Y0 + 100
rr((DX - 20, DY - 20, DX + DW + 20, DY + DH + 20), 16, "#22282F", None, 0)
rr((DX, DY, DX + DW, DY + DH), 6, "#0E1B16", None, 0)

k = DW / 320.0


def S(x, y):
    return (DX + x * k, DY + y * k)


d.line([S(0, 26), S(320, 26)], fill="#1E3A2E", width=1)
text(S(10, 6), "DSH", 15, "#6EE7A8", True)
text(S(52, 7), "holocubic", 14, "#7E9C8C")
d.ellipse([S(286, 8), S(296, 18)], fill="#4ADE80")
text(S(300, 7), "12m", 12, "#7E9C8C")

bx = (320 - 160) / 2
d.rounded_rectangle([S(bx, 34), S(bx + 160, 194)], radius=6, outline="#2A4A3C", width=2)
d.text(((S(bx, 34)[0] + S(bx + 160, 194)[0]) / 2, (S(bx, 34)[1] + S(bx + 160, 194)[1]) / 2),
       "160×160", font=font(14), fill="#3F6B58", anchor="mm")

text(S(12, 200), "思考中", 18, "#E6F7EE", True)
text(S(256, 198), "42%", 12, "#7E9C8C")
d.rounded_rectangle([S(12, 226), S(308, 232)], radius=3, fill="#1C3329")
d.rounded_rectangle([S(12, 226), S(196, 232)], radius=3, fill="#3FBF7F")

# 部署路径
text((1004, Y0 + 452), "部署路径", 17, MUTED, True)
mt((1004, Y0 + 480), "/sd/apps/dsh_pet/", 18, GREEN)
text((1004, Y0 + 514), "main.lua 改皮 · assets/*.gif 替换 · 状态枚举沿用", 15, MUTED)

# 帧示例
text((1004, Y0 + 560), "设备收到的帧（每帧 <1KB）", 16, INK, True)
frame = ['{ "state": "working",',
         '  "event": "PreToolUse",',
         '  "project": "HoloCubic",',
         '  "tool": "bash",',
         '  "ctx": 0.42,',
         '  "ts": 1762658400 }']
for i, ln in enumerate(frame):
    mt((1004, Y0 + 592 + i * 24), ln, 14, "#3A4A5E")

# ================= 连线 =================
ymid = DY + DH / 2
arrow((704, ymid), (976, ymid), GREEN, 4, 15)
text((704, ymid - 70), "局域网 SSE 直连", 17, GREEN, True)
mt((704, ymid - 44), "GET /events", 15, PURPLE)
text((704, ymid + 22), "无中间进程 · 心跳 10s", 14, MUTED)

for y in range(Y0 - 20, Y1 + 40, 22):
    d.line([(840, y), (840, y + 10)], fill="#C9B79B", width=2)
text((840, Y1 + 36), "回环 / 局域网 边界", 15, "#A08860", anchor="ma")

# ================= 底部映射 =================
text((60, 946), "事件怎么落到设备的 8 个状态（设备靠它选 GIF）", 24, INK, True)

chips = [
    ("assistant/chunk", "thinking", "思考", "#3B72B8"),
    ("tool/call", "working", "工作", "#C0672E"),
    ("tool/result", "error", "失败 / 检查", "#B03A48"),
    ("approval/asked", "notification", "待确认", "#8A6A1F"),
    ("turn/end", "done", "完成", "#2C7A5B"),
    ("断流 30s", "—", "离线", "#8A929E"),
]
cw, gap = 250, 16
x = 60
for evname, st, label, col in chips:
    rr((x, 992, x + cw, 1092), 12, "#FFFFFF", col, 2)
    smart((x + 16, 1004), evname, 15, MUTED)
    d.text((x + 16, 1036), "→ " + st, font=mono(16), fill=col)
    text((x + 16, 1064), label, 15, INK)
    x += cw + gap

img.save(os.path.join(OUT, "architecture.png"))
print("ok")
