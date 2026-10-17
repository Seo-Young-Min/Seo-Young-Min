"""한국풍(한지·수묵·단청 색감) 스마트팜 애니메이션 3종

    greenhouse : 비닐하우스 센서 → 데이터가 흘러 모니터 그래프로 (데이터의 중요성·활용)
    scroll     : 두루마리에 환경 측정 기록이 한 칸씩 채워지고 새싹이 자람 (숫자 하나의 의미)
    fix        : 표의 오류값을 돋보기로 찾아 붓 원으로 표시, 바로잡고 '검수완료' 도장 (오류 바로잡기)

하단 자막 자리(y > 840)는 비워 둔다. 2배 크기로 그린 뒤 줄여서 테두리를 매끄럽게 한다.
"""
import math
import os
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1920, 1080, 30
S = 2  # 슈퍼샘플링 배율

INK = (40, 38, 45)
INDIGO = (44, 62, 107)
RED = (178, 62, 44)
GREEN = (58, 125, 107)
OCHRE = (217, 164, 65)
PAPER = (236, 226, 204)


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def seg(t, a, b):
    return ease((t - a) / (b - a)) if b > a else float(t >= a)


def hanji_bg(seed=3, mountains=True, sun=True, light=False):
    rng = np.random.default_rng(seed)
    base = np.ones((H, W, 3)) * np.array(PAPER, dtype=float)
    base += rng.normal(0, 3.5, (H, W, 1))
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))
    # 한지 섬유
    fib = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(fib)
    for _ in range(1400):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        a = rng.uniform(0, math.pi)
        ln = rng.uniform(8, 40)
        d.line([(x, y), (x + ln * math.cos(a), y + ln * math.sin(a))], fill=int(rng.uniform(20, 60)), width=1)
    fib = fib.filter(ImageFilter.GaussianBlur(0.8))
    img = Image.composite(Image.new("RGB", (W, H), (250, 244, 230)), img, fib)
    img = img.convert("RGBA")
    if sun:
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(lay).ellipse([500, 110, 620, 230], fill=RED + (200,))
        img.alpha_composite(lay.filter(ImageFilter.GaussianBlur(1.5)))
    if mountains:
        for k, (yb, amp, alpha, blur) in enumerate([(430, 150, 55, 6), (520, 120, 85, 4), (610, 90, 120, 3)]):
            if light:
                alpha = int(alpha * 0.45)
            xs = np.linspace(-50, W + 50, 60)
            ph = rng.uniform(0, 6, 3)
            ys = yb - amp * (0.55 * np.sin(xs / 260 + ph[0]) + 0.3 * np.sin(xs / 120 + ph[1])
                             + 0.15 * np.sin(xs / 55 + ph[2])) ** 2 / 1.0
            poly = [(x, y) for x, y in zip(xs, ys)] + [(W + 50, H), (-50, H)]
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(lay).polygon(poly, fill=INK + (alpha,))
            # 수묵 번짐: 아래로 갈수록 옅게
            fade = Image.linear_gradient("L").resize((W, H))
            fade = fade.point(lambda v, yb=yb: 255 if v < yb * 255 / H else max(0, 255 - (v - yb * 255 / H) * 4))
            lay.putalpha(Image.composite(lay.getchannel("A"), Image.new("L", (W, H), 0), fade))
            img.alpha_composite(lay.filter(ImageFilter.GaussianBlur(blur)))
    # 가장자리 비네팅
    vig = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vig).rectangle([0, 0, W, H], outline=255, width=90)
    vig = vig.filter(ImageFilter.GaussianBlur(80)).point(lambda v: int(v * 0.45))
    img.alpha_composite(Image.merge("RGBA", [Image.new("L", (W, H), 60)] * 3 + [vig]))
    return img.convert("RGB")


