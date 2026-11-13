"""画「外观配色 → 界面区域」对照图：真实 A/B 页布局 + 细箭头指向配色标签。"""

from PIL import Image, ImageDraw, ImageFont

FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"
FONT_REG = "C:/Windows/Fonts/msyh.ttc"
FONT_MONO = "C:/Windows/Fonts/consola.ttf"

W, H = 1400, 800
BG = "#0a0d12"

C = {
    "bg": "#0B1512",
    "panel": "#13241C",
    "line": "#2A4034",
    "track": "#223A2E",
    "cream": "#F2FBF6",
    "peach": "#A8C2B5",
    "dim": "#7E9C8C",
    "rust": "#4ADE80",
    "mint": "#4ADE80",
    "warn": "#FBBF24",
    "error": "#F87171",
}

img = Image.new("RGBA", (W, H), BG + (255,) if isinstance(BG, tuple) else BG)
d = ImageDraw.Draw(img)


def f(path, size):
    return ImageFont.truetype(path, size)


F_TITLE = f(FONT_BOLD, 26)
F_LABEL = f(FONT_BOLD, 15)
F_HEX = f(FONT_MONO, 12)
F_TINY = f(FONT_BOLD, 9)
F_MICRO = f(FONT_REG, 8)


def arrow(p0, p1, color="#5b9cff", width=2, head=7):
    """细长箭头：4 倍超采样后缩小，避免 1px 阶梯状的锯齿。"""
    import math
    ss = 4
    layer = Image.new("RGBA", (W * ss, H * ss), (0, 0, 0, 0))
    dl = ImageDraw.Draw(layer)
    a0 = (p0[0] * ss, p0[1] * ss)
    a1 = (p1[0] * ss, p1[1] * ss)
    dl.line([a0, a1], fill=color, width=width * ss)
    ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    hh = head * ss
    for s in (-1, 1):
        off = ang + s * 0.44
        tip = (a1[0] - hh * math.cos(off), a1[1] - hh * math.sin(off))
        dl.line([a1, tip], fill=color, width=width * ss)
    layer = layer.resize((W, H), Image.LANCZOS)
    img.alpha_composite(layer)


def tag_left(x, y, name, key):
    """左侧标签：名称在色块上方，箭头从色块右缘出发。"""
    d.text((x, y - 20), name, font=F_LABEL, fill="#e8eef7")
    d.text((x, y + 30), key, font=F_MICRO, fill="#8b9bb4")
    d.rounded_rectangle([x, y, x + 34, y + 24], 5, fill=C[key], outline="#3a4b64", width=1)
    return (x + 36, y + 12)


def tag_right(x, y, name, key):
    """右侧标签：名称在色块上方右对齐，箭头从色块左缘出发。"""
    d.text((x + 34, y - 20), name, font=F_LABEL, fill="#e8eef7", anchor="ra")
    d.text((x + 34, y + 30), key, font=F_MICRO, fill="#8b9bb4", anchor="ra")
    d.rounded_rectangle([x, y, x + 34, y + 24], 5, fill=C[key], outline="#3a4b64", width=1)
    return (x - 2, y + 12)


# ---------------- 页面绘制 ----------------
DW, DH = 400, 300
KA = 290
KB = 760
Y0 = 96


def page(dx, dy, name, subtitle):
    """返回 (ox, oy, k) 供坐标换算。"""
    k = DW / 320.0
    d.rounded_rectangle([dx - 8, dy - 8, dx + DW + 8, dy + DH + 8], 12, fill="#1b2233", outline="#2a3550", width=2)
    d.text((dx + 2, dy - 46), name, font=F_TITLE, fill="#e8eef7")
    # 副标题不画：图例里已有说明，避免与标题挤在一起
    _ = subtitle
    return dx, dy, k


def P(ox, oy, k, x, y):
    return (ox + x * k, oy + y * k)


def box(ox, oy, k, x, y, w, h, fill, outline=None, width=1, r=0):
    r0 = [ox + x * k, oy + y * k, ox + (x + w) * k, oy + (y + h) * k]
    if r:
        d.rounded_rectangle(r0, r, fill=fill, outline=outline, width=width)
    else:
        d.rectangle(r0, fill=fill, outline=outline, width=width)


