"""下载 PC2005-cloud/dsh-pet 的 webm 抽样并转成设备用的 160x160 索引 GIF，估算全量体积。"""
import io
import json
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "build" / "_work" / "pc2005"
WORK.mkdir(parents=True, exist_ok=True)

SAMPLE = ["三球抛接.webm", "东张西望.webm", "优雅女仆舞.webm", "下五子棋.webm",
          "中秋赏月吃月饼.webm", "余额-分文不剩.webm"]
RAW = "https://raw.githubusercontent.com/PC2005-cloud/dsh-pet/main/dsh-pet/assets/webm/"
SIZE = 160
COLORS = 30


def download(name):
    dst = WORK / name
    if dst.exists() and dst.stat().st_size > 10000:
        return dst
    req = urllib.request.Request(RAW + urllib.parse.quote(name), headers={"User-Agent": "dsh-fish"})
    dst.write_bytes(urllib.request.urlopen(req, timeout=180).read())
    return dst


def probe(src):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,nb_frames,r_frame_rate",
         "-of", "json", str(src)],
        capture_output=True, text=True, check=True,
    ).stdout
    st = json.loads(out)["streams"][0]
    w, h = int(st["width"]), int(st["height"])
    n = st.get("nb_frames")
    if not n or n == "N/A":
        num, den = st["r_frame_rate"].split("/")
        dur = float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)],
            capture_output=True, text=True, check=True).stdout.strip())
        n = int(float(num) / float(den) * dur)
    return w, h, int(n)


def decode(src, w, h, n):
    out = WORK / (src.stem + f".{w}x{h}.rgba")
    if not out.exists() or out.stat().st_size < 1000:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-c:v", "libvpx-vp9", "-i", str(src),
             "-pix_fmt", "rgba", "-f", "rawvideo", str(out)],
            check=True,
        )
    raw = np.fromfile(str(out), dtype=np.uint8)
    per = w * h * 4
    n = min(n, raw.size // per)
    return raw[: n * per].reshape(n, h, w, 4), n


def union_bbox(frames):
    box = None
    for f in frames:
        a = np.array(f.getchannel("A"))
        ys, xs = np.nonzero(a > 16)
        if len(xs) == 0:
            continue
        b = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]),
                                     max(box[2], b[2]), max(box[3], b[3]))
    return box


def encode(frames, n_frames, duration=110):
    idx = np.linspace(0, len(frames) - 1, min(n_frames, len(frames))).round().astype(int)
    picked = [frames[i] for i in idx]
    box = union_bbox(picked)
    if box:
        picked = [f.crop(box) for f in picked]
    small = [f.resize((SIZE, SIZE), Image.LANCZOS) for f in picked]

    pf = []
    for f in small:
        q = f.convert("RGB").quantize(colors=COLORS - 1, method=Image.MEDIANCUT).convert("P")
        pal = q.getpalette()[: (COLORS - 1) * 3]
        q.putpalette([0, 0, 0] + pal + [0, 0, 0] * max(0, COLORS - 1 - len(pal) // 3))
        q = q.point(lambda v: min(COLORS - 1, v + 1))
        q.paste(0, mask=f.getchannel("A").point(lambda v: 255 if v == 0 else 0))
        pf.append(q)
    buf = io.BytesIO()
    pf[0].save(buf, format="GIF", save_all=True, append_images=pf[1:], duration=duration,
               loop=0, disposal=2, transparency=0, optimize=False)
    return buf.getvalue()


def main():
    rows = []
    for name in SAMPLE:
        try:
            src = download(name)
            w, h, n = probe(src)
            frames, n = decode(src, w, h, n)
            imgs = [Image.fromarray(a, "RGBA") for a in frames]
            for nf in (10, 12):
                data = encode(imgs, nf)
                rows.append((name, n, nf, len(data)))
                print(f"{name}  源{n}帧 {w}x{h} -> {nf}帧  {len(data)/1024:5.1f} KB")
        except Exception as e:
            print(f"{name}: FAIL {type(e).__name__} {e}")

    if rows:
        for nf in (10, 12):
            sizes = [r[3] for r in rows if r[2] == nf]
            if sizes:
                avg = sum(sizes) / len(sizes)
                print(f"\n[{nf}帧] 平均 {avg/1024:.1f} KB，114 个动作单档约 {avg*114/1048576:.2f} MB，三档约 {avg*114*3/1048576:.1f} MB")


if __name__ == "__main__":
    main()
