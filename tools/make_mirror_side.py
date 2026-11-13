import os
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKINS = os.path.join(ROOT, "build", "dsh_fish", "assets", "skins")
SPEEDS = ("slow", "normal", "fast")

# 侧身/半侧身、适合当水平移动动作的素材（依据源视频动作名与首帧姿态人工挑的）
SIDE_FACING = (
    "idle_02.gif",            # 东张西望
    "idle_04.gif",            # 照镜子
    "pretooluse.gif",         # 写代码
    "posttooluse.gif",        # 轻快记录
    "subagentstop.gif",       # 拆礼物
    "precompact.gif",         # 深度思考碎碎念
)


def mirror_gif(src, dst):
    im = Image.open(src)
    frames, durations = [], []
    n = getattr(im, "n_frames", 1)
    for i in range(n):
        im.seek(i)
        frame = im.copy()
        if frame.mode != "P":
            frame = frame.convert("P")
        frames.append(frame.transpose(Image.FLIP_LEFT_RIGHT))
        durations.append(im.info.get("duration", 120))
    if not frames:
        return 0
    trans = im.info.get("transparency", 0)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    frames[0].save(
        dst, save_all=True, append_images=frames[1:], duration=durations,
        loop=0, disposal=2, transparency=trans, optimize=False,
    )
    return len(frames)


total = 0
for skin in sorted(os.listdir(SKINS)):
    skin_dir = os.path.join(SKINS, skin)
    if not os.path.isdir(skin_dir):
        continue
    for speed in SPEEDS:
        src_dir = os.path.join(skin_dir, speed)
        if not os.path.isdir(src_dir):
            continue
        for name in SIDE_FACING:
            src = os.path.join(src_dir, name)
            if not os.path.exists(src):
                continue
            dst = os.path.join(skin_dir, "mirror", speed, name)
            n = mirror_gif(src, dst)
            total += 1
            print(f"{skin}/{speed}/{name}  {n}f  {os.path.getsize(dst)/1024:.1f}KB")

print(f"\nmirrored {total} side-facing files")