# ===== A 页 =====
ox, oy, k = page(KA, Y0, "A 页 · 角色为主", "顶栏 / 角色动画 / 底部状态条")
box(ox, oy, k, 0, 0, 320, 240, C["bg"])
box(ox, oy, k, 0, 0, 320, 20, C["bg"])
d.text(P(ox, oy, k, 10, 3), "DSH // 待命", font=f(FONT_BOLD, int(14 * k)), fill=C["rust"])
d.text(P(ox, oy, k, 300, 5), "14:32", font=f(FONT_BOLD, int(12 * k)), fill=C["peach"], anchor="ra")
# 角色圆
cx, cy = P(ox, oy, k, 160, 108)
r = 54 * k
d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=C["panel"], outline=C["line"], width=3)
d.ellipse([cx - 16 * k, cy - 16 * k, cx + 16 * k, cy + 16 * k], fill=C["mint"])
# 底栏
box(ox, oy, k, 0, 196, 320, 44, C["bg"], outline=C["line"], width=1)
# 状态条（cream 底 + bg 文字）
box(ox, oy, k, 0, 196, 102, 21, C["cream"])
d.text(P(ox, oy, k, 6, 198), "待命", font=f(FONT_BOLD, int(13 * k)), fill=C["bg"])
d.text(P(ox, oy, k, 114, 199), "HoloCubic", font=f(FONT_BOLD, int(11 * k)), fill=C["rust"])
d.text(P(ox, oy, k, 308, 200), "dsh", font=f(FONT_BOLD, int(10 * k)), fill=C["dim"], anchor="ra")
# 计时条（line 底 + cream 字）
box(ox, oy, k, 0, 219, 58, 21, C["line"])
d.text(P(ox, oy, k, 5, 221), "12m", font=f(FONT_BOLD, int(10 * k)), fill=C["cream"])
# rust 计时条
box(ox, oy, k, 58, 219, 58, 21, C["rust"])
d.text(P(ox, oy, k, 63, 221), "R2d", font=f(FONT_BOLD, int(10 * k)), fill=C["bg"])
# 用量
d.text(P(ox, oy, k, 120, 223), "38%", font=f(FONT_BOLD, int(10 * k)), fill=C["peach"])
box(ox, oy, k, 178, 228, 84, 4, C["line"])
box(ox, oy, k, 178, 228, 84 * 0.38, 4, C["mint"])
d.text(P(ox, oy, k, 308, 223), "R2d", font=f(FONT_BOLD, int(10 * k)), fill=C["dim"], anchor="ra")

# ===== B 页 =====
ox2, oy2, k2 = page(KB, Y0, "B 页 · 场景化终端", "终端窗 / 角色 / 上下文与峰谷")
box(ox2, oy2, k2, 0, 0, 320, 240, C["bg"])
d.text(P(ox2, oy2, k2, 9, 4), "SESSION // LIVE", font=f(FONT_BOLD, int(12 * k2)), fill=C["rust"])
d.text(P(ox2, oy2, k2, 300, 5), "14:32", font=f(FONT_BOLD, int(11 * k2)), fill=C["peach"], anchor="ra")
box(ox2, oy2, k2, 4, 22, 312, 110, C["panel"], outline=C["line"], width=1)
d.text(P(ox2, oy2, k2, 8, 26), "deepseek-flash", font=f(FONT_BOLD, int(9 * k2)), fill=C["rust"])
box(ox2, oy2, k2, 4, 38, 312, 26, C["rust"])
d.text(P(ox2, oy2, k2, 10, 42), "执行中", font=f(FONT_BOLD, int(12 * k2)), fill=C["bg"])
d.text(P(ox2, oy2, k2, 310, 44), "bash", font=f(FONT_BOLD, int(9 * k2)), fill=C["bg"], anchor="ra")
for i in range(5):
    d.text(P(ox2, oy2, k2, 8, 70 + i * 12), ["$ npm run build", "ok built in 12.4s", "$ edit src/main.lua",
                                              "> waiting for model", "· 3 tools"][i],
           font=f(FONT_MONO, int(8 * k2)), fill=C["cream"] if i % 2 == 0 else C["dim"])
