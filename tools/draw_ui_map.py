# -*- coding: utf-8 -*-
"""画「大肥鱼」两个界面的区域说明图：真实 320x240 布局 + 编号标注 + 图例。"""
import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1780, 1320
S = 2.5                       # 放大倍数
F = "C:/Windows/Fonts/msyh.ttc"
FB = "C:/Windows/Fonts/msyhbd.ttc"

BG = "#F4F6F9"
INK = "#0F172A"
MUTED = "#64748B"
ACC = "#0EA5E9"
SCR_BG = "#0E1B16"
SCR_PANEL = "#13241C"
SCR_LINE = "#2A4034"
SCR_FG = "#E6F7EE"
SCR_DIM = "#7E9C8C"
SCR_ACC = "#4ADE80"


def font(sz, bold=False):
    return ImageFont.truetype(FB if bold else F, sz)


img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)


def text(xy, s, sz=18, color=INK, bold=False, anchor=None):
    d.text(xy, s, font=font(sz, bold), fill=color, anchor=anchor)


def P(x, y, ox, oy):
    """逻辑坐标 → 画面坐标"""
    return (ox + x * S, oy + y * S)


def rect(x, y, w, h, ox, oy, color, radius=0, outline=None, width=1):
    x0, y0 = P(x, y, ox, oy)
    x1, y1 = P(x + w, y + h, ox, oy)
    d.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=color,
                        outline=outline, width=width)


# ---------------------------------------------------------------- 标题
text((44, 30), "大肥鱼 · 两个界面的区域说明", 40, INK, True)
text((44, 84), "左：B 界面（角色为主）　右：C 界面（场景化终端）"
              "　编号对应下方图例；所有坐标都是设备真实 320×240 布局", 19, MUTED)

OX_B, OY = 44, 152
OX_C = 940


# ---------------------------------------------------------------- 屏幕外壳
def body(ox, oy, label):
    x0, y0 = P(-10, -10, ox, oy)
    x1, y1 = P(330, 250, ox, oy)
    d.rounded_rectangle((x0, y0, x1, y1), radius=26, fill="#1B2530")
    x0, y0 = P(0, 0, ox, oy)
    x1, y1 = P(320, 240, ox, oy)
    d.rectangle((x0, y0, x1, y1), fill=SCR_BG)
    # 页名交给下方图例标题，屏上不再重复标注，避免和图例撞行
    _ = label


body(OX_B, OY, "B 界面 · 角色为主")
body(OX_C, OY, "C 界面 · 场景化终端")


# ---------------------------------------------------------------- B 页内容
def draw_b(ox, oy):
    # 顶栏
    text(P(10, 3, ox, oy), "DSH // 执行中", 26, SCR_ACC, True)
    text(P(249, 5, ox, oy), "LIVE", 20, SCR_DIM, anchor="ra")
    text(P(311, 5, ox, oy), "14:32", 22, "#A8C2B5", anchor="ra")
    # 角色
    cx, cy = P(160, 110, ox, oy)
    r = 58 * S / 2.5
    d.ellipse((cx - 92, cy - 92, cx + 92, cy + 92), fill="#16302A")
    rect(80, 28, 160, 160, ox, oy, None, radius=12,
         outline="#2F5D4C", width=2)
    text((cx, cy), "皮肤 GIF 160×160", 21, "#4F7A68", anchor="mm")
    # 底栏
    rect(0, 196, 320, 44, ox, oy, SCR_PANEL, outline=SCR_LINE)
    rect(0, 196, 102, 21, ox, oy, "#D8ECDF")
    text(P(6, 198, ox, oy), "执行中", 24, "#0E1B16", True)
    text(P(108, 197, ox, oy), ">", 24, "#D8ECDF")
    text(P(116, 200, ox, oy), "HoloCubic", 20, SCR_ACC)
    text(P(309, 201, ox, oy), "dsh", 16, SCR_DIM, anchor="ra")
    rect(0, 219, 58, 21, ox, oy, "#22362C")
    text(P(4, 220, ox, oy), "12m", 16, SCR_FG)
    rect(58, 219, 58, 21, ox, oy, "#4ADE80")
    text(P(62, 220, ox, oy), "3s", 16, "#0E1B16")
    text(P(122, 224, ox, oy), "38%", 15, "#A8C2B5")
    rect(178, 228, 84, 4, ox, oy, SCR_LINE)
    rect(178, 228, 32, 4, ox, oy, "#4ADE80")
    text(P(309, 224, ox, oy), "R2d", 15, SCR_DIM, anchor="ra")


