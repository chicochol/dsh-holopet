"""逐个 GIF 检查尺寸/透明/异常帧（出框或反色）。"""
import sys
from pathlib import Path
from PIL import Image, ImageSequence

ROOT = Path(__file__).resolve().parent.parent
SKINS = ROOT / "build" / "dsh_fish" / "assets" / "skins"


def scan(path):
    im = Image.open(path)
    w, h = im.size
    issues = []
    frames = list(ImageSequence.Iterator(im))
    cover = []
    for i, fr in enumerate(frames):
        rgba = fr.convert("RGBA")
        alpha = rgba.getchannel("A")
        opaque = alpha.point(lambda v: 255 if v > 16 else 0)
        bb = opaque.getbbox()
        if bb is None:
            cover.append(1.0)
            issues.append(f"f{i} 全透明")
            continue
        frac = 1 - (sum(1 for v in alpha.getdata() if v > 16) / (w * h))
        cover.append(round(frac, 3))
        if bb[0] <= 0 or bb[1] <= 0 or bb[2] >= w or bb[3] >= h:
            issues.append(f"f{i} 触边 bbox={bb}")
    return w, h, len(frames), cover, issues


def main():
    worst = []
    for skin in sorted(SKINS.iterdir()):
        if not skin.is_dir():
            continue
        for speed in ("slow", "normal", "fast"):
            d = skin / speed
            if not d.is_dir():
                continue
            for gif in sorted(d.glob("*.gif")):
                w, h, n, cover, issues = scan(gif)
                tag = f"{skin.name}/{speed}/{gif.name}"
                if w != 160 or h != 160:
                    issues.insert(0, f"尺寸 {w}x{h}")
                if cover and (max(cover) - min(cover) > 0.25):
                    issues.append(f"透明占比跳变 {min(cover):.2f}~{max(cover):.2f}")
                if issues:
                    worst.append((tag, issues[:4], len(issues)))
    for tag, issues, n in worst:
        print(f"{tag}  ({n} 处)  " + " | ".join(issues))
    print(f"\n共 {len(worst)} 个文件有问题")


if __name__ == "__main__":
    main()