class Canvas:
    """2배 크기 RGBA 레이어에 1배 좌표로 그리기."""

    def __init__(self):
        self.im = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def p(self, pts):
        return [(x * S, y * S) for x, y in pts]

    def b(self, box):
        return [v * S for v in box]

    def line(self, pts, fill, width=2):
        self.d.line(self.p(pts), fill=fill, width=int(width * S), joint="curve")

    def _soft(self, box, pad, draw_fn):
        """반투명 도형은 작은 임시 레이어에 그려 겹쳐 붙임 (아래 도형과 제대로 섞이도록)."""
        x0, y0 = int(box[0] * S) - pad, int(box[1] * S) - pad
        x1, y1 = int(box[2] * S) + pad, int(box[3] * S) + pad
        lay = Image.new("RGBA", (max(1, x1 - x0), max(1, y1 - y0)), (0, 0, 0, 0))
        draw_fn(ImageDraw.Draw(lay), [-x0, -y0])
        self.im.alpha_composite(lay, dest=(max(0, x0), max(0, y0)),
                                source=(max(0, -x0), max(0, -y0)))

    @staticmethod
    def _translucent(*colors):
        return any(c is not None and len(c) == 4 and c[3] < 255 for c in colors)

    def rect(self, box, fill=None, outline=None, width=2, r=0):
        def go(d, off):
            b = [box[0] * S + off[0], box[1] * S + off[1], box[2] * S + off[0], box[3] * S + off[1]]
            if r:
                d.rounded_rectangle(b, r * S, fill=fill, outline=outline, width=int(width * S))
            else:
                d.rectangle(b, fill=fill, outline=outline, width=int(width * S))
        if self._translucent(fill, outline):
            self._soft(box, int(width * S) + 4, go)
        else:
            go(self.d, [0, 0])

    def circle(self, c, r, fill=None, outline=None, width=2):
        box = [c[0] - r, c[1] - r, c[0] + r, c[1] + r]

        def go(d, off):
            d.ellipse([box[0] * S + off[0], box[1] * S + off[1], box[2] * S + off[0], box[3] * S + off[1]],
                      fill=fill, outline=outline, width=int(width * S))
        if self._translucent(fill, outline):
            self._soft(box, int(width * S) + 4, go)
        else:
            go(self.d, [0, 0])

    def arc(self, box, a0, a1, fill, width=2):
        self.d.arc(self.b(box), a0, a1, fill=fill, width=int(width * S))

    def poly(self, pts, fill=None, outline=None):
        self.d.polygon(self.p(pts), fill=fill, outline=outline)

    def text(self, xy, s, fnt, fill, anchor="mm"):
        self.d.text((xy[0] * S, xy[1] * S), s, font=fnt, fill=fill, anchor=anchor)

    def frame(self, bg):
        small = self.im.resize((W, H), Image.LANCZOS)
        out = bg.convert("RGBA")
        out.alpha_composite(small)
        return out.convert("RGB")