draw_b(OX_B, OY)


# ---------------------------------------------------------------- C 页内容
def draw_c(ox, oy):
    text(P(9, 4, ox, oy), "SESSION // LIVE", 24, SCR_ACC, True)
    text(P(311, 5, ox, oy), "14:32", 22, "#A8C2B5", anchor="ra")
    # 终端窗
    rect(4, 22, 312, 110, ox, oy, SCR_PANEL, outline=SCR_LINE)
    text(P(8, 24, ox, oy), "deepseek-flash", 16, SCR_ACC)
    rect(4, 38, 310, 26, ox, oy, "#4ADE80")
    text(P(9, 42, ox, oy), "执行中", 20, "#0E1B16", True)
    text(P(309, 44, ox, oy), "bash", 17, "#0E1B16", anchor="ra")
    rows = ["$ npm run build", "ok built in 12.4s", "$ edit src/main.lua",
            "> waiting for model"]
    for i, row in enumerate(rows):
        text(P(10, 68 + i * 12, ox, oy), row, 15, SCR_DIM)
    # 角色区（空）
    rect(4, 136, 96, 92, ox, oy, SCR_PANEL, outline="#4ADE80", width=2)
    text(P(52, 182, ox, oy), "（空）", 22, "#B45309", bold=True, anchor="mm")
    # 上下文面板
    rect(104, 136, 212, 92, ox, oy, SCR_BG, outline=SCR_LINE)
    rect(104, 136, 39, 18, ox, oy, "#4ADE80")
    text(P(107, 138, ox, oy), "CTX", 14, "#0E1B16", True)
    text(P(309, 138, ox, oy), "12.6%", 15, "#A8C2B5", anchor="ra")
    rect(110, 162, 200, 6, ox, oy, SCR_LINE)
    rect(110, 162, 25, 6, ox, oy, "#4ADE80")
    text(P(110, 176, ox, oy), "126K / 1M", 15, SCR_DIM)


draw_c(OX_C, OY)


# ---------------------------------------------------------------- 标注层
overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
od = ImageDraw.Draw(overlay)

FILL = (14, 165, 233, 42)
LINE = (14, 165, 233, 210)


def mark(ox, oy, x, y, w, h, num, small=False, nofill=False):
    x0, y0 = P(x, y, ox, oy)
    x1, y1 = P(x + w, y + h, ox, oy)
    od.rounded_rectangle((x0, y0, x1, y1), radius=5,
                         fill=None if nofill else FILL,
                         outline=LINE, width=2)
    cx = x0 + 15 if not small else (x0 + x1) / 2
    cy = y0 + 13 if not small else (y0 + y1) / 2
    rad = 13
    od.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=(2, 132, 199, 255))
    od.text((cx, cy + 1), num, font=font(15, True), fill=(255, 255, 255, 255),
            anchor="mm")


B_REGIONS = [
    ("1", 10, 3, 190, 20, False), ("2", 202, 5, 47, 18, False),
    ("3", 253, 5, 58, 18, False), ("4", 0, 20, 320, 180, False),
    ("5", 0, 196, 102, 21, False), ("6", 103, 196, 10, 19, True),
    ("7", 114, 199, 132, 17, False), ("8", 262, 200, 47, 15, True),
    ("9", 0, 219, 58, 21, False), ("10", 58, 219, 58, 21, False),
    ("11", 120, 223, 55, 14, True), ("12", 178, 228, 84, 4, True),
    ("13", 264, 223, 52, 14, True),
]
for num, x, y, w, h, small in B_REGIONS:
    mark(OX_B, OY, x, y, w, h, num, small)

