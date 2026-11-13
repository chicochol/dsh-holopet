"""生成两套皮肤「事件 → 动作 → 变体」对照表。

事件与动作的对应关系不是素材自带的：鲸鱼娘的精灵表只有行列坐标，
蓝发少女的源文件只有动作序号，两边都没有语义标签。这张表把当前的
对应关系和我们选择它的依据一起列出来，方便对着看是否要换。
"""

import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SKIN_DIR = ROOT / "build" / "dsh_fish" / "assets" / "skins"
OUT = ROOT / "docs" / "img" / "action-map.png"

EVENTS = [
    ("Idle", "待命"),
    ("UserPromptSubmit", "接收指令"),
    ("PreToolUse", "执行工具"),
    ("PostToolUse", "检查结果"),
    ("PermissionRequest", "等待确认"),
    ("SubagentStart", "分派子任务"),
    ("SubagentStop", "合并子任务"),
    ("PreCompact", "压缩前"),
    ("PostCompact", "压缩后"),
    ("Error", "出错"),
    ("Stop", "本轮完成"),
    ("SessionStart", "会话开始"),
    ("Sleeping", "休眠"),
]

# 为什么这么配（人工按动作的视觉内容判断）
WHY = {
    "whale": "精灵表坐标：行=动作族，列=帧",
    "chibi-blue": "源视频动作序号：按画面内容归类",
}

REASON = {
    ("whale", "Idle"): "站立轻微晃动，4 个变体轮换",
    ("whale", "UserPromptSubmit"): "抬头聆听",
    ("whale", "PreToolUse"): "侧身走动",
    ("whale", "PostToolUse"): "转身查看",
    ("whale", "PermissionRequest"): "正面摊手等待",
    ("whale", "SubagentStart"): "抬手示意",
    ("whale", "SubagentStop"): "转身收势",
    ("whale", "PreCompact"): "低头整理",
    ("whale", "PostCompact"): "正面站定",
    ("whale", "Error"): "低头难过",
    ("whale", "Stop"): "转身完成",
    ("whale", "SessionStart"): "抬手打招呼",
    ("whale", "Sleeping"): "闭眼睡觉",
    ("chibi-blue", "Idle"): "站立呼吸，4 变体轮换",
    ("chibi-blue", "UserPromptSubmit"): "抬头听",
    ("chibi-blue", "PreToolUse"): "敲键盘",
    ("chibi-blue", "PostToolUse"): "捧杯子查看",
    ("chibi-blue", "PermissionRequest"): "抱礼物期待",
    ("chibi-blue", "SubagentStart"): "抛三个球",
    ("chibi-blue", "SubagentStop"): "拆礼物",
    ("chibi-blue", "PreCompact"): "低头碎碎念",
    ("chibi-blue", "PostCompact"): "举手欢呼",
    ("chibi-blue", "Error"): "低头哭",
    ("chibi-blue", "Stop"): "比心",
    ("chibi-blue", "SessionStart"): "唱歌",
    ("chibi-blue", "Sleeping"): "趴着睡",
}


def parse_manifest(path):
    txt = path.read_text(encoding="utf-8")
    out = {}
    for name, body in re.findall(r'\[\s*"([A-Za-z]+)"\s*\]\s*=\s*\{([^}]*)\}', txt):
        files = re.findall(r'"([^"]+\.gif)"', body)
        if files:
            out[name] = files
    return out


def font(size, bold=False):
    for p in (r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
              r"C:\Windows\Fonts\msyh.ttc"):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def first_frame(path, size):
    im = Image.open(path)
    im.seek(0)
    f = im.convert("RGBA")
    f.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(f, ((size - f.width) // 2, (size - f.height) // 2), f)
    return canvas


def main():
    skins = ["whale", "chibi-blue"]
    data = {s: parse_manifest(SKIN_DIR / s / "manifest.lua") for s in skins}
    name_cn = {"whale": "鲸鱼娘 whale", "chibi-blue": "蓝发少女 chibi-blue"}

    W = 1500
    row_h = 96
    head_h = 150
    H = head_h + row_h * len(EVENTS) + 90
    img = Image.new("RGB", (W, H), "#0E1512")
    d = ImageDraw.Draw(img)

    f_title = font(34, True)
    f_sub = font(16)
    f_col = font(20, True)
    f_ev = font(17, True)
    f_file = font(13)
    f_reason = font(14)

    d.text((28, 22), "两套皮肤 · 事件 → 动作 → 变体 对照表", font=f_title, fill="#F2FBF6")
    d.text((28, 78), "事件与动作的对应不是素材自带的：鲸鱼娘精灵表只有行列坐标，蓝发少女只有动作序号，"
                     "下面的归类是人工按画面内容判断的，可对着改。", font=f_sub, fill="#8FA89B")

    col_x = [320, 890]
    gw = 120
    for ci, s in enumerate(skins):
        x = col_x[ci]
        d.text((x, 108), name_cn[s], font=f_col, fill="#4ADE80" if ci == 0 else "#60A5FA")
        d.text((x, 134), WHY[s], font=f_sub, fill="#6E8478")

    y = head_h
    for ev, cn in EVENTS:
        d.text((26, y + 22), cn, font=f_ev, fill="#F2FBF6")
        d.text((26, y + 46), ev, font=f_file, fill="#6E8478")
        for ci, s in enumerate(skins):
            x = col_x[ci]
            files = data[s].get(ev, [])
            for fi, fn in enumerate(files[:4]):
                fr = first_frame(SKIN_DIR / s / "normal" / fn, 76)
                box = (x + fi * 84, y + 6)
                d.rectangle((box[0], box[1], box[0] + 76, box[1] + 76), fill="#111B16", outline="#2A4034")
                img.paste(fr, (box[0], box[1]), fr)
                d.text((box[0], box[1] + 78), fn.replace(".gif", ""), font=f_file, fill="#8FA89B")
            label = REASON.get((s, ev), "")
            if label:
                d.text((x + 4 * 84 - 24, y + 30), label, font=f_reason, fill="#C8D8CE" if ci == 0 else "#B8CDE8")
        d.line((20, y + row_h - 4, W - 20, y + row_h - 4), fill="#1D2B24")
        y += row_h

    d.text((28, H - 62), "变体说明：Idle 有 4 个变体（设备自动轮换），其余事件目前各 1 个。"
                         "要支持「一组多动作、逐个开关、逐个配置是否可走动」，需要先扩充素材再改配置结构。",
           font=f_sub, fill="#8FA89B")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT)
    print("ok", OUT, img.size)


if __name__ == "__main__":
    main()