# 角色 + 上下文
box(ox2, oy2, k2, 4, 136, 96, 92, C["panel"], outline=C["line"], width=1)
box(ox2, oy2, k2, 104, 136, 212, 92, C["panel"], outline=C["line"], width=1)
box(ox2, oy2, k2, 110, 142, 39, 16, C["mint"])
d.text(P(ox2, oy2, k2, 116, 144), "CTX", font=f(FONT_BOLD, int(9 * k2)), fill=C["bg"])
d.text(P(ox2, oy2, k2, 310, 143), "12.6%", font=f(FONT_BOLD, int(9 * k2)), fill=C["peach"], anchor="ra")
box(ox2, oy2, k2, 110, 166, 200, 6, C["line"])
box(ox2, oy2, k2, 110, 166, 200 * 0.42, 6, C["mint"])
d.text(P(ox2, oy2, k2, 110, 180), "126K / 1M", font=f(FONT_BOLD, int(8 * k2)), fill=C["dim"])
# 峰谷条
box(ox2, oy2, k2, 110, 196, 200, 5, "#3B82F6")
box(ox2, oy2, k2, 110 + 200 * 9 / 24, 196, 200 * 3 / 24, 5, C["warn"])
box(ox2, oy2, k2, 110 + 200 * 14 / 24, 196, 200 * 4 / 24, 5, C["warn"])
# 错误块
box(ox2, oy2, k2, 110, 208, 70, 12, C["error"])
d.text(P(ox2, oy2, k2, 114, 209), "ERR 02", font=f(FONT_BOLD, int(8 * k2)), fill=C["bg"])

# ---------------- 标签与箭头 ----------------
tag_left(58, 112, "强调色", "rust")
arrow((58 + 36, 124), P(ox, oy, k, 16, 12), head=6)

tag_left(58, 200, "背景", "bg")
arrow((58 + 36, 212), P(ox, oy, k, 64, 74), head=6)

tag_left(58, 320, "主文字", "cream")
arrow((58 + 36, 332), P(ox, oy, k, 28, 206), head=6)

tag_left(58, 410, "次要文字", "peach")
arrow((58 + 36, 422), P(ox, oy, k, 130, 228), head=6)

tag_right(1290, 130, "面板", "panel")
arrow((1288, 142), P(ox2, oy2, k2, 300, 62), head=6)

tag_right(1290, 250, "进度条底色", "track")
arrow((1288, 262), P(ox2, oy2, k2, 258, 158), head=6)

tag_right(1290, 430, "警示色", "warn")
arrow((1288, 442), P(ox2, oy2, k2, 205, 198), head=6)

tag_right(1290, 512, "错误色", "error")
arrow((1288, 524), P(ox2, oy2, k2, 165, 214), head=6)

# ---------------- 底部说明 ----------------
f_leg = f(FONT_REG, 15)
f_note = f(FONT_REG, 15)
d.text((40, 640), "强调色=标题/项目名/状态色   背景=整屏底色   主文字=正文文字+左下角状态条底   次要文字=百分比/计时", font=f_leg, fill="#8b9bb4")
d.text((40, 668), "面板=B 页终端窗与卡片底   进度条底色=上下文进度条未填充的那一截   警示色=峰时段与待确认   错误色=失败与报错", font=f_leg, fill="#8b9bb4")
d.text((40, 712), "描边不再单独配色：A 页底栏描边跟着当前状态色，B 页事件窗跟着状态色、上下文窗跟着占用率变色。", font=f_note, fill="#a8b6cc")
d.text((40, 740), "透明屏上「背景」设成纯黑就是不发光=全透明；想要有色底，调成深墨绿/深藏青这类低亮度颜色即可。", font=f_note, fill="#a8b6cc")

img.convert("RGB").save("build/dsh_fish/assets/ui/color-map.png")
print("saved", img.size)
