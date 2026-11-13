# -*- coding: utf-8 -*-
"""三个 UI 方向的效果图（320×240 实机坐标，统一 2 倍放大）。

A 极简仪表盘 / B 角色为主 / C 场景化（角色 + 终端小窗）
"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, "..", "assets", "refs")
OUT = os.path.join(HERE, "..", "docs", "img", "ui-directions.png")

SW, SH = 320, 240
K = 2.0
PAD = 14
GAP = 44
COLS = 3

W = 60 * 2 + COLS * (SW * 2 * K // 2 + PAD * 2) + GAP * (COLS - 1)
BW = SW * 2 // 1  # 640 占位，下面重算

CW = int(SW * K)          # 640
CH = int(SH * K)          # 480
BOXW = CW + PAD * 2
BOXH = CH + PAD * 2
W = 60 * 2 + COLS * BOXW + GAP * (COLS - 1)
H = 810

BG = "#F4F7FA"
INK = "#16202B"
MUTED = "#6B7A8C"
SCREEN = "#0B1512"

FR = "C:/Windows/Fonts/msyh.ttc"
FB = "C:/Windows/Fonts/msyhbd.ttc"
FM = "C:/Windows/Fonts/consola.ttf"

C_IDLE = "#4ADE80"
C_THINK = "#60A5FA"
C_WORK = "#FBBF24"
C_DONE = "#34D399"
C_ERR = "#F87171"


def font(size, bold=False):
    return ImageFont.truetype(FB if bold else FR, int(size * K))


def mono(size):
    return ImageFont.truetype(FM, int(size * K))


class Screen:
    """以 320×240 坐标作画，内部乘 K。"""

    def __init__(self, ox, oy, bg=SCREEN):
        self.ox = self.oy = 0   # 内部作画坐标系，外部 paste 定位
        self.img = Image.new("RGB", (CW, CH), bg)
        self.d = ImageDraw.Draw(self.img)

    def px(self, x, y):
        return (x * K, y * K)

    def rect(self, x1, y1, x2, y2, fill=None, outline=None, r=0, w=1):
        box = [self.ox + x1 * K, self.oy + y1 * K, self.ox + x2 * K, self.oy + y2 * K]
        if r:
            self.d.rounded_rectangle(box, radius=r * K, fill=fill, outline=outline, width=int(w * K))
        else:
            self.d.rectangle(box, fill=fill, outline=outline, width=int(w * K))

    def text(self, x, y, s, size, color="#E6F7EE", bold=False, anchor="la", f=None):
        self.d.text((self.ox + x * K, self.oy + y * K), s, font=f or font(size, bold),
                    fill=color, anchor=anchor)

    def dot(self, x, y, r, color):
        self.d.ellipse([self.ox + (x - r) * K, self.oy + (y - r) * K,
                        self.ox + (x + r) * K, self.oy + (y + r) * K], fill=color)

    def bar(self, x, y, w, h, pct, color, track="#1B2B23"):
        self.rect(x, y, x + w, y + h, fill=track, r=h / 2)
        if pct > 0:
            self.rect(x, y, x + max(h, w * pct), y + h, fill=color, r=h / 2)

    def paste_char(self, path, idx, cx, cy, target_h, cw=192, ch=208, cols=8):
        sheet = Image.open(path).convert("RGBA")
        r, c = divmod(idx, cols)
        cell = sheet.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch))
        b = cell.getbbox()
        if b:
            cell = cell.crop(b)
        k = target_h * K / cell.size[1]
        cell = cell.resize((max(1, int(cell.size[0] * k)), int(target_h * K)), Image.LANCZOS)
        x = int(self.ox + cx * K - cell.size[0] / 2)
        y = int(self.oy + cy * K - cell.size[1] / 2)
        self.img.paste(cell, (x, y), cell)


img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)
d.text((60, 40), "UI 三种方向 · 320 × 240", font=ImageFont.truetype(FB, 40), fill=INK)
d.text((60, 96), "同一块屏、同一套数据，只换信息组织方式；角色素材取鲸鱼娘（BSD-3）", font=ImageFont.truetype(FR, 19), fill=MUTED)

WHALE = os.path.join(REF, "whale-sprite.webp")

# ---------------- A 极简仪表盘 ----------------
A = Screen(60 + PAD, 170 + PAD)
A.rect(0, 0, SW, 24, fill="#101C17")
A.text(8, 5, "DSH", 10, C_IDLE, True)
A.text(34, 6, "holocubic", 8, "#7E9C8C")
A.dot(270, 12, 3, C_WORK)
A.text(306, 6, "12m", 8, "#7E9C8C", anchor="ra")

A.text(160, 62, "执行中", 34, "#FFF7E6", True, anchor="ma")
A.text(160, 104, "bash", 14, C_WORK, anchor="ma")
A.rect(60, 126, 260, 127, fill="#1B2B23")

A.text(40, 142, "上下文", 10, "#7E9C8C")
A.bar(40, 158, 240, 6, 0.55, C_WORK)
A.text(40, 172, "本轮 12.4k tokens", 10, "#7E9C8C")
A.text(40, 190, "3 个会话 · 今日 48.2k", 9, "#5C7368")

A.rect(0, 212, SW, 240, fill="#0E1814")
A.text(10, 222, "DeepSeek Harness", 8, "#5C7368")
A.text(310, 222, "idle 2h", 8, "#5C7368", anchor="ra")

# ---------------- B 角色为主 ----------------
B = Screen(60 + BOXW + GAP + PAD, 170 + PAD)
B.rect(0, 0, SW, SH, fill=SCREEN)
# 状态色描边
B.rect(1, 1, SW - 1, SH - 1, outline=C_THINK, r=6, w=2)
B.paste_char(WHALE, 2, 160, 96, 136)
# 顶部极简
B.dot(14, 16, 4, C_THINK)
B.text(24, 10, "思考中", 11, "#E6F7EE", True)
B.text(306, 10, "12m", 9, "#7E9C8C", anchor="ra")
# 底部渐变遮罩
ov = Image.new("RGBA", (int(SW * K), int(60 * K)), (0, 0, 0, 0))
od = ImageDraw.Draw(ov)
for i in range(int(60 * K)):
    a = int(200 * (i / (60 * K)) ** 1.4)
    od.line([(0, i), (int(SW * K), i)], fill=(11, 21, 18, a))
B.img.paste(ov, (0, int((SH - 60) * K)), ov)
B.text(16, 204, "deepseek-reasoner", 9, "#A8C2B5")
B.text(16, 220, "上下文 42%", 9, "#7E9C8C")
B.bar(120, 221, 168, 5, 0.42, C_THINK)

# ---------------- C 场景化 ----------------
C = Screen(60 + (BOXW + GAP) * 2 + PAD, 170 + PAD)
C.rect(0, 0, SW, 22, fill="#101C17")
C.text(8, 4, "DSH", 9, C_IDLE, True)
C.dot(270, 11, 3, C_WORK)
C.text(306, 5, "12m", 8, "#7E9C8C", anchor="ra")

# 终端小窗
C.rect(10, 28, 310, 116, fill="#0F1A15", outline="#22392D", r=4, w=1)
C.rect(10, 28, 310, 40, fill="#152219", r=4)
C.text(16, 31, "bash", 8, "#8AA596")
C.text(304, 31, "●", 7, C_WORK, anchor="ra")
rows = [("$ npm run build", "#8AA596"),
        ("ok built in 12.4s", C_DONE),
        ("$ edit src/main.lua", "#8AA596"),
        ("> waiting for model", "#5C7368")]
for i, (s, col) in enumerate(rows):
    C.text(18, 46 + i * 16, s, 8, col, f=mono(8))
C.rect(18, 110, 24, 112, fill=C_WORK)

# 角色
C.paste_char(WHALE, 9, 62, 168, 104)

# 右侧状态
C.text(126, 128, "执行中", 24, "#FFF7E6", True)
C.text(126, 158, "上下文 55% · 12.4k", 9, "#7E9C8C")
C.bar(126, 176, 180, 5, 0.55, C_WORK)
C.text(126, 190, "3 会话 · 已运行 12m", 8, "#5C7368")

C.rect(0, 212, SW, 240, fill="#0E1814")
C.text(10, 221, "dsh-holocubic v0.1", 7, "#5C7368")
C.text(310, 221, "8 状态", 7, "#5C7368", anchor="ra")

# ---------------- 拼装 ----------------
for i, (sc, title, desc) in enumerate([
        (A, "A · 极简仪表盘", "角色退场，信息优先"),
        (B, "B · 角色为主", "角色占满，状态在边框"),
        (C, "C · 场景化", "终端小窗 + 角色 + 数据")]):
    ox = 60 + i * (BOXW + GAP)
    oy = 170
    d.rounded_rectangle((ox, oy, ox + BOXW, oy + BOXH), 22, fill="#1A242F")
    img.paste(sc.img, (ox + PAD, oy + PAD))
    d.text((ox, oy + BOXH + 14), title, font=ImageFont.truetype(FB, 22), fill=INK)
    d.text((ox, oy + BOXH + 46), desc, font=ImageFont.truetype(FR, 15), fill=MUTED)

d.text((60, 760), "注：角色为精灵表真实帧（鲸鱼娘 BSD-3），非手绘示意；三套共用同一份状态数据，差别只在信息如何排布。",
       font=ImageFont.truetype(FR, 16), fill=MUTED)

img.save(OUT)
print("ok", OUT, img.size)
