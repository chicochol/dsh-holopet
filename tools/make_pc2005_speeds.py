"""用现有的 normal 帧生成 slow / fast 两档（只改每帧 duration，画面不动）。"""
from pathlib import Path
from PIL import Image, ImageSequence

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "build" / "skins" / "pc2005"
SPEEDS = {"slow": 150, "normal": 120, "fast": 90}


def retime(src: Path, dst: Path, duration: int) -> int:
    im = Image.open(src)
    frames = []
    for fr in ImageSequence.Iterator(im):
        frames.append(fr.convert("P").copy())
    dst.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(dst, save_all=True, append_images=frames[1:],
                   duration=[duration] * len(frames), loop=0,
                   transparency=0, disposal=2, optimize=False)
    return dst.stat().st_size


def main():
    normal = BASE / "normal"
    gifs = sorted(normal.glob("*.gif"))
    print(f"源 {len(gifs)} 个")
    for speed, dur in SPEEDS.items():
        if speed == "normal":
            continue
        out = BASE / speed
        if out.exists():
            for f in out.glob("*.gif"):
                f.unlink()
        out.mkdir(parents=True, exist_ok=True)
        total = 0
        for i, gif in enumerate(gifs, 1):
            total += retime(gif, out / gif.name, dur)
            if i % 40 == 0:
                print(f"  {speed} {i}/{len(gifs)}")
        print(f"{speed}: {len(gifs)} files, {total/1024/1024:.2f} MB")


if __name__ == "__main__":
    main()
