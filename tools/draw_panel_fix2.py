from PIL import Image, ImageDraw, ImageFont

BG = (11, 21, 18)
PANEL = (19, 36, 28)
LINE = (42, 64, 52)
RUST = (74, 222, 128)
CREAM = (242, 251, 246)
DIM = (126, 156, 140)
PEACH = (168, 194, 181)
WARN = (251, 191, 36)

S = 4
F14 = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 14 * S)
F12 = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 12 * S)
F10 = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 10 * S)
F9 = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 9 * S)
FLBL = ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc', 24)


def border(d, w, h):
    d.rectangle([0, 0, w * S - 1, h * S - 1], outline=LINE, width=S)


# A 页底栏 320x44
a = Image.new('RGB', (320 * S, 44 * S), BG)
da = ImageDraw.Draw(a)
border(da, 320, 44)
da.rectangle([1 * S, 1 * S, 103 * S - 1, 22 * S - 1], fill=CREAM)
da.text((6 * S, 2 * S), '待命', font=F14, fill=BG)
da.text((103 * S, 2 * S), '>', font=F14, fill=CREAM)
da.text((114 * S, 4 * S), 'HoloCubic', font=F12, fill=RUST)
da.text((262 * S, 5 * S), 'dsh', font=F10, fill=DIM)
da.rectangle([1 * S, 24 * S, 57 * S - 1, 43 * S - 1], fill=PEACH)
da.text((6 * S, 25 * S), '12m', font=F10, fill=BG)
da.text((62 * S, 25 * S), 'R2d', font=F10, fill=CREAM)

# B 页上下文面板 212x92
b = Image.new('RGB', (212 * S, 92 * S), BG)
db = ImageDraw.Draw(b)
border(db, 212, 92)
db.rectangle([0, 0, 39 * S - 1, 18 * S - 1], fill=RUST)
db.text((3 * S, 1 * S), '上下文', font=F10, fill=BG)
pct = '12.6%'
tw = db.textlength(pct, font=F10)
db.text((204 * S - tw, 2 * S), pct, font=F10, fill=PEACH)
db.rectangle([6 * S, 20 * S, 206 * S - 1, 26 * S - 1], fill=LINE)
db.rectangle([6 * S, 20 * S, 6 * S + int(200 * 0.126) * S, 26 * S - 1], fill=RUST)
rows = [('本轮 6.9M', 6, 32), ('总计 6.9M', 108, 32),
        ('未缓存 215K', 6, 46), ('输出 215K', 108, 46),
        ('缓存读 214M', 6, 60), ('命中 99.9%', 108, 60)]
for txt, x, y in rows:
    db.text((x * S, y * S), txt, font=F9, fill=DIM)
eta = '-> 13m'
tw2 = db.textlength(eta, font=F9)
db.text((206 * S - tw2, 71 * S), eta, font=F9, fill=PEACH)
db.rectangle([6 * S, 84 * S, 206 * S - 1, 88 * S - 1], fill=(59, 130, 246))
db.rectangle([75 * S, 84 * S, 100 * S - 1, 88 * S - 1], fill=WARN)
db.rectangle([116 * S, 84 * S, 150 * S - 1, 88 * S - 1], fill=WARN)
ax = 6 + int(200 * 0.582)
db.rectangle([ax * S, 79 * S, ax * S + 2 * S - 1, 85 * S - 1], fill=CREAM)

W = 320 * S + 40
H = 44 * S + 92 * S + 210
out = Image.new('RGB', (W, H), (10, 14, 20))
dr = ImageDraw.Draw(out)
dr.text((20, 14), 'A 页底栏：描边现在完整一圈（状态块/计时块都不再压住边框）', font=FLBL, fill=(232, 238, 247))
out.paste(a, (20, 52))
y2 = 52 + 44 * S + 46
dr.text((20, y2), 'B 页上下文面板：双色进度条 + 峰谷条右上角倒计时', font=FLBL, fill=(232, 238, 247))
out.paste(b, (20, y2 + 36))
y3 = y2 + 36 + 92 * S + 10
dr.text((20, y3), '进度条底色=总窗口，绿色=已用（12.6%）；倒计时=距下一次峰谷切换 13m', font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 20), fill=(139, 155, 180))
out.save('docs/img/panel-fix2.png')
print(out.size)
