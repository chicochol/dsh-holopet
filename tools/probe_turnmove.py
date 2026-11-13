"""下载 PC2005 的 turn/move 关键动作，抽帧拼图，用于确认朝向与动作段落。"""
import io
import json
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "build" / "_work" / "pc2005"
WORK.mkdir(parents=True, exist_ok=True)

RAW = "https://raw.githubusercontent.com/PC2005-cloud/dsh-pet/main/dsh-pet/assets/webm/"
NAMES = ["东张西望", "螃蟹走路", "原地左转奔跑", "开心小跑", "侧身急躁跑"]
NOTE = {
    "东张西望": "turn（官方指定转向）",
    "螃蟹走路": "move 默认 60-240px",
    "原地左转奔跑": "move 120-320px lead1.75 tail4.8",
    "开心小跑": "baifan 跑向底部",
    "侧身急躁跑": "baifan 追饭侧身跑",
}
COLS = 12
THUMB = 128
FONT = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 16)
SMALL = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 12)


def download(name):
    dst = WORK / (name + ".webm")
    if dst.exists() and dst.stat().st_size > 10000:
        return dst
    req = urllib.request.Request(RAW + urllib.parse.quote(name + ".webm"), headers={"User-Agent": "dsh-fish"})
    dst.write_bytes(urllib.request.urlopen(req, timeout=180).read())
    return dst


def probe(src):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,nb_frames,r_frame_rate,duration",
         "-of", "json", str(src)],
        capture_output=True, text=True, check=True).stdout
    st = json.loads(out)["streams"][0]
    w, h = int(st["width"]), int(st["height"])
    fps = st.get("r_frame_rate", "30/1")
    num, den = fps.split("/")
    fps = float(num) / float(den) if float(den) else 30.0
    n = int(st["nb_frames"]) if st.get("nb_frames") not in (None, "N/A") else 0
    dur = float(st.get("duration") or 0) or (n / fps if n else 0)
    return w, h, n, fps, dur


def decode(src, w, h):
    out = WORK / (src.stem + f".{w}x{h}.rgba")
    if not out.exists() or out.stat().st_size < 1000:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-c:v", "libvpx-vp9",
                        "-i", str(src), "-pix_fmt", "rgba", "-f", "rawvideo", str(out)], check=True)
    raw = np.fromfile(str(out), dtype=np.uint8)
    per = w * h * 4
    n = raw.size // per
    return raw[: n * per].reshape(n, h, w, 4)


def centering(frames):
    """每帧角色 alpha 质心 x 相对画布中心的偏移，用来看身体是否在左右移动。"""
    vals = []
    for a in frames:
        al = a[..., 3].astype(float)
        ys, xs = np.nonzero(al > 24)
        if len(xs) == 0:
            vals.append(0.0)
            continue
        vals.append((xs * al[ys, xs]).sum() / al[ys, xs].sum() - a.shape[1] / 2.0)
    return vals


def main():
    rows = []
    for name in NAMES:
        src = download(name)
        w, h, n, fps, dur = probe(src)
        frames = decode(src, w, h)
        n = min(n or len(frames), len(frames))
        idx = np.linspace(0, n - 1, COLS).round().astype(int)
        cent = centering(frames[idx])
        rows.append((name, w, h, n, fps, dur, frames, idx, cent))
        print(f"{name}: {w}x{h} {n}帧 {fps:.1f}fps {dur:.2f}s  质心x偏移 {min(cent):.1f}..{max(cent):.1f}")

    W = 20 + COLS * (THUMB + 8)
    H = 20 + len(rows) * (THUMB + 46)
    img = Image.new("RGB", (W, H), (11, 15, 22))
    d = ImageDraw.Draw(img)
    for r, (name, w, h, n, fps, dur, frames, idx, cent) in enumerate(rows):
        d.text((20, 20 + r * (THUMB + 46)), f"{name}   {dur:.1f}s / {n}帧   {NOTE[name]}", fill=(230, 238, 247), font=FONT)
        for c, fi in enumerate(idx):
            a = frames[fi]
            fr = Image.fromarray(a, "RGBA")
            bb = fr.getchannel("A").point(lambda v: 255 if v > 16 else 0).getbbox()
            if bb:
                fr = fr.crop(bb)
            fr.thumbnail((THUMB, THUMB), Image.LANCZOS)
            x = 20 + c * (THUMB + 8)
            y = 20 + r * (THUMB + 46) + 26
            img.paste(fr, (x + (THUMB - fr.width) // 2, y + (THUMB - fr.height) // 2), fr)
            d.text((x + 2, y + THUMB - 2), f"{fi}", fill=(120, 140, 170), font=SMALL)
    out = ROOT / "docs" / "img" / "pc2005-turnmove.png"
    img.save(out)
    print("saved", out, img.size)


if __name__ == "__main__":
    main()
