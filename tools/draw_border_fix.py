from PIL import Image, ImageDraw, ImageFont

BG = (11, 21, 18)
LINE = (42, 64, 52)
CREAM = (242, 251, 246)
RUST = (74, 222, 128)
DIM = (126, 156, 140)

S = 5
PW, PH = 320, 44
F14 = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 14 * S)
F12 = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 12 * S)
F10 = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 10 * S)
FLBL = ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc', 22)


def bar(old):
    img = Image.new('RGB', (PW * S, PH * S), BG)
    d = ImageDraw.Draw(img)
    # panel 边框
    d.rectangle([0, 0, PW * S - 1, PH * S - 1], outline=LINE, width=S)
    # 状态块
    if old:
        x0, y0, w, h = 0, 0, 102, 21
    else:
        x0, y0, w, h = 1, 1, 100, 19
    d.rectangle([x0 * S, y0 * S, (x0 + w) * S - 1, (y0 + h) * S - 1], fill=CREAM)
    d.text(((x0 + 6) * S, (y0 + 1) * S), '待命', font=F14, fill=BG)
    d.text((103 * S, 1 * S), '>', font=F14, fill=CREAM)
    d.text((114 * S, 3 * S), 'HoloCubic', font=F12, fill=RUST)
    d.text((262 * S, 4 * S), 'dsh', font=F10, fill=DIM)
    d.text((6 * S, 24 * S), '本轮 12m', font=F10, fill=CREAM)
    return img


a = bar(True)
b = bar(False)
W = PW * S
H = a.height * 2 + 130
out = Image.new('RGB', (W + 40, H), (10, 14, 20))
dr = ImageDraw.Draw(out)
dr.text((20, 14), '改前：状态块贴着 0,0，盖掉了左边框和顶边框的左半段', font=FLBL, fill=(232, 238, 247))
out.paste(a, (20, 50))
# 标出断口
dr.rectangle([20, 50, 20 + 102 * S, 50 + 3 * S], outline=(248, 113, 113), width=2)
dr.text((20, 50 + a.height + 4), '↑ 红框处：边框被实心块盖住，看起来断了一截', font=FLBL, fill=(248, 113, 113))

y2 = 50 + a.height + 44
dr.text((20, y2), '改后：状态块内缩 1px，描边完整一圈不断', font=FLBL, fill=(232, 238, 247))
out.paste(b, (20, y2 + 36))
dr.text((20, y2 + 36 + b.height + 6), '↑ 四条边现在都能连上', font=FLBL, fill=(74, 222, 128))
out.save('docs/img/panel-border-fix.png')
print(out.size)
