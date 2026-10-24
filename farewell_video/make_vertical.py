"""휴대폰용 세로 영상(1080×1920) 만들기 — make_video.py의 장면·자막·길이를 그대로 사용

화면 구성: 위쪽에 사진·동영상·애니메이션, 아래쪽에 큰 자막, 배경은 같은 장면을 흐리게 깐다.

사용법:
    python make_vertical.py --media <사진·영상 폴더> --font-dir <폰트 폴더> --music bgm.wav --out farewell_세로.mp4
"""
import argparse
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anim  # noqa: E402
import make_video as mv  # noqa: E402

from PIL import Image, ImageDraw, ImageFilter, ImageOps  # noqa: E402

VW, VH, FPS = 1080, 1920, 30
BOX_W, BOX_H = 1000, 1080      # 사진·영상이 들어가는 칸
BOX_CY = 690                   # 칸의 가운데 높이
CAP_CY = 1590                  # 자막 덩어리의 가운데 높이
CAP_SIZE = 70                  # 세로 영상 자막 크기 (모든 줄 같은 크기)
CAP_MAX_W = 960

# 애니메이션은 글씨가 있는 부분만 잘라 크게 보여 줌 (x, y, w, h)
ANIM_CROP = {"greenhouse": (0, 40, 1920, 1000), "scroll": (330, 100, 1560, 720), "fix": (330, 100, 1560, 720)}


def wrap(lines, fnt, max_w):
    """너무 긴 줄은 가운데 가까운 띄어쓰기에서 두 줄로 나눔."""
    out = []
    for ln in lines:
        if fnt.getlength(ln) <= max_w or " " not in ln:
            out.append(ln)
            continue
        spaces = [i for i, ch in enumerate(ln) if ch == " "]
        cut = min(spaces, key=lambda i: abs(i - len(ln) / 2))
        out += wrap([ln[:cut], ln[cut + 1:]], fnt, max_w)
    return out


