"""把 PC2005-cloud/dsh-pet 的全量动画转成设备用的 160x160 索引 GIF。

- 中文动作名 → README 里对应的拼音文件名（跨平台安全）
- 只转 normal 档（120ms），慢/快两档需要时再补
- 输出 build/skins/pc2005/normal/<pinyin>.gif
"""
import io
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "build" / "_work" / "pc2005"
OUT = ROOT / "build" / "skins" / "pc2005" / "normal"
WORK.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

RAW = "https://raw.githubusercontent.com/PC2005-cloud/dsh-pet/main/dsh-pet/assets/webm/"
README_URL = "https://raw.githubusercontent.com/PC2005-cloud/dsh-pet/main/README.md"

SIZE = 160
COLORS = 30
FRAMES = 10
DURATION = 120
BOX = (170, 25, 470, 325)   # 统一裁切框（360x360 等比缩到 160x160）


def fetch(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": "dsh-fish"})
    data = urllib.request.urlopen(req, timeout=180).read()
    return data if binary else data.decode("utf-8", "replace")


def name_map():
    """从 README 里解析 中文动作名 -> 拼音文件名。"""
    txt = fetch(README_URL)
    pairs = re.findall(r'src="dsh-pet/assets/preview/([a-z0-9\-]+)\.gif"[^>]*alt="([^"]+)"', txt)
    mp = {zh.strip(): py for py, zh in pairs}
    print(f"README 映射 {len(mp)} 条")
    return mp


def webm_list():
    """仓库里全部 webm 的中文名（用 GitHub API 一次拿到；限流则退回 README 的名单）。"""
    try:
        tree = json.loads(fetch(
            "https://api.github.com/repos/PC2005-cloud/dsh-pet/git/trees/main?recursive=1"))
        names = [t["path"].rsplit("/", 1)[1][:-5] for t in tree["tree"]
                 if t["path"].lower().endswith(".webm")]
        print(f"API 列出 {len(names)} 个 webm")
        return sorted(names)
    except Exception as e:
        print("API 不可用，退回 README 名单:", e)
        return sorted(name_map().keys())


def probe(src):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", str(src)],
        capture_output=True, text=True, check=True).stdout
    st = json.loads(out)["streams"][0]
    return int(st["width"]), int(st["height"])


def decode(src, w, h):
    out = WORK / (src.stem + f".{w}x{h}.rgba")
    if not out.exists() or out.stat().st_size < 1000:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-c:v", "libvpx-vp9",
                        "-i", str(src), "-pix_fmt", "rgba", "-f", "rawvideo", str(out)], check=True)
    raw = np.fromfile(str(out), dtype=np.uint8)
    per = w * h * 4
    n = raw.size // per
    return raw[: n * per].reshape(n, h, w, 4)


def union_bbox(frames):
    box = None
    for f in frames:
        a = np.array(f.getchannel("A"))
        ys, xs = np.nonzero(a > 32)
        if len(xs) == 0:
            continue
        b = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]),
                                     max(box[2], b[2]), max(box[3], b[3]))
    return box


def encode(frames):
    n = len(frames)
    idx = np.linspace(0, n - 1, min(FRAMES, n)).round().astype(int)
    picked = [frames[i] for i in idx]
    # 统一用同一个裁切框，所有动作的角色相对大小才一致、也不会被拉变形。
    # 640x360 源画布，角色本体约在 x 196..448 / y 58..335。
    picked = [f.crop(BOX).resize((SIZE, SIZE), Image.LANCZOS) for f in picked]

    pf = []
    for f in picked:
        q = f.convert("RGB").quantize(colors=COLORS - 1, method=Image.MEDIANCUT).convert("P")
        pal = q.getpalette()[: (COLORS - 1) * 3]
        q.putpalette([0, 0, 0] + pal + [0, 0, 0] * max(0, COLORS - 1 - len(pal) // 3))
        q = q.point(lambda v: min(COLORS - 1, v + 1))
        # 半透明边缘直接切掉，避免白边
        q.paste(0, mask=f.getchannel("A").point(lambda v: 255 if v < 128 else 0))
        pf.append(q)
    buf = io.BytesIO()
    pf[0].save(buf, format="GIF", save_all=True, append_images=pf[1:], duration=DURATION,
               loop=0, disposal=2, transparency=0, optimize=False)
    return buf.getvalue()


def main():
    mp = name_map()
    names = webm_list()
    todo = [n for n in names if n in mp]
    missing = [n for n in names if n not in mp]
    print(f"可转换 {len(todo)}，缺拼音映射 {len(missing)}: {missing[:8]}")

    done = 0
    total = 0
    failed = []
    for i, zh in enumerate(todo, 1):
        py = mp[zh]
        dst = OUT / (py + ".gif")
        if dst.exists() and dst.stat().st_size > 2000:
            done += 1
            total += dst.stat().st_size
            continue
        try:
            src = WORK / (zh + ".webm")
            if not src.exists() or src.stat().st_size < 10000:
                src.write_bytes(fetch(RAW + urllib.parse.quote(zh + ".webm"), binary=True))
            w, h = probe(src)
            frames = decode(src, w, h)
            data = encode([Image.fromarray(a, "RGBA") for a in frames])
            dst.write_bytes(data)
            done += 1
            total += len(data)
            print(f"[{i}/{len(todo)}] {zh} -> {py}.gif  {len(data)/1024:.0f}KB")
        except Exception as e:
            failed.append((zh, f"{type(e).__name__}: {e}"))
            print(f"[{i}/{len(todo)}] {zh} FAIL {e}")

    print(f"\n完成 {done}/{len(todo)}，总 {total/1048576:.2f} MB，失败 {len(failed)}")
    if failed:
        for zh, err in failed[:10]:
            print("  ", zh, err)
    (WORK / "name-map.json").write_text(json.dumps(mp, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()

