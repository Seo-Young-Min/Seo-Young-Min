"""수료 영상용 잔잔한 가을 왈츠 배경음 생성기 (직접 작곡·합성, 저작권 걱정 없음)

G장조 3/4박 피아노 왈츠 + 현악 패드.
구성: 전주 4마디 → A 8마디 → B 8마디 → A' 8마디(현악 추가) → B' 8마디 → 후주 4마디

사용법:
    python make_music.py --seconds 100 --out bgm.wav
필요: numpy, scipy
"""
import argparse

import numpy as np
from scipy.io import wavfile
from scipy.signal import fftconvolve

SR = 44100


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


# 화음: (베이스, 화음 구성음 pitch class)
CH = {
    "G": (43, [7, 11, 2]), "D/F#": (42, [2, 6, 9]), "Em": (40, [4, 7, 11]),
    "C": (36, [0, 4, 7]), "Am7": (45, [9, 0, 4, 7]), "D7": (38, [2, 6, 9, 0]),
    "Dsus": (38, [2, 7, 9]), "D": (38, [2, 6, 9]), "Bm": (47, [11, 2, 6]),
    "Am": (45, [9, 0, 4]),
}
A_CH = ["G", "D/F#", "Em", "C", "Am7", "D7", "G", "Dsus"]
B_CH = ["C", "D", "Bm", "Em", "Am", "D", "G", "G"]
# 선율: 마디별 (MIDI 음, 박)
A_MEL = [[(71, 1.5), (72, .5), (74, 1)], [(74, 2), (69, 1)], [(71, 1.5), (69, .5), (67, 1)],
         [(64, 2), (67, 1)], [(72, 1.5), (71, .5), (69, 1)], [(66, 1), (69, 1), (72, 1)],
         [(71, 2), (69, .5), (67, .5)], [(69, 3)]]
B_MEL = [[(76, 1.5), (74, .5), (72, 1)], [(74, 1.5), (72, .5), (69, 1)], [(71, 1.5), (69, .5), (66, 1)],
         [(67, 2), (71, 1)], [(72, 1), (76, 1), (74, 1)], [(72, 1.5), (71, .5), (69, 1)],
         [(67, 3)], []]


def piano(f, dur, vel):
    n = int((dur + 2.5) * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for k in range(1, 9):
        fk = k * f * np.sqrt(1 + 0.0004 * k * k)
        if fk > SR / 2.2:
            break
        decay = 0.55 + 0.35 * k + f / 900
        out += (1 / k ** 1.4) * np.sin(2 * np.pi * fk * t) * np.exp(-t * decay)
    att = np.minimum(t / 0.006, 1)
    rel = np.where(t > dur, np.exp(-(t - dur) * 6), 1)  # 건반에서 손 뗌
    return out * att * rel * vel


def pad(f, dur, vel):
    n = int((dur + 1.5) * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for det in (-0.12, 0, 0.12):
        for k in range(1, 6):
            out += (1 / k ** 1.6) * np.sin(2 * np.pi * k * f * (1 + det / 100) * t + k * det)
    env = np.minimum(t / 0.9, 1) * np.where(t > dur, np.exp(-(t - dur) * 3), 1)
    vib = 1 + 0.003 * np.sin(2 * np.pi * 5 * t)
    return out * env * vib * vel / 3


def add(buf, sig, start, pan):
    i = int(start * SR)
    j = min(len(buf), i + len(sig))
    if j <= i:
        return
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    buf[i:j, 0] += sig[: j - i] * l
    buf[i:j, 1] += sig[: j - i] * r


def voicing(chord):
    bass, pcs = CH[chord]
    tones = sorted(m for m in range(bass + 7, bass + 27) if m % 12 in pcs)
    return bass, tones[:4]


def render(seconds):
    bars_total = 40
    bar = (seconds - 4.0) / bars_total
    beat = bar / 3
    buf = np.zeros((int((seconds + 3) * SR), 2))

    plan = ([("intro", c, None, False) for c in ["G", "C", "G", "Dsus"]]
            + [("a", c, m, False) for c, m in zip(A_CH, A_MEL)]
            + [("b", c, m, False) for c, m in zip(B_CH, B_MEL)]
            + [("a2", c, m, True) for c, m in zip(A_CH, A_MEL)]
            + [("b2", c, m, True) for c, m in zip(B_CH, B_MEL)]
            + [("outro", c, None, True) for c in ["C", "D", "G", "G"]])

    for bi, (sec, chord, mel, strings) in enumerate(plan):
        t0 = bi * bar
        bass, tones = voicing(chord)
        last = bi == len(plan) - 1
        if last:  # 마지막 화음은 굴려서 길게
            for k, m in enumerate([bass, bass + 12] + tones):
                add(buf, piano(mtof(m), 4.0, 0.22), t0 + k * 0.09, -0.3 + 0.15 * k)
            continue
        # 왼손 분산화음 (8분음표 6개)
        rit = 1.0 + (0.12 * (bi - (len(plan) - 4)) if sec == "outro" else 0)
        pattern = [bass, tones[0], tones[1], tones[2], tones[1], tones[0]]
        for k, m in enumerate(pattern):
            v = 0.20 if k == 0 else 0.11
            add(buf, piano(mtof(m), beat * 1.6, v), t0 + k * beat / 2 * rit, -0.35 + 0.12 * k)
        # 오른손 선율
        if mel:
            pos = 0.0
            for m, b in mel:
                up = 12 if sec == "a2" else 0
                add(buf, piano(mtof(m + up), b * beat * 0.95, 0.30), t0 + pos * beat, 0.2)
                pos += b
        # 현악 패드
        if strings:
            for m in tones[:3]:
                add(buf, pad(mtof(m), bar, 0.06), t0, 0.0)
            add(buf, pad(mtof(bass + 12), bar, 0.05), t0, 0.0)

    # 잔향
    rng = np.random.default_rng(7)
    ir_len = int(2.6 * SR)
    tt = np.arange(ir_len) / SR
    ir = rng.standard_normal((ir_len, 2)) * np.exp(-tt * 2.4)[:, None]
    ir[: int(0.02 * SR)] = 0
    wet = np.stack([fftconvolve(buf[:, c], ir[:, c])[: len(buf)] for c in range(2)], axis=1)
    wet /= np.max(np.abs(wet)) + 1e-9
    dry = buf / (np.max(np.abs(buf)) + 1e-9)
    mix = 0.72 * dry + 0.38 * wet
    # 고역 살짝 깎기 (따뜻한 소리)
    k = np.ones(5) / 5
    mix = np.stack([np.convolve(mix[:, c], k, mode="same") for c in range(2)], axis=1)
    mix = mix[: int(seconds * SR)]
    fade = int(3 * SR)
    mix[-fade:] *= np.linspace(1, 0, fade)[:, None]
    mix *= 0.85 / np.max(np.abs(mix))
    return (mix * 32767).astype(np.int16)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, required=True)
    ap.add_argument("--out", default="bgm.wav")
    a = ap.parse_args()
    wavfile.write(a.out, SR, render(a.seconds))
    print(f"완료: {a.out} ({a.seconds:.1f}초)")
