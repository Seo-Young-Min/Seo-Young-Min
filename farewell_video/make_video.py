"""빅데이터 조사 과정 수료 기념 · 동료 인사 영상 생성기

사용법:
    python make_video.py --media <사진·영상 폴더> --font-dir <폰트 폴더> --out farewell.mp4
    python make_video.py ... --music bgm.wav          # 배경음 함께 합성
    python make_video.py ... --print-length           # 영상 길이(초)만 출력 (배경음 길이 맞출 때)

필요: ffmpeg, Pillow
"""
import argparse
import os
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

W, H, FPS = 1920, 1080, 30
XF = 1.0  # 장면 전환(크로스페이드) 길이(초)
DATE_LINE = "2026. 10. 30."

# 자막 읽기 시간: 보통 사람이 편하게 읽는 속도(초당 약 4.5음절) 기준
SEC_PER_SYLLABLE = 0.22
READ_BASE = 1.3
LEAD, TAIL, FADE, GAP = 1.0, 1.0, 0.5, 0.35

# 장면: (종류, 파일, 자막 목록, 배치방식, 옵션)
#   자막 하나 = 한 화면에 함께 보이는 줄들(최대 3줄)
#   배치방식: cover = 16:9로 채움(켄번스), fit = 사진 전체 보이기, side = 시비 확대 + 오른쪽 자막
SCENES = [
    ("title", "783c445a-image.jpg", [["시월의 어느 멋진 날에", "빅데이터 조사 과정 8개월의 여정"]], None, {"dur": 7.0}),
    ("photo", "54cecf94-image.jpg", [["처음에는 낯설었던 데이터,", "하나하나 살피고 확인하며"],
                                     ["우리는 배움의 길을 걸었습니다."]], "cover", {}),
    ("video", "2e764b03-20261012_115501.mp4", [["데이터의 중요성과", "활용 가능성을 알게 되었습니다."]], None, {}),
    ("photo", "80f093a6-image.jpg", [["숫자 하나에도 의미가 있었고,"]], "cover", {}),
    ("photo", "993cc237-image.jpg", [["작은 오류 하나를 바로잡는 일에도", "정성과 책임이 필요했습니다."]], "cover", {}),
    ("photo", "7a1fce7a-image.jpg", [["8개월의 시간,", "때로는 힘들고", "때로는 보람 있었지만"]], "side",
     {"crop": (1320, 600, 2760, 2520), "min": 12.0}),
    ("photo", "932d9a62-image.jpg", [["함께했기에", "여기까지 올 수 있었습니다."]], "fit", {}),
    ("photo", "83520179-image.jpg", [["우리가 조사하고 검수한 작은 기록들이", "우리 농업의 더 나은 내일을 만들고,"]], "fit", {}),
    ("photo", "f030f540-image.jpg", [["미래를 여는 소중한 밑거름이", "되기를 바랍니다."]], "fit", {}),
    ("photo", "1a1db0fc-image.jpg", [["이제 하나의 여정은 마무리되지만,", "배움은 끝나지 않았습니다."]], "side",
     {"crop": (1250, 860, 2560, 2480), "min": 12.0}),
    ("photo", "0f24662b-image.jpg", [["함께한 모든 분께 감사드리며,", "8개월의 소중한 추억을 가슴에 담고"]], "cover", {}),
    ("video", "d3214c72-20261012_115648.mp4", [["또 다른 내일을 향해 나아갑니다."]], None, {}),
    ("outro", "f1eaf656-image.jpg", [["함께한 시간에 감사하며,", "우리의 도전은 계속됩니다."]], None, {"dur": 9.0}),
]

CAP_SIZE = 58          # 하단 자막: 모든 줄 같은 크기·굵기로 균형
SIDE_SIZE = 56         # 시비 장면 오른쪽 자막
SIDE_X0 = 1000         # 시비 장면 자막 영역 시작 x


def font(d, name, size):
    return ImageFont.truetype(os.path.join(d, name), size)


def syllables(lines):
    return sum(1 for ln in lines for ch in ln if "가" <= ch <= "힣" or ch.isalnum())


