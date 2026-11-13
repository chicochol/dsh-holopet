"""把两个皮肤的 manifest 改成「一个事件挂多个动作变体」，并补上动作中文名。

素材本身没变（16 个 GIF 就是 16 个源动作），这里只是允许同一个 GIF
被多个事件复用，从而让每个事件都有 2~4 个候选变体。
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIN_DIR = ROOT / "build" / "dsh_fish" / "assets" / "skins"

# chibi-blue：同一动作可服务多个事件，第一个是默认（保持原来的映射不变）
CHIBI_MAP = {
    "Idle": ["idle_01.gif", "idle_02.gif", "idle_03.gif", "idle_04.gif"],
    "UserPromptSubmit": ["userpromptsubmit.gif", "sessionstart.gif", "stop.gif"],
    "PreToolUse": ["pretooluse.gif", "posttooluse.gif"],
    "PostToolUse": ["posttooluse.gif", "postcompact.gif"],
    "PermissionRequest": ["permissionrequest.gif", "userpromptsubmit.gif"],
    "SubagentStart": ["subagentstart.gif", "pretooluse.gif"],
    "SubagentStop": ["subagentstop.gif", "stop.gif"],
    "PreCompact": ["precompact.gif", "postcompact.gif"],
    "PostCompact": ["postcompact.gif", "stop.gif"],
    "Error": ["error.gif"],
    "Stop": ["stop.gif", "subagentstop.gif"],
    "SessionStart": ["sessionstart.gif", "userpromptsubmit.gif"],
    "Sleeping": ["sleeping.gif"],
}

LABELS = {
    "idle_01.gif": "待机呼吸",
    "idle_02.gif": "东张西望",
    "idle_03.gif": "悠闲哼歌",
    "idle_04.gif": "照镜子",
    "userpromptsubmit.gif": "元气挥手",
    "pretooluse.gif": "敲代码",
    "posttooluse.gif": "轻快记录",
    "permissionrequest.gif": "期待开饭",
    "error.gif": "垂头叹气",
    "stop.gif": "雀跃庆祝",
    "sessionstart.gif": "伸懒腰",
    "subagentstart.gif": "抛接三球",
    "subagentstop.gif": "拆礼物",
    "precompact.gif": "碎碎念",
    "postcompact.gif": "清点归档",
    "sleeping.gif": "睡觉",
}

WHALE_LABELS = {f"idle_0{i}.gif": f"待机 {i}" for i in range(1, 5)}


def parse_old(path):
    """读旧 manifest，拿到 speeds / events / weather / name 等字段。"""
    txt = path.read_text(encoding="utf-8")
    out = {"events": {}, "speeds": {}, "name": "", "name_en": "", "id": ""}
    m = re.search(r'id\s*=\s*"([^"]+)"', txt)
    if m:
        out["id"] = m.group(1)
    m = re.search(r'name\s*=\s*"([^"]+)"', txt)
    if m:
        out["name"] = m.group(1)
    m = re.search(r'name_en\s*=\s*"([^"]+)"', txt)
    if m:
        out["name_en"] = m.group(1)
    m = re.search(r"speeds\s*=\s*\{([^}]*)\}", txt)
    if m:
        for k, v in re.findall(r"(\w+)\s*=\s*(\d+)", m.group(1)):
            out["speeds"][k] = int(v)
    for name, body in re.findall(r'\[\s*"([A-Za-z]+)"\s*\]\s*=\s*\{([^}]*)\}', txt):
        files = re.findall(r'"([^"]+\.gif)"', body)
        if files:
            out["events"][name] = files
    return out


def emit(skin, old, events, labels):
    speeds = old["speeds"] or {"slow": 150, "normal": 120, "fast": 90}
    lines = [
        "-- 皮肤包清单（由 tools/make_manifests.py 生成）",
        "-- events: 事件名 -> 候选动作文件列表，第一个为默认；同一文件可被多个事件复用",
        "-- labels: 文件 -> 中文动作名，管理页展示用",
        "return {",
        f'  id = "{skin}",',
        f'  name = "{old["name"] or skin}",',
        f'  name_en = "{old["name_en"] or skin}",',
        "  speeds = { " + ", ".join(f"{k} = {v}" for k, v in speeds.items()) + " },",
        '  default_speed = "normal",',
        "  labels = {",
    ]
    for fn in sorted(labels):
        lines.append(f'    ["{fn}"] = "{labels[fn]}",')
    lines.append("  },")
    lines.append("  events = {")
    for name in [
        "Idle", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PermissionRequest",
        "SubagentStart", "SubagentStop", "PreCompact", "PostCompact", "Error",
        "Stop", "SessionStart", "Sleeping",
    ]:
        files = events.get(name) or old["events"].get(name) or []
        lines.append(f'    ["{name}"] = {{ ' + ", ".join(f'"{f}"' for f in files) + " },")
    lines.append("  },")
    lines.append("  weather = {},")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main():
    for skin, mapping in (("chibi-blue", CHIBI_MAP), ("whale", None)):
        d = SKIN_DIR / skin
        old = parse_old(d / "manifest.lua")
        if mapping:
            events = mapping
            labels = LABELS
        else:
            # whale 保持原映射，只补 Idle 的中文名
            events = old["events"]
            labels = {}
            for fn in events.get("Idle", []):
                labels[fn] = WHALE_LABELS.get(fn, fn.replace(".gif", ""))
            for name, files in events.items():
                for fn in files:
                    labels.setdefault(fn, name)
        text = emit(skin, old, events, labels)
        (d / "manifest.lua").write_text(text, encoding="utf-8", newline="\n")
        flat = sum(len(v) for v in events.values())
        print(f"{skin}: {len(events)} 事件 / {flat} 条映射 / {len(labels)} 个动作名")


if __name__ == "__main__":
    main()
