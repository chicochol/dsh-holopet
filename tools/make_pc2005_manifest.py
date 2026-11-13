"""生成 pc2005 皮肤的 manifest.lua（事件映射 / 标签 / 转向与移动动画池）。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "build" / "_work" / "pc2005"
MAP_FILE = WORK / "name-map.json"
OUT = ROOT / "build" / "skins" / "pc2005" / "manifest.lua"

# 拼音 -> 事件，依据 PC2005 官方 config.jsonc 的 workStatus 六档与 baifan 玩法
EVENTS = {
    "Idle": ["daiji-huxi-xiuxian", "dongzhangxiwang", "youxian-hengga", "zhao-jingzi"],
    "UserPromptSubmit": ["dianji-huiying-yuanqi-huishou", "chaoda-shenlanyao"],
    "PreToolUse": ["gongzuozhuangtai-manglu-dianan", "xie-daima", "qingkuai-jilu"],
    "PostToolUse": ["gongzuozhuangtai-qingdian-guidang", "qingkuai-jilu"],
    "PermissionRequest": ["gongzuozhuangtai-yuandi-duobu-zhangwang", "qidai-kaifan"],
    "SubagentStart": ["sanqiu-paojie", "bian-gezi"],
    "SubagentStop": ["chai-liwu", "shou-hongbao"],
    "PreCompact": ["gongzuozhuangtai-sikao-maopao", "shendu-sikao-suisuinian"],
    "PostCompact": ["gongzuozhuangtai-qingdian-guidang"],
    "Error": ["gongzuozhuangtai-chuitou-tanqi-maohan", "wan-youxi-qijibaituai"],
    "Stop": ["gongzuozhuangtai-queyue-qingzhu", "fang-yanhua", "dianji-huiying-kaixin-yuedong"],
    "SessionStart": ["chaoda-shenlanyao", "chenjian-shuaya"],
    "Sleeping": ["shuijiao-xunhuan"],
}

# 移动动画池（官方 moves + baifan 里的两个跑动），lead/tail 单位为秒
# 第一个是默认走动动画。facing 指原图人物面朝哪边（像素质心实测）。
MOVES = [
    {"file": "ceshen-jizao-pao", "lead": 0.6, "tail": 0.6, "facing": "left"},
    {"file": "pangxie-zoulu", "lead": 2.0, "tail": 2.0, "facing": "right"},
    {"file": "yuandi-piaofu-tabu", "lead": 2.0, "tail": 2.0, "facing": "right"},
    {"file": "yuandi-zuozhuan-benpao", "lead": 1.75, "tail": 4.8, "facing": "right"},
    {"file": "kaixin-xiaopao", "lead": 2.0, "tail": 2.0, "facing": "right"},
]
TURN = ["dongzhangxiwang"]


def q(s):
    return '"' + s + '"'


def main():
    mp = json.loads(MAP_FILE.read_text(encoding="utf-8"))  # 中文 -> 拼音
    have = {p.stem for p in (ROOT / "build" / "skins" / "pc2005" / "normal").glob("*.gif")}
    lines = ["return {",
             '  id = "pc2005",',
             '  name = "蓝毛小女仆",',
             '  name_en = "Blue Maid",',
             "  speeds = { slow = 150, normal = 120, fast = 90 },",
             '  default_speed = "normal",',
             "  events = {"]
    for ev, files in EVENTS.items():
        got = [f for f in files if f in have]
        if not got:
            continue
        lines.append(f"    [{q(ev)}] = {{ " + ", ".join(q(f + ".gif") for f in got) + " },")
    lines.append("  },")
    lines.append("  weather = {},")
    lines.append("  moves = {")
    for m in MOVES:
        if m["file"] not in have:
            continue
        lines.append(
            f'    {{ file = {q(m["file"] + ".gif")}, lead = {m["lead"]}, tail = {m["tail"]}, '
            f'facing = {q(m["facing"])} }},')
    lines.append("  },")
    lines.append("  turn = { " + ", ".join(q(f + ".gif") for f in TURN if f in have) + " },")
    lines.append("  labels = {")
    for zh, py in mp.items():
        if py in have:
            lines.append(f"    [{q(py + '.gif')}] = {q(zh)},")
    lines.append("  },")
    lines.append("}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("wrote", OUT, f"{len(have)} gifs available")
    for ev, files in EVENTS.items():
        got = [f for f in files if f in have]
        miss = [f for f in files if f not in have]
        if miss:
            print(f"  {ev}: 缺 {miss}")


if __name__ == "__main__":
    main()