def read_time(lines):
    return READ_BASE + SEC_PER_SYLLABLE * syllables(lines)


def probe_duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def plan_scene(kind, src_path, caps, opts):
    """장면 길이와 자막별 (시작, 끝) 시각을 계산."""
    if kind in ("title", "outro"):
        return opts["dur"], []
    holds = [read_time(c) for c in caps]
    need = LEAD + sum(h + 2 * FADE for h in holds) + GAP * (len(caps) - 1) + TAIL
    if kind == "video":
        dur = probe_duration(src_path) - 0.1
        if need > dur:
            raise SystemExit(f"자막이 영상보다 깁니다: {caps}")
    else:
        dur = max(need, opts.get("min", 0))
    extra = (dur - need) / len(holds)  # 남는 시간은 자막을 더 오래 보여 줌
    t, windows = LEAD, []
    for h in holds:
        windows.append((t, t + 2 * FADE + h + extra))
        t = windows[-1][1] + GAP
    return dur, windows


def cover(im, w, h):
    return ImageOps.fit(im, (w, h), Image.LANCZOS, centering=(0.5, 0.5))


def blurred_bg(im, w, h, dim=0.35):
    bg = cover(im, w, h).filter(ImageFilter.GaussianBlur(w // 48))
    return Image.blend(bg, Image.new("RGB", (w, h), (0, 0, 0)), dim)


def fit_on_blur(im, w, h):
    """원본 전체를 보이게 하고 남는 공간은 같은 사진 흐림 배경으로 채움 (하단은 자막 자리)."""
    bg = blurred_bg(im, w, h)
    fg = ImageOps.contain(im, (w, int(h * 0.76)), Image.LANCZOS)
    bg.paste(fg, ((w - fg.width) // 2, int(h * 0.03)))
    return bg


def side_layout(im, crop, w, h):
    """시비 글씨 부분을 화면 높이 가득 확대해 왼쪽에 두고, 오른쪽은 자막 자리로 비움."""
    bg = blurred_bg(im, w, h, dim=0.55)
    stone = im.crop(crop)
    stone = ImageEnhance.Contrast(stone).enhance(1.15).filter(ImageFilter.UnsharpMask(2, 80, 2))
    sh = int(h * 0.96)
    stone = stone.resize((int(stone.width * sh / stone.height), sh), Image.LANCZOS)
    x = int(w * 0.07)
    y = (h - sh) // 2
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rectangle([x + 10, y + 14, x + stone.width + 10, y + sh + 14], fill=(0, 0, 0, 170))
    bg = bg.convert("RGBA")
    bg.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(w // 120)))
    bg = bg.convert("RGB")
    bg.paste(stone, (x, y))
    return bg


def shadow_text(img, xy, text, fnt, fill=(255, 255, 255, 255), anchor="mm", blur=6):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((xy[0] + 3, xy[1] + 4), text, font=fnt, fill=(0, 0, 0, 210), anchor=anchor)
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))
    ImageDraw.Draw(img).text(xy, text, font=fnt, fill=fill, anchor=anchor)


def fitted_font(fd, lines, size, max_w):
    """가장 긴 줄이 max_w를 넘지 않도록 글자 크기를 맞춤 (모든 줄 같은 크기)."""
    while size > 36:
        f = font(fd, "NanumMyeongjoEB.ttf", size)
        if max(f.getlength(ln) for ln in lines) <= max_w:
            return f, size
        size -= 2
    return font(fd, "NanumMyeongjoEB.ttf", size), size


def gradient_png(path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gh = 400
    grad = Image.new("L", (1, gh))
    for y in range(gh):
        grad.putpixel((0, y), int(185 * (y / (gh - 1)) ** 1.5))
    img.paste((0, 0, 0, 255), (0, H - gh, W, H), grad.resize((W, gh)))
    img.save(path)


def caption_png(path, lines, fd, side=False):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if side:
        area_w = W - SIDE_X0 - 80
        f, size = fitted_font(fd, lines, SIDE_SIZE, area_w)
        lh = int(size * 1.75)
        cx = SIDE_X0 + area_w // 2
        y0 = H // 2 - lh * (len(lines) - 1) // 2
        for k, ln in enumerate(lines):
            shadow_text(img, (cx, y0 + k * lh), ln, f)
    else:
        f, size = fitted_font(fd, lines, CAP_SIZE, W - 220)
        lh = int(size * 1.55)
        y_last = H - 95
        for k, ln in enumerate(lines):
            y = y_last - (len(lines) - 1 - k) * lh
            shadow_text(img, (W // 2, y), ln, f)
    img.save(path)


def title_frame(path, src, lines, fd, outro=False):
    base = cover(ImageOps.exif_transpose(Image.open(src)).convert("RGB"), W, H)
    base = base.filter(ImageFilter.GaussianBlur(7 if outro else 12))
    base = Image.blend(base, Image.new("RGB", (W, H), (20, 12, 30)), 0.5).convert("RGBA")
    d = ImageDraw.Draw(base)
    cy = H // 2 - 50
    big, small = lines
    if outro:
        f, _ = fitted_font(fd, [big, small], 84, W - 300)
        shadow_text(base, (W // 2, cy - 40), big, f)
        shadow_text(base, (W // 2, cy + 80), small, f, fill=(255, 240, 225, 255))
        d.line([(W // 2 - 220, cy + 175), (W // 2 + 220, cy + 175)], fill=(255, 225, 235, 200), width=2)
        shadow_text(base, (W // 2, cy + 235), DATE_LINE, font(fd, "NanumMyeongjo.ttf", 44),
                    fill=(240, 232, 245, 255))
    else:
        shadow_text(base, (W // 2, cy - 40), big, font(fd, "NanumMyeongjoEB.ttf", 112))
        d.line([(W // 2 - 280, cy + 55), (W // 2 + 280, cy + 55)], fill=(255, 225, 235, 200), width=2)
        shadow_text(base, (W // 2, cy + 135), small, font(fd, "NanumMyeongjoEB.ttf", 64),
                    fill=(255, 240, 225, 255))
        shadow_text(base, (W // 2, cy + 235), DATE_LINE, font(fd, "NanumMyeongjo.ttf", 44),
                    fill=(240, 232, 245, 255))
    base.convert("RGB").save(path, quality=95)


def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if r.returncode:
        raise SystemExit(r.stderr[-2000:])


def plan_all(media):
    plans = []
    for kind, src, caps, mode, opts in SCENES:
        dur, windows = plan_scene(kind, os.path.join(media, src), caps, opts)
        plans.append((dur, windows))
    total = sum(d for d, _ in plans) - XF * (len(plans) - 1)
    return plans, total


def build(media, fd, out, music):
    plans, total = plan_all(media)
    tmp = tempfile.mkdtemp(prefix="farewell_")
    grad = os.path.join(tmp, "grad.png")
    gradient_png(grad)
    segs = []
    enc = ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an"]
    for i, ((kind, src, caps, mode, opts), (dur, windows)) in enumerate(zip(SCENES, plans)):
        seg = os.path.join(tmp, f"seg{i:02d}.mp4")
        frames = int(dur * FPS)
        src_path = os.path.join(media, src)
        if kind in ("title", "outro"):
            still = os.path.join(tmp, f"still{i}.jpg")
            title_frame(still, src_path, caps[0], fd, outro=(kind == "outro"))
            vf = (f"scale=3840:2160,zoompan=z='1+0.04*on/{frames}':x='iw/2-(iw/zoom/2)':"
                  f"y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS}")
            run(["ffmpeg", "-y", "-loop", "1", "-i", still, "-vf", vf, "-t", f"{dur:.2f}", *enc, seg])
        else:
            if kind == "photo":
                im = ImageOps.exif_transpose(Image.open(src_path)).convert("RGB")
                still = os.path.join(tmp, f"still{i}.jpg")
                if mode == "side":
                    side_layout(im, opts["crop"], W, H).save(still, quality=95)
                    vf_bg = f"scale={W}:{H},fps={FPS}"  # 글씨를 읽어야 하므로 움직이지 않음
                else:
                    big_im = cover(im, 3840, 2160) if mode == "cover" else fit_on_blur(im, 3840, 2160)
                    big_im.save(still, quality=95)
                    zmax = 0.10 if mode == "cover" else 0.03
                    drift = ""
                    if mode == "cover":
                        drift = ("+" if i % 2 else "-") + f"(on/{frames})*iw*0.02"
                    vf_bg = (f"zoompan=z='1+{zmax}*on/{frames}':x='iw/2-(iw/zoom/2){drift}':"
                             f"y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS}")
                inputs = ["-loop", "1", "-i", still]
            else:
                vf_bg = f"scale={W}:{H},fps={FPS}"
                inputs = ["-i", src_path]

            side = mode == "side"
            fc = [f"[0:v]{vf_bg},format=rgba[l0]"]
            n_in = 1
            last = "l0"
            if not side:  # 하단 그라데이션은 장면 내내 유지
                inputs += ["-loop", "1", "-t", f"{dur:.2f}", "-i", grad]
                fc.append(f"[{n_in}:v]format=rgba,fade=t=in:st=0.4:d=0.8:alpha=1,"
                          f"fade=t=out:st={dur - 1.0:.2f}:d=0.6:alpha=1[g]")
                fc.append(f"[{last}][g]overlay=0:0[l{n_in}]")
                last = f"l{n_in}"
                n_in += 1
            for k, (lines, (t0, t1)) in enumerate(zip(caps, windows)):
                cap = os.path.join(tmp, f"cap{i}_{k}.png")
                caption_png(cap, lines, fd, side=side)
                inputs += ["-loop", "1", "-t", f"{dur:.2f}", "-i", cap]
                fc.append(f"[{n_in}:v]format=rgba,fade=t=in:st={t0:.2f}:d={FADE}:alpha=1,"
                          f"fade=t=out:st={t1 - FADE:.2f}:d={FADE}:alpha=1[c{k}]")
                fc.append(f"[{last}][c{k}]overlay=0:0[l{n_in}]")
                last = f"l{n_in}"
                n_in += 1
            fc.append(f"[{last}]format=yuv420p[v]")
            run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", "[v]",
                 "-t", f"{dur:.2f}", *enc, seg])
        segs.append((seg, dur))
        print(f"  [{i + 1}/{len(SCENES)}] {dur:5.1f}초  {' / '.join(caps[0])}")

    # 크로스페이드로 이어 붙이기
    args, chain, off = [], "", 0.0
    for seg, _ in segs:
        args += ["-i", seg]
    prev = "0:v"
    for k in range(1, len(segs)):
        off += segs[k - 1][1] - XF
        lab = f"x{k}"
        chain += f"[{prev}][{k}:v]xfade=transition=fade:duration={XF}:offset={off:.2f}[{lab}];"
        prev = lab
    chain += f"[{prev}]fade=t=in:st=0:d=1.2,fade=t=out:st={total - 2:.2f}:d=2[v]"

    amap = []
    if music:
        args += ["-i", music]
        a = len(segs)
        chain += (f";[{a}:a]atrim=0:{total:.2f},asetpts=PTS-STARTPTS,afade=t=in:d=1.5,"
                  f"afade=t=out:st={total - 4:.2f}:d=4[a]")
        amap = ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    run(["ffmpeg", "-y", *args, "-filter_complex", chain, "-map", "[v]", *amap,
         "-c:v", "libx264", "-preset", "slow", "-crf", "23", "-maxrate", "9M", "-bufsize", "18M",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", out])
    print(f"완료: {out}  ({total:.1f}초)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--media", required=True)
    ap.add_argument("--font-dir")
    ap.add_argument("--out", default="farewell.mp4")
    ap.add_argument("--music", help="배경음 파일(wav/mp3 등)")
    ap.add_argument("--print-length", action="store_true", help="영상 길이(초)만 출력")
    a = ap.parse_args()
    if a.print_length:
        print(f"{plan_all(a.media)[1]:.2f}")
    else:
        build(a.media, a.font_dir, a.out, a.music)
