"""按主题风格合成 4 组应用音效。

设计原则：不要尖锐 —— 基频控制在 200~1300Hz，谐波快速衰减，attack 8ms 以上，
整体幅度 0.30~0.42，全部用正弦/三角波，不用方波。
"""
import wave
from pathlib import Path

import numpy as np

RATE = 16000
OUT = Path('build/dsh_fish/assets/sounds')


def env_ad(n, attack=0.010, decay=6.0, curve=1.0):
    """attack-decay 包络，attack 用线性淡入避免爆音。"""
    t = np.arange(n) / RATE
    e = np.exp(-decay * np.maximum(t - attack, 0) * curve)
    a = int(RATE * attack)
    if a > 1:
        e[:a] *= np.linspace(0, 1, a)
    return e


def tone(freq, dur, amp=0.4, decay=8.0, attack=0.010, harmonics=((1, 1.0),), slide_to=None):
    n = int(RATE * dur)
    t = np.arange(n) / RATE
    if slide_to:
        f = np.linspace(freq, slide_to, n)
        phase = 2 * np.pi * np.cumsum(f) / RATE
    else:
        phase = 2 * np.pi * freq * t
    w = np.zeros(n, dtype=np.float64)
    for mult, weight in harmonics:
        w += weight * np.sin(phase * mult)
    w /= max(1e-6, sum(abs(h[1]) for h in harmonics))
    return (w * env_ad(n, attack, decay) * amp).astype(np.float32)


def tri(freq, dur, amp=0.4, decay=8.0, attack=0.010):
    n = int(RATE * dur)
    t = np.arange(n) / RATE
    w = 2 * np.abs(2 * ((freq * t) % 1) - 1) - 1
    return (w * env_ad(n, attack, decay) * amp).astype(np.float32)


def silence(dur):
    return np.zeros(int(RATE * dur), dtype=np.float32)


def seq(*parts):
    return np.concatenate(parts)


def mix(*parts):
    n = max(len(p) for p in parts)
    out = np.zeros(n, dtype=np.float32)
    for p in parts:
        out[: len(p)] += p
    return out


def save(path, sig):
    sig = np.clip(sig, -1, 1)
    data = (sig * 32767).astype('<i2')
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data.tobytes())


# ---------------- 四组主题 ----------------

def make_soft():
    """木质马林巴：基频 + 第 4 谐波，圆润，衰减中等。"""
    H = ((1, 1.0), (2, 0.18), (4, 0.10))
    return {
        'prompt': tone(523, 0.16, 0.36, 9, 0.012, H),
        'tool': tone(440, 0.10, 0.30, 14, 0.008, H),
        'done': seq(tone(523, 0.13, 0.36, 8, 0.012, H),
                    tone(659, 0.13, 0.36, 8, 0.012, H),
                    tone(784, 0.34, 0.38, 6, 0.012, H)),
        'error': seq(tone(392, 0.16, 0.36, 8, 0.012, H),
                     silence(0.03),
                     tone(330, 0.30, 0.36, 6, 0.012, H)),
        'ask': seq(tone(659, 0.12, 0.34, 10, 0.012, H),
                   silence(0.06),
                   tone(659, 0.18, 0.34, 9, 0.012, H)),
        'start': seq(tone(392, 0.14, 0.34, 8, 0.012, H),
                     tone(523, 0.14, 0.36, 8, 0.012, H),
                     tone(659, 0.36, 0.38, 6, 0.012, H)),
    }


def make_crystal():
    """玻璃/风铃：非整数谐波，长衰减，幅度压低避免刺耳。"""
    H = ((1, 1.0), (2.76, 0.22), (5.40, 0.08))
    return {
        'prompt': tone(880, 0.30, 0.26, 5.0, 0.014, H),
        'tool': tone(1046, 0.18, 0.22, 8.0, 0.010, H),
        'done': seq(tone(784, 0.22, 0.26, 5.5, 0.014, H),
                    tone(1046, 0.42, 0.26, 4.5, 0.014, H)),
        'error': seq(tone(587, 0.22, 0.26, 5.5, 0.014, H),
                     silence(0.04),
                     tone(494, 0.40, 0.26, 4.5, 0.014, H)),
        'ask': seq(tone(880, 0.20, 0.24, 6.5, 0.014, H),
                   silence(0.08),
                   tone(880, 0.28, 0.24, 6.0, 0.014, H)),
        'start': seq(tone(659, 0.10, 0.24, 7.0, 0.012, H),
                     tone(880, 0.10, 0.25, 7.0, 0.012, H),
                     tone(1319, 0.44, 0.24, 4.0, 0.016, H)),
    }


def make_retro():
    """复古 8bit：三角波（比方波柔和）+ 短衰减。"""
    return {
        'prompt': tri(523, 0.12, 0.32, 12),
        'tool': tri(392, 0.08, 0.28, 16),
        'done': seq(tri(523, 0.10, 0.32, 10),
                    tri(659, 0.10, 0.32, 10),
                    tri(784, 0.26, 0.34, 8)),
        'error': seq(tri(311, 0.14, 0.32, 10),
                     silence(0.03),
                     tri(262, 0.28, 0.32, 8)),
        'ask': seq(tri(659, 0.10, 0.30, 12),
                   silence(0.05),
                   tri(659, 0.16, 0.30, 11)),
        'start': seq(tri(440, 0.10, 0.30, 10),
                     tri(554, 0.10, 0.32, 10),
                     tri(659, 0.30, 0.34, 7)),
    }


def make_nature():
    """水滴 / 气泡：频率下滑，短促柔和。"""
    return {
        'prompt': tone(760, 0.16, 0.34, 11, 0.008, ((1, 1.0),), slide_to=520),
        'tool': tone(640, 0.10, 0.28, 16, 0.006, ((1, 1.0),), slide_to=480),
        'done': mix(
            tone(520, 0.20, 0.32, 9, 0.008, ((1, 1.0),), slide_to=760),
            seq(silence(0.16), tone(880, 0.34, 0.26, 7, 0.010, ((1, 1.0),), slide_to=620)),
        ),
        'error': seq(tone(420, 0.20, 0.34, 9, 0.010, ((1, 1.0),), slide_to=280),
                     silence(0.05),
                     tone(320, 0.30, 0.32, 8, 0.010, ((1, 1.0),), slide_to=200)),
        'ask': seq(tone(700, 0.14, 0.30, 11, 0.008, ((1, 1.0),), slide_to=560),
                   silence(0.07),
                   tone(700, 0.18, 0.30, 10, 0.008, ((1, 1.0),), slide_to=560)),
        'start': seq(tone(480, 0.16, 0.30, 9, 0.008, ((1, 1.0),), slide_to=700),
                     silence(0.04),
                     tone(700, 0.38, 0.28, 6, 0.012, ((1, 1.0),), slide_to=900)),
    }


GROUPS = {
    'soft': ('木质', make_soft()),
    'crystal': ('水晶', make_crystal()),
    'retro': ('复古', make_retro()),
    'nature': ('水滴', make_nature()),
}

for gid, (zh, sounds) in GROUPS.items():
    total = 0
    for name, sig in sounds.items():
        p = OUT / gid / (name + '.wav')
        save(p, sig)
        total += p.stat().st_size
    print(f'{gid} ({zh}): {len(sounds)} 个音效，合计 {total/1024:.1f} KB')