def caption_png(path, lines, fd):
    img = Image.new("RGBA", (VW, VH), (0, 0, 0, 0))
    size = CAP_SIZE
    while True:
        f = mv.font(fd, "NanumMyeongjoEB.ttf", size)
        rows = wrap(lines, f, CAP_MAX_W)
        if max(f.getlength(r) for r in rows) <= CAP_MAX_W or size <= 52:
            break
        size -= 2
    lh = int(size * 1.6)
    y0 = CAP_CY - lh * (len(rows) - 1) / 2
    # 글씨 뒤 은은한 어두운 띠
    band = Image.new("RGBA", (VW, VH), (0, 0, 0, 0))
    top, bot = y0 - lh * 0.9, y0 + lh * (len(rows) - 1) + lh * 0.9
    ImageDraw.Draw(band).rounded_rectangle([30, top, VW - 30, bot], 36, fill=(0, 0, 0, 95))
    img.alpha_composite(band.filter(ImageFilter.GaussianBlur(14)))
    for k, r in enumerate(rows):
        mv.shadow_text(img, (VW // 2, int(y0 + k * lh)), r, f)
    img.save(path)


def blurred_cover(im, dim=0.45):
    bg = ImageOps.fit(im, (VW, VH), Image.LANCZOS).filter(ImageFilter.GaussianBlur(28))
    return Image.blend(bg, Image.new("RGB", (VW, VH), (0, 0, 0)), dim)


def photo_frame(im):
    bg = blurred_cover(im)
    fg = ImageOps.contain(im, (BOX_W, BOX_H), Image.LANCZOS)
    x, y = (VW - fg.width) // 2, int(BOX_CY - fg.height / 2)
    sh = Image.new("RGBA", (VW, VH), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle([x + 8, y + 12, x + fg.width + 8, y + fg.height + 12], fill=(0, 0, 0, 150))
    bg = bg.convert("RGBA")
    bg.alpha_composite(sh.filter(ImageFilter.GaussianBlur(14)))
    bg = bg.convert("RGB")
    bg.paste(fg, (x, y))
    return bg


def title_frame(path, src, lines, fd, outro=False):
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    base = ImageOps.fit(im, (VW, VH), Image.LANCZOS).filter(ImageFilter.GaussianBlur(10 if outro else 16))
    base = Image.blend(base, Image.new("RGB", (VW, VH), (20, 12, 30)), 0.5).convert("RGBA")
    d = ImageDraw.Draw(base)
    big, small = lines
    cy = VH // 2 - 120
    if outro:
        f = mv.font(fd, "NanumMyeongjoEB.ttf", 80)
        rows = wrap([big, small], f, 960)
        for k, r in enumerate(rows):
            mv.shadow_text(base, (VW // 2, cy - 60 + k * 120), r, f,
                           fill=(255, 255, 255, 255) if k == 0 else (255, 240, 225, 255))
        y = cy - 60 + (len(rows) - 1) * 120 + 110
        d.line([(VW // 2 - 200, y), (VW // 2 + 200, y)], fill=(255, 225, 235, 210), width=3)
        mv.shadow_text(base, (VW // 2, y + 80), mv.DATE_LINE, mv.font(fd, "NanumMyeongjoEB.ttf", 56),
                       fill=(245, 236, 248, 255))
        mv.shadow_text(base, (VW // 2, VH - 170), "♪ 배경음악", mv.font(fd, "NanumMyeongjoEB.ttf", 44),
                       fill=(240, 232, 245, 255))
        mv.shadow_text(base, (VW // 2, VH - 105), "10월에 만든 3박자 왈츠 곡", mv.font(fd, "NanumMyeongjoEB.ttf", 44),
                       fill=(240, 232, 245, 255))
    else:
        f_big = mv.font(fd, "NanumMyeongjoEB.ttf", 100)
        rows = wrap([big], f_big, 980)
        for k, r in enumerate(rows):
            mv.shadow_text(base, (VW // 2, cy - 140 + k * 140), r, f_big)
        y = cy - 140 + (len(rows) - 1) * 140 + 110
        d.line([(VW // 2 - 240, y), (VW // 2 + 240, y)], fill=(255, 225, 235, 210), width=3)
        f_sub = mv.font(fd, "NanumMyeongjoEB.ttf", 68)
        for k, r in enumerate(wrap([small], f_sub, 960)):
            mv.shadow_text(base, (VW // 2, y + 100 + k * 100), r, f_sub, fill=(255, 240, 225, 255))
        n_sub = len(wrap([small], f_sub, 960))
        mv.shadow_text(base, (VW // 2, y + 100 + n_sub * 100 + 30), mv.DATE_LINE,
                       mv.font(fd, "NanumMyeongjoEB.ttf", 56), fill=(245, 236, 248, 255))
    base.convert("RGB").save(path)


def moving_filter(crop=None):
    """동영상·애니메이션: 흐린 배경 + 위쪽 칸에 원본 크기 그대로."""
    pre = f"crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]}," if crop else ""
    return (f"[0:v]{pre}fps={FPS},split[a][b];"
            f"[a]scale=-2:{VH},crop={VW}:{VH},gblur=sigma=30,eq=brightness=-0.12[bg];"
            f"[b]scale={BOX_W + 80}:-2[fg];"
            f"[bg][fg]overlay=(W-w)/2:{BOX_CY}-h/2,format=rgba[l0]")


def build(media, fd, out, music):
    plans, total = mv.plan_all(media)
    tmp = tempfile.mkdtemp(prefix="farewell_v_")
    enc = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an"]
    segs = []
    for i, ((kind, src, caps, mode, opts), (dur, windows)) in enumerate(zip(mv.SCENES, plans)):
        seg = os.path.join(tmp, f"seg{i:02d}.mp4")
        src_path = os.path.join(media, src)
        if kind in ("title", "outro"):
            still = os.path.join(tmp, f"still{i}.png")
            title_frame(still, src_path, caps[0], fd, outro=(kind == "outro"))
            mv.run(["ffmpeg", "-y", "-loop", "1", "-i", still, "-vf", f"fps={FPS}", "-t", f"{dur:.2f}", *enc, seg])
        else:
            if kind == "photo":
                im = ImageOps.exif_transpose(Image.open(src_path)).convert("RGB")
                if "crop" in opts:
                    im = im.crop(opts["crop"])
                still = os.path.join(tmp, f"still{i}.png")
                photo_frame(im).save(still)
                inputs = ["-loop", "1", "-i", still]
                fc = [f"[0:v]fps={FPS},format=rgba[l0]"]
            else:
                if kind == "anim":
                    clip = os.path.join(tmp, f"anim{i}.mp4")
                    anim.render(src, dur, clip, fd)
                    inputs, fc = ["-i", clip], [moving_filter(ANIM_CROP[src])]
                else:
                    inputs, fc = ["-i", src_path], [moving_filter()]
            last, n_in = "l0", 1
            for k, (lines, (t0, t1)) in enumerate(zip(caps, windows)):
                cap = os.path.join(tmp, f"cap{i}_{k}.png")
                caption_png(cap, lines, fd)
                inputs += ["-loop", "1", "-t", f"{dur:.2f}", "-i", cap]
                fc.append(f"[{n_in}:v]format=rgba,fade=t=in:st={t0:.2f}:d={mv.FADE}:alpha=1,"
                          f"fade=t=out:st={t1 - mv.FADE:.2f}:d={mv.FADE}:alpha=1[c{k}]")
                fc.append(f"[{last}][c{k}]overlay=0:0[l{n_in}]")
                last, n_in = f"l{n_in}", n_in + 1
            fc.append(f"[{last}]format=yuv420p[v]")
            mv.run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", "[v]",
                    "-t", f"{dur:.2f}", *enc, seg])
        segs.append((seg, dur))
        print(f"  [{i + 1}/{len(mv.SCENES)}] {dur:5.1f}초  {' / '.join(caps[0])}")

    args, chain, off = [], "", 0.0
    for seg, _ in segs:
        args += ["-i", seg]
    prev = "0:v"
    for k in range(1, len(segs)):
        off += segs[k - 1][1] - mv.XF
        chain += f"[{prev}][{k}:v]xfade=transition=fade:duration={mv.XF}:offset={off:.2f}[x{k}];"
        prev = f"x{k}"
    chain += f"[{prev}]fade=t=in:st=0:d=1.2,fade=t=out:st={total - 2:.2f}:d=2[v]"
    amap = []
    if music:
        chain += ";" + mv.audio_chain(media, plans, total, len(segs), args, music)
        amap = ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    mv.run(["ffmpeg", "-y", *args, "-filter_complex", chain, "-map", "[v]", *amap,
            "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-tune", "film",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", out])
    print(f"완료: {out}  ({total:.1f}초)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--media", required=True)
    ap.add_argument("--font-dir", required=True)
    ap.add_argument("--out", default="farewell_세로.mp4")
    ap.add_argument("--music")
    a = ap.parse_args()
    build(a.media, a.font_dir, a.out, a.music)
