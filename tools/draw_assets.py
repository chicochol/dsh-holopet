# -*- coding: utf-8 -*-
"""把四条素材路线的代表帧排在一起，看美术风格。

所有帧都先 alpha 合成到屏幕底色上再缩放，避免 GIF 透明边缘发黑；
再按实际内容裁掉空白，让不同尺寸的角色在同一张图里大小可比。
"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, "..", "assets", "refs")
OUT = os.path.join(HERE, "..", "docs", "img", "asset-routes.png")

W, H = 1840, 1660
BG = "#F4F7FA"
INK = "#16202B"
MUTED = "#6B7A8C"
SCREEN = "#0E1B16"          # 真实屏幕底色
GREEN = "#4ADE80"

FONT_R = "C:/Windows/Fonts/msyh.ttc"
FONT_B = "C:/Windows/Fonts/msyhbd.ttc"


def F(size, bold=False):
    return ImageFont.truetype(FONT_B if bold else FONT_R, size)


def text(d, xy, s, size, color=INK, bold=False):
    d.text(xy, s, font=F(size, bold), fill=color)


def compose(im, bg):
    base = Image.new("RGBA", im.size, bg)
    base.alpha_composite(im.convert("RGBA"))
    return base.convert("RGB")


def fit_box(im, box_w, box_h):
    w, h = im.size
    k = min(box_w / w, box_h / h)
    return im.resize((max(1, int(w * k)), max(1, int(h * k))), Image.LANCZOS)


def trim(im):
    """裁掉四周全透明区域，保留一点边距。"""
    b = im.convert("RGBA").getbbox()
    if not b:
        return im
    pad = 2
    return im.crop((max(0, b[0] - pad), max(0, b[1] - pad),
                    min(im.size[0], b[2] + pad), min(im.size[1], b[3] + pad)))


def gif_frame(path, which=0.35):
    im = Image.open(path)
    n = getattr(im, "n_frames", 1)
    im.seek(min(n - 1, int(n * which)))
    return trim(im.convert("RGBA"))


def sprite_frames(path, idxs, cw=192, ch=208, cols=8):
    sheet = Image.open(path).convert("RGBA")
    out = []
    for i in idxs:
        r, c = divmod(i, cols)
        out.append(trim(sheet.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch))))
    return out


img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

text(d, (60, 44), "宠物素材 · 四条路线美术风格对比", 42, INK, True)
text(d, (60, 104), "四套素材均已实测四角透明，不存在“带底图”问题；此处统一以真实屏幕色 #0E1B16 为底渲染，并按内容裁切以统一角色大小",
     19, MUTED)

rows = [
    ("A", "holopet 的 clawdmoji",
     "你设备上现成的 · 160×160", "每状态 4 变体 · 单文件 3–21KB",
     [("gif", os.path.join(REF, "holopet-idle_01.gif")),
      ("gif", os.path.join(REF, "holopet-idle_05.gif")),
      ("gif", os.path.join(REF, "holopet-pretooluse_01.gif")),
      ("gif", os.path.join(REF, "holopet-pretooluse_02.gif")),
      ("gif", os.path.join(REF, "holopet-stop_01.gif")),
      ("gif", os.path.join(REF, "holopet-error_01.gif"))]),
    ("B", "鲸鱼娘",
     "linxin666/dsh-pet · BSD-3 · 60 帧", "精灵表 1.5MB · 有逐帧时长",
     [("sprite", os.path.join(REF, "whale-sprite.webp"), [0, 1, 2, 3, 8, 9])]),
    ("C", "蓝发少女",
     "PC2005-cloud/dsh-pet · 5942★", "220×124 · 120 帧/动作 · 109 个动作",
     [("gif", os.path.join(REF, "pc2005-chitoken.gif")),
      ("gif", os.path.join(REF, "pc2005-beixiayitiao-zhamao.gif")),
      ("gif", os.path.join(REF, "pc2005-chai-liwu.gif")),
      ("gif", os.path.join(REF, "pc2005-chenjian-shuaya.gif")),
      ("gif", os.path.join(REF, "pc2005-bian-gezi.gif")),
      ("gif", os.path.join(REF, "pc2005-chi-bingqilin-ronghua.gif"))]),
    ("D", "像素白龙",
     "mjw-git/dsh-pet · 74 帧 · 无版权声明", "192×208 · 精灵表 3.2MB",
     [("sprite", os.path.join(REF, "mjw-sprite.webp"), [0, 1, 2, 3, 8, 9])]),
]

y = 160
BOX = 196
GAP = 22
X0 = 470

for tag, name, meta1, meta2, items in rows:
    d.rounded_rectangle((60, y - 26, W - 60, y + 300), 16, fill="#FFFFFF", outline="#E2E9F0", width=1)
    d.rounded_rectangle((84, y - 6, 130, y + 42), 10, fill=GREEN)
    text(d, (95, y + 1), tag, 26, "#0B2418", True)
    text(d, (144, y - 10), name, 21, INK, True)
    text(d, (144, y + 26), meta1, 14, MUTED)
    text(d, (144, y + 50), meta2, 14, MUTED)

    frames = []
    for it in items:
        if it[0] == "gif":
            frames.append(gif_frame(it[1]))
        else:
            frames.extend(sprite_frames(it[1], it[2]))

    x = X0
    for fr in frames:
        d.rounded_rectangle((x, y, x + BOX, y + BOX + 24), 14, fill=SCREEN)
        pic = compose(fr, SCREEN)
        pic = fit_box(pic, BOX - 18, BOX - 18)
        img.paste(pic, (x + (BOX - pic.size[0]) // 2, y + (BOX + 24 - pic.size[1]) // 2))
        x += BOX + GAP

    y += 330

d.rounded_rectangle((60, y - 10, W - 60, y + 104), 14, fill="#EAF7EE", outline="#BFE5CD", width=1)
text(d, (88, y + 10), "结论", 20, "#14603A", True)
text(d, (152, y + 8),
     "四套都是真透明背景（四角 alpha=0），不存在“带底图”问题，全息屏上会直接浮在底上。", 17, "#1F4A38")
text(d, (152, y + 44),
     "A 最贴合 320×240、最省内存但画风偏简陋；B 最精致；C 动作最多但要抽帧降采样；D 像素龙质感好。",
     17, "#1F4A38")

img.save(OUT)
print("ok", OUT, img.size)