def bezier(p0, p1, p2, t):
    return ((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
            (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1])


# ───────────────────────── 1. 비닐하우스 + 데이터 흐름 ─────────────────────────
def greenhouse_static(fd):
    bg = hanji_bg(seed=5).convert("RGBA")
    c = Canvas()
    # 들판
    c.poly([(0, 640), (W, 610), (W, 860), (0, 860)], fill=(150, 160, 98, 255))
    for k in range(9):
        y = 650 + k * 24
        c.line([(0, y + 6), (W, y - 8)], fill=(120, 136, 80, 160), width=2)
    # 비닐하우스 3동 (뒤에서 앞으로)
    for x0, y0, w, h, a in [(470, 640, 300, 120, 150), (180, 690, 380, 150, 190), (600, 715, 420, 165, 215)]:
        box = [x0, y0 - h, x0 + w, y0 + h]
        c.d.chord(c.b(box), 180, 360, fill=(250, 252, 248, a), outline=INDIGO + (255,), width=3 * S)
        for k in range(1, 8):
            xx = x0 + w * k / 8
            dy = h * math.sqrt(max(0, 1 - ((xx - x0 - w / 2) / (w / 2)) ** 2))
            c.line([(xx, y0), (xx, y0 - dy)], fill=INDIGO + (110,), width=1.5)
        c.line([(x0, y0), (x0 + w, y0)], fill=INDIGO + (255,), width=3)
        # 안쪽 작물
        for k in range(14):
            xx = x0 + 20 + (w - 40) * k / 13
            c.circle((xx, y0 - 14), 9, fill=GREEN + (200,))
        c.rect([x0 + w / 2 - 22, y0 - 58, x0 + w / 2 + 22, y0], outline=INDIGO + (220,), width=2)
    # 모니터(창살 테두리)
    c.rect([1180, 110, 1820, 600], fill=(252, 247, 236, 240), outline=INDIGO + (255,), width=5, r=18)
    c.rect([1194, 124, 1806, 586], outline=RED + (200,), width=2, r=12)
    c.text((1500, 165), "스마트팜 환경 데이터", font(fd, "NanumMyeongjoEB.ttf", 38 * S), INK + (255,))
    c.line([(1240, 520), (1760, 520)], fill=INK + (200,), width=2)
    c.line([(1240, 520), (1240, 210)], fill=INK + (200,), width=2)
    return c.frame(bg)


SENSORS = [(330, 690), (760, 640), (880, 715)]


def greenhouse_frame(t, dur, bg, fd):
    c = Canvas()
    f_small = font(fd, "NanumMyeongjoEB.ttf", 24 * S)
    # 센서 기둥 + 신호 고리
    for k, (x, y) in enumerate(SENSORS):
        top = (x, y - 230)
        c.line([(x, y), top], fill=INK + (230,), width=4)
        c.rect([x - 16, top[1] - 26, x + 16, top[1] + 6], fill=(252, 247, 236, 255), outline=INDIGO + (255,), width=3)
        on = (math.sin(t * 6 + k) > 0)
        c.circle((x, top[1] - 10), 5, fill=(GREEN if on else OCHRE) + (255,))
        for j in range(3):
            r = ((t * 45 + j * 30 + k * 12) % 90)
            a = int(200 * (1 - r / 90) * seg(t, 0.3, 1.0))
            c.circle((x, top[1] - 10), 20 + r, outline=GREEN + (a,), width=3)
    # 데이터 점: 센서 → 모니터
    for k, (x, y) in enumerate(SENSORS):
        p0 = (x, y - 250)
        p2 = (1240, 300 + k * 70)
        p1 = ((p0[0] + p2[0]) / 2, 60 + k * 40)
        for j in range(7):
            u = ((t * 0.35 + j / 7 + k * 0.11) % 1.0)
            if t < 0.8 + u * 0.5:
                continue
            q = bezier(p0, p1, p2, u)
            a = int(255 * math.sin(math.pi * u))
            c.circle(q, 9, fill=OCHRE + (int(a * 0.35),))
            c.circle(q, 5, fill=(RED if j % 3 == 0 else OCHRE) + (a,))
    # 그래프가 그려짐
    prog = seg(t, 1.2, dur - 2.0)
    n = 40
    pts = []
    for i in range(int(n * prog) + 1):
        xx = 1240 + 520 * i / n
        yy = 430 - 120 * (0.5 + 0.35 * math.sin(i / 5.0) + 0.15 * math.sin(i / 1.7)) + i * 1.5
        pts.append((xx, yy))
    if len(pts) > 1:
        c.line(pts, fill=GREEN + (255,), width=5)
        c.circle(pts[-1], 8, fill=RED + (255,))
    # 수치 카드
    vals = [("온도", 24.3, "°C"), ("습도", 65, "%"), ("CO2", 450, "ppm")]
    for k, (name, v, unit) in enumerate(vals):
        a = seg(t, 1.5 + k * 0.6, 2.2 + k * 0.6)
        if a <= 0:
            continue
        x = 1325 + k * 175
        c.rect([x - 84, 538, x + 84, 578], fill=(255, 255, 255, int(230 * a)), outline=INDIGO + (int(255 * a),),
               width=2, r=8)
        shown = v * min(1, a * 1.2)
        txt = f"{name} {shown:.1f}{unit}" if isinstance(v, float) else f"{name} {int(shown)}{unit}"
        c.text((x, 558), txt, f_small, INK + (int(255 * a),))
    return c.frame(bg)


# ───────────────────────── 2·3. 두루마리 기록표 ─────────────────────────
COLS = ["시각", "온도(°C)", "습도(%)", "CO2(ppm)", "일사(W/m²)"]
ROWS = [["06:00", "18.2", "82", "520", "15"], ["09:00", "22.6", "71", "460", "310"],
        ["12:00", "26.9", "58", "410", "720"], ["15:00", "27.4", "55", "395", "540"],
        ["18:00", "23.1", "66", "430", "80"], ["21:00", "19.8", "78", "505", "0"]]
TX0, TX1, TY0 = 380, 1540, 250
ROW_H = 72


def col_x(i):
    return TX0 + (TX1 - TX0) * (i + 0.5) / len(COLS)


def scroll_paper(c, open_k, fd):
    """가운데에서 양옆으로 펼쳐지는 두루마리. open_k: 0~1"""
    cx = (TX0 + TX1) / 2
    half = (TX1 - TX0) / 2 + 80
    l, r = cx - half * open_k - 10, cx + half * open_k + 10
    c.rect([l, 140, r, 760], fill=(250, 243, 225, 255), outline=(150, 120, 80, 255), width=2)
    if r - l > 40:
        c.rect([l + 14, 154, r - 14, 746], outline=RED + (160,), width=1.5)
    for x in (l - 18, r - 4):
        c.rect([x, 118, x + 22, 782], fill=(110, 70, 40, 255), r=8)
        c.circle((x + 11, 118), 15, fill=(90, 55, 30, 255))
        c.circle((x + 11, 782), 15, fill=(90, 55, 30, 255))
    return l, r


def table_grid(c, fd, alpha=255, clip=None):
    f_h = font(fd, "NanumMyeongjoEB.ttf", 32 * S)
    c.text(((TX0 + TX1) / 2, 195), "환경 측정 기록", font(fd, "NanumMyeongjoEB.ttf", 40 * S), INK + (alpha,))
    for i, name in enumerate(COLS):
        c.text((col_x(i), TY0 + 30), name, f_h, INDIGO + (alpha,))
    c.line([(TX0, TY0 + 62), (TX1, TY0 + 62)], fill=INK + (alpha,), width=3)
    for k in range(len(ROWS) + 1):
        y = TY0 + 62 + k * ROW_H
        c.line([(TX0, y), (TX1, y)], fill=INK + (int(alpha * 0.35),), width=1.5)
    for i in range(1, len(COLS)):
        x = TX0 + (TX1 - TX0) * i / len(COLS)
        c.line([(x, TY0 + 10), (x, TY0 + 62 + len(ROWS) * ROW_H)], fill=INK + (int(alpha * 0.25),), width=1.5)


def cell_center(r, i):
    return col_x(i), TY0 + 62 + ROW_H * (r + 0.5)


def sprout(c, base, k):
    """새싹: k 0~1 만큼 자람"""
    if k <= 0:
        return
    x, y = base
    c.poly([(x - 60, y), (x + 60, y), (x + 45, y + 70), (x - 45, y + 70)], fill=(150, 90, 55, 255))
    c.rect([x - 66, y - 10, x + 66, y + 4], fill=(120, 70, 40, 255), r=4)
    hgt = 150 * k
    c.line([(x, y - 8), (x, y - 8 - hgt)], fill=GREEN + (255,), width=6)
    for j, (dy, side) in enumerate([(0.45, -1), (0.7, 1), (0.95, -1)]):
        kk = seg(k, 0.25 + j * 0.2, 0.55 + j * 0.2)
        if kk <= 0:
            continue
        cx, cy = x + side * 34 * kk, y - 8 - hgt * dy
        c.d.ellipse(c.b([cx - 34 * kk, cy - 14 * kk, cx + 34 * kk, cy + 14 * kk]), fill=GREEN + (255,))


def scroll_frame(t, dur, bg, fd):
    c = Canvas()
    open_k = seg(t, 0.2, 1.6)
    scroll_paper(c, open_k, fd)
    if open_k >= 0.98:
        table_grid(c, fd)
        f = font(fd, "NanumMyeongjoEB.ttf", 32 * S)
        cells = [(r, i) for r in range(len(ROWS)) for i in range(len(COLS))]
        span = max(dur - 4.0, 3.0)
        for n, (r, i) in enumerate(cells):
            a = seg(t, 1.8 + span * n / len(cells), 2.1 + span * n / len(cells))
            if a > 0:
                c.text(cell_center(r, i), ROWS[r][i], f, INK + (int(255 * a),))
        # 한 줄씩 비추는 황토빛 띠
        hl = (t - 1.8) / span * len(ROWS)
        if 0 <= hl < len(ROWS):
            r = int(hl)
            y = TY0 + 62 + r * ROW_H
            c.rect([TX0 + 4, y + 4, TX1 - 4, y + ROW_H - 4], fill=OCHRE + (50,), r=6)
    sprout(c, (1790, 700), seg(t, 2.0, dur - 1.0))
    return c.frame(bg)


ERR = (2, 1)  # 12:00 온도 칸
ERR_BAD, ERR_GOOD = "-999.0", "26.9"


def fix_frame(t, dur, bg, fd):
    c = Canvas()
    scroll_paper(c, 1.0, fd)
    table_grid(c, fd)
    f = font(fd, "NanumMyeongjoEB.ttf", 32 * S)
    ex, ey = cell_center(*ERR)
    t_find, t_circle, t_fix, t_seal = 1.2, 3.0, 4.2, 5.4
    k = (dur - 1.5) / 6.8  # 장면 길이에 맞춰 늘이기
    t_find, t_circle, t_fix, t_seal = (v * k for v in (t_find, t_circle, t_fix, t_seal))
    for r in range(len(ROWS)):
        for i in range(len(COLS)):
            if (r, i) == ERR:
                continue
            c.text(cell_center(r, i), ROWS[r][i], f, INK + (255,))
    # 오류 칸
    fixed = seg(t, t_fix, t_fix + 0.7)
    if fixed < 1:
        blink = 0.6 + 0.4 * math.sin(t * 8) if t < t_circle else 1.0
        c.rect([ex - 100, ey - 30, ex + 100, ey + 30], fill=RED + (int(45 * blink * (1 - fixed)),), r=6)
        c.text((ex, ey), ERR_BAD, f, RED + (int(255 * (1 - fixed)),))
    if fixed > 0:
        c.text((ex, ey), ERR_GOOD, f, GREEN + (int(255 * fixed),))
    # 돋보기
    g = seg(t, 0.3, t_find)
    gx = 1700 + (ex + 40 - 1700) * g
    gy = 700 + (ey + 30 - 700) * g
    gone = seg(t, t_fix + 0.6, t_fix + 1.4)
    if gone < 1:
        a = int(255 * (1 - gone))
        c.circle((gx, gy), 70, fill=(255, 255, 255, int(40 * (1 - gone))), outline=INDIGO + (a,), width=8)
        c.line([(gx + 50, gy + 50), (gx + 120, gy + 120)], fill=(110, 70, 40, a), width=16)
    # 붓으로 그린 원
    pc = seg(t, t_circle, t_circle + 0.9)
    if pc > 0:
        for w, off in ((7, 0), (3, 4)):
            c.arc([ex - 125 - off, ey - 50 + off, ex + 125 + off, ey + 50 - off], -100, -100 + 350 * pc,
                  RED + (230,), width=w)
    # 체크 표시
    ck = seg(t, t_fix + 0.4, t_fix + 1.0)
    if ck > 0:
        p0, p1, p2 = (ex + 140, ey), (ex + 165, ey + 25), (ex + 215, ey - 35)
        pts = [p0, (p0[0] + (p1[0] - p0[0]) * min(1, ck * 2), p0[1] + (p1[1] - p0[1]) * min(1, ck * 2))]
        if ck > 0.5:
            u = (ck - 0.5) * 2
            pts.append((p1[0] + (p2[0] - p1[0]) * u, p1[1] + (p2[1] - p1[1]) * u))
        c.line(pts, fill=GREEN + (255,), width=9)
    # 검수완료 도장
    st = seg(t, t_seal, t_seal + 0.35)
    if st > 0:
        scale = 1.6 - 0.6 * st
        sx, sy, half = 1640, 640, 78 * scale
        a = int(235 * st)
        c.rect([sx - half, sy - half, sx + half, sy + half], fill=RED + (int(a * 0.12),), outline=RED + (a,),
               width=7 * scale, r=10)
        fs = font(fd, "NanumMyeongjoEB.ttf", int(46 * scale * S))
        c.text((sx, sy - 26 * scale), "검수", fs, RED + (a,))
        c.text((sx, sy + 30 * scale), "완료", fs, RED + (a,))
    return c.frame(bg)


def font(fd, name, size):
    return ImageFont.truetype(os.path.join(fd, name), size)


def render(name, dur, out, fd):
    if name == "greenhouse":
        bg = greenhouse_static(fd)
        fn = greenhouse_frame
    elif name == "scroll":
        bg = hanji_bg(seed=11, light=True)
        fn = scroll_frame
    elif name == "fix":
        bg = hanji_bg(seed=17, light=True, sun=False)
        fn = fix_frame
    else:
        raise ValueError(name)
    n = int(round(dur * FPS))
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "16",
                          "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
    for k in range(n):
        p.stdin.write(fn(k / FPS, dur, bg, fd).tobytes())
    p.stdin.close()
    if p.wait():
        raise SystemExit(f"애니메이션 인코딩 실패: {name}")
