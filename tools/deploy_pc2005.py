"""把重转后的 pc2005 皮肤装进应用目录：复制 normal/ + 给移动动画生成镜像。"""
import shutil
from pathlib import Path
from PIL import Image, ImageSequence

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "build" / "skins" / "pc2005"
DST = ROOT / "build" / "dsh_fish" / "assets" / "skins" / "pc2005"

# 需要镜像的动作（会左右移动或侧身站立）
MIRROR = [
    "pangxie-zoulu",
    "yuandi-piaofu-tabu",
    "yuandi-zuozhuan-benpao",
    "ceshen-jizao-pao",
    "kaixin-xiaopao",
]


def mirror_gif(src: Path, dst: Path) -> int:
    im = Image.open(src)
    frames, durs = [], []
    for fr in ImageSequence.Iterator(im):
        frames.append(fr.convert("P").transpose(Image.FLIP_LEFT_RIGHT))
        durs.append(fr.info.get("duration", 120))
    dst.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(dst, save_all=True, append_images=frames[1:], duration=durs,
                   loop=0, transparency=0, disposal=2, optimize=False)
    return dst.stat().st_size


def main():
    if DST.exists():
        shutil.rmtree(DST)
    (DST / "normal").mkdir(parents=True, exist_ok=True)

    n = 0
    total = 0
    for gif in sorted((SRC / "normal").glob("*.gif")):
        out = DST / "normal" / gif.name
        shutil.copy2(gif, out)
        n += 1
        total += out.stat().st_size

    shutil.copy2(SRC / "manifest.lua", DST / "manifest.lua")
    total += (DST / "manifest.lua").stat().st_size

    m = 0
    for name in MIRROR:
        src = SRC / "normal" / (name + ".gif")
        if not src.exists():
            print("  skip mirror (missing):", name)
            continue
        size = mirror_gif(src, DST / "mirror" / "normal" / (name + ".gif"))
        m += 1
        total += size

    print(f"copied {n} gifs + {m} mirrors, {total / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    main()
