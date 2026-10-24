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
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anim  # noqa: E402

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

W, H, FPS = 1920, 1080, 30
XF = 1.0  # 장면 전환(크로스페이드) 길이(초)
DATE_LINE = "2026. 10. 30."

# 자막 읽기 시간: 보통 사람이 편하게 읽는 속도(초당 약 4.5음절) 기준
SEC_PER_SYLLABLE = 0.22
READ_BASE = 1.3
LEAD, TAIL, FADE, GAP = 1.0, 1.0, 0.5, 0.35

# 장면: (종류, 파일, 자막 목록, 배치방식, 옵션)
#   종류: title / photo / video / anim(anim.py 애니메이션) / outro
#   자막 하나 = 한 화면에 함께 보이는 줄들
#   배치방식: cover = 16:9로 채움, fit = 사진 전체 보이기(crop 옵션으로 일부만), 사진은 모두 정지 화면(원본 그대로)
SCENES = [
    ("title", "783c445a-image.jpg", [["빅데이터 조사 과정 8개월의 여정", "시월의 어느 멋진 날에"]], None, {"dur": 7.0}),
    ("photo", "54cecf94-image.jpg", [["처음에는 낯설었던 데이터,", "하나하나 살피고 확인하며"]], "cover", {}),
    ("video", "2e764b03-20261012_115501.mp4", [["우리의 생소한 빅데이터 조사가", "시작되었습니다."]], None, {}),
    ("anim", "greenhouse", [["데이터의 중요성과", "활용 가능성을 알게 되었습니다."]], None, {"min": 9.0}),
    ("anim", "scroll", [["숫자 하나에도 의미가 있었고,"]], None, {"min": 9.0}),
    ("anim", "fix", [["작은 오류 하나를 바로잡는 일에도", "정성과 책임이 필요했습니다."]], None, {"min": 9.5}),
    ("photo", "7a1fce7a-image.jpg", [["8개월의 시간,", "때로는 힘들고 때로는 보람 있었지만"]], "fit",
     {"crop": (1120, 140, 2980, 2790), "min": 10.0}),
    ("video", "65fde172-1000025668.mp4", [["2026 데이터·인공지능 현장 활용 경진대회"],
                                          ["동료들의 뜨거운 응원 속에서"]], None,
     {"audio": True}),  # 경진대회 응원 영상: 현장 함성을 살리고 배경음악은 잠시 낮춤
    ("photo", "932d9a62-image.jpg", [["함께했기에", "여기까지 올 수 있었습니다."]], "fit", {}),
    ("photo", "83520179-image.jpg", [["우리가 조사하고 검수한 작은 기록들이", "우리 농업의 더 나은 내일을 만들고,"]], "fit", {}),
    ("photo", "f030f540-image.jpg", [["미래를 여는 소중한 밑거름이", "되기를 바랍니다."]], "fit", {}),
    ("photo", "1a1db0fc-image.jpg", [["이제 하나의 여정은 마무리되지만,", "배움은 끝나지 않았습니다."]], "fit",
     {"crop": (880, 610, 2920, 2770), "min": 10.0}),
    ("photo", "0f24662b-image.jpg", [["함께한 모든 분께 감사드리며,", "8개월의 소중한 추억을 가슴에 담고"]], "cover", {}),
    ("video", "d3214c72-20261012_115648.mp4", [["또 다른 내일을 향해 나아갑니다."]], None, {}),
    ("outro", "f1eaf656-image.jpg", [["함께한 시간에 감사하며,", "우리의 도전은 계속됩니다."]], None, {"dur": 9.0}),
]
MUSIC_CREDIT = "♪ 배경음악: 10월에 만든 3박자 왈츠 곡"