C_REGIONS = [
    ("1", 9, 4, 220, 18, False), ("2", 253, 5, 58, 18, False),
    ("3", 4, 22, 312, 110, False), ("4", 8, 24, 150, 14, True),
    ("5", 160, 24, 150, 14, True), ("6", 4, 38, 310, 26, False),
    ("7", 10, 66, 300, 60, False), ("8", 4, 136, 96, 92, False),
    ("9", 104, 136, 212, 92, True), ("10", 148, 138, 160, 14, True),
    ("11", 110, 162, 200, 6, True), ("12", 110, 176, 200, 14, True),
]
for num, x, y, w, h, small in C_REGIONS:
    mark(OX_C, OY, x, y, w, h, num, small, nofill=(num == "3"))

img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
d = ImageDraw.Draw(img)


# ---------------------------------------------------------------- 图例
def legend(x, y, title, items, colr):
    text((x, y), title, 24, INK, True)
    yy = y + 42
    for num, name, desc in items:
        d.ellipse((x, yy + 3, x + 20, yy + 23), fill=colr)
        d.text((x + 10, yy + 14), num, font=font(12, True), fill="white",
               anchor="mm")
        text((x + 30, yy), name, 17, INK, True)
        text((x + 30 + 118, yy + 1), desc, 16, MUTED)
        yy += 30


legend(44, 812, "B 界面（状态页）", [
    ("1", "状态标题", "DSH // 执行中 —— 当前 8 态之一"),
    ("2", "连接态", "LIVE / WAIT —— SSE 是否连着"),
    ("3", "时钟", "设备本地时间 HH:MM"),
    ("4", "角色区", "皮肤 GIF，160×160 透明，居中"),
    ("5", "状态大字", "同 1，浅底深字，最醒目"),
    ("6", "箭头", "装饰，指向项目名"),
    ("7", "项目名", "DSH 当前工作目录的项目名"),
    ("8", "来源", "数据来源标识（dsh）"),
    ("9", "本轮计时", "本轮对话已持续时间"),
    ("10", "状态计时", "当前状态已持续多久"),
    ("11", "用量文字", "上下文占用百分比"),
    ("12", "用量条", "同 11 的图形化，84×4"),
    ("13", "重置倒计时", "Claude 周配额残留，DSH 下需替换"),
], (2, 132, 199))

legend(930, 812, "C 界面（会话页）", [
    ("1", "标题", "SESSION // LIVE"),
    ("2", "时钟", "设备本地时间"),
    ("3", "终端窗", "整体容器，312×110"),
    ("4", "模型名（左）", "当前模型，如 deepseek-flash"),
    ("5", "模型名（右）", "预留位，目前为空"),
    ("6", "状态条", "状态大字 + 右侧工具名"),
    ("7", "命令流", "最近 5 条事件，每行一条"),
    ("8", "角色区", "96×92 —— 现在没有素材，是空的"),
    ("9", "上下文面板", "整体容器，212×92"),
    ("10", "百分比", "上下文占用，右上角"),
    ("11", "进度条", "200×6，同 10"),
    ("12", "tokens", "已用 / 窗口，如 126K / 1M"),
], (217, 119, 6))

text((44, 1288), "注：编号 9–13（B 页）沿用自 holopet 的 Claude 用量面板，"
                 "DSH 没有周配额概念，这几处需要按 DSH 的真实指标重定义。", 18, "#B45309")

out = "docs/img/ui-map.png"
os.makedirs(os.path.dirname(out), exist_ok=True)
img.save(out)
print("ok", out, img.size)