CAP_SIZE = 70          # 하단 자막: 모든 줄 같은 크기·굵기로 균형 (세로 영상과 같은 크기)


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
    fg = ImageOps.contain(im, (w, int(h * 0.73)), Image.LANCZOS)
    bg.paste(fg, ((w - fg.width) // 2, int(h * 0.025)))
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


def caption_png(path, lines, fd):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    f, size = fitted_font(fd, lines, CAP_SIZE, W - 220)
    lh = int(size * 1.55)
    y_last = H - 80
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
        shadow_text(base, (W // 2, cy + 245), DATE_LINE, font(fd, "NanumMyeongjoEB.ttf", 56),
                    fill=(245, 236, 248, 255))
        shadow_text(base, (W // 2, H - 80), MUSIC_CREDIT, font(fd, "NanumMyeongjoEB.ttf", 44),
                    fill=(240, 232, 245, 255))
    else:
        f_big, _ = fitted_font(fd, [big], 104, W - 200)
        shadow_text(base, (W // 2, cy - 40), big, f_big)
        d.line([(W // 2 - 300, cy + 55), (W // 2 + 300, cy + 55)], fill=(255, 225, 235, 210), width=3)
        shadow_text(base, (W // 2, cy + 140), small, font(fd, "NanumMyeongjoEB.ttf", 68),
                    fill=(255, 240, 225, 255))
        shadow_text(base, (W // 2, cy + 245), DATE_LINE, font(fd, "NanumMyeongjoEB.ttf", 56),
                    fill=(245, 236, 248, 255))
    base.convert("RGB").save(path)


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


def audio_chain(media, plans, total, n_video_inputs, args, music):
    """배경음악 + 현장음을 살릴 장면(옵션 audio)의 소리. 그 장면 동안 배경음악은 25%로 낮춤."""
    starts, t = [], 0.0
    for dur, _ in plans:
        starts.append(t)
        t += dur - XF
    args += ["-i", music]
    m = n_video_inputs
    duck, mix, n = [], [], 0
    for (kind, src, caps, mode, opts), (dur, _), st in zip(SCENES, plans, starts):
        if not opts.get("audio"):
            continue
        s, e = st + 0.5, st + dur - 0.5
        duck.append(f"0.75*clip((t-{s:.2f})/1.2,0,1)*clip(({e:.2f}-t)/1.2,0,1)")
        args += ["-i", os.path.join(media, src)]
        n += 1
        ms = int(st * 1000)
        mix.append(f"[{m + n}:a]atrim=0:{dur - 0.1:.2f},asetpts=PTS-STARTPTS,afade=t=in:d=0.8,"
                   f"afade=t=out:st={dur - 1.6:.2f}:d=1.5,volume=1.4,adelay={ms}|{ms}[s{n}]")
    vol = f"volume='1-({'+'.join(duck)})':eval=frame," if duck else ""
    chain = (f"[{m}:a]atrim=0:{total:.2f},asetpts=PTS-STARTPTS,{vol}afade=t=in:d=1.5,"
             f"afade=t=out:st={total - 4:.2f}:d=4[mus]")
    if mix:
        chain += ";" + ";".join(mix)
        chain += ";[mus]" + "".join(f"[s{k}]" for k in range(1, n + 1))
        chain += f"amix=inputs={n + 1}:normalize=0:duration=first,alimiter=limit=0.95[a]"
    else:
        chain += ";[mus]anull[a]"
    return chain


def build(media, fd, out, music):
    plans, total = plan_all(media)
    tmp = tempfile.mkdtemp(prefix="farewell_")
    grad = os.path.join(tmp, "grad.png")
    gradient_png(grad)
    segs = []
    enc = ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an"]
    for i, ((kind, src, caps, mode, opts), (dur, windows)) in enumerate(zip(SCENES, plans)):
        seg = os.path.join(tmp, f"seg{i:02d}.mp4")
        src_path = os.path.join(media, src)
        if kind in ("title", "outro"):
            still = os.path.join(tmp, f"still{i}.png")
            title_frame(still, src_path, caps[0], fd, outro=(kind == "outro"))
            run(["ffmpeg", "-y", "-loop", "1", "-i", still, "-vf", f"fps={FPS}", "-t", f"{dur:.2f}", *enc, seg])
        else:
            if kind == "photo":
                im = ImageOps.exif_transpose(Image.open(src_path)).convert("RGB")
                if "crop" in opts:
                    im = im.crop(opts["crop"])
                still = os.path.join(tmp, f"still{i}.png")
                (cover(im, W, H) if mode == "cover" else fit_on_blur(im, W, H)).save(still)
                vf_bg = f"fps={FPS}"  # 원본 그대로 정지 화면 (확대·이동하면 잔무늬가 반짝거림)
                inputs = ["-loop", "1", "-i", still]
            elif kind == "anim":
                clip = os.path.join(tmp, f"anim{i}.mp4")
                anim.render(src, dur, clip, fd)
                vf_bg = f"fps={FPS}"
                inputs = ["-i", clip]
            else:
                vf_bg = f"fps={FPS}"  # 동영상은 원본 그대로
                inputs = ["-i", src_path]

            fc = [f"[0:v]{vf_bg},format=rgba[l0]"]
            # 하단 그라데이션은 장면 내내 유지 (자막 가독성)
            inputs += ["-loop", "1", "-t", f"{dur:.2f}", "-i", grad]
            fc.append("[1:v]format=rgba,fade=t=in:st=0.4:d=0.8:alpha=1,"
                      f"fade=t=out:st={dur - 1.0:.2f}:d=0.6:alpha=1[g]")
            fc.append("[l0][g]overlay=0:0[l1]")
            last, n_in = "l1", 2
            for k, (lines, (t0, t1)) in enumerate(zip(caps, windows)):
                cap = os.path.join(tmp, f"cap{i}_{k}.png")
                caption_png(cap, lines, fd)
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
        chain += ";" + audio_chain(media, plans, total, len(segs), args, music)
        amap = ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    run(["ffmpeg", "-y", *args, "-filter_complex", chain, "-map", "[v]", *amap,
         "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-tune", "film",
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
