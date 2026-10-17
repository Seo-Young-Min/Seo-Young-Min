"""빅데이터 조사 과정 수료 기념 · 동료 인사 영상 생성기

사용법:
    python make_video.py --media <사진·영상 폴더> --font-dir <폰트 폴더> --out farewell.mp4
    python make_video.py ... --music "시월의 어느 멋진 날에.mp3"   # 배경음 함께 합성

필요: ffmpeg, Pillow
"""
import argparse
import os
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

W, H, FPS = 1920, 1080, 30
XF = 1.0  # 장면 전환(크로스페이드) 길이(초)

# (종류, 파일, 길이, 자막 큰글씨, 자막 작은글씨, 배치방식)
#   배치방식: cover = 16:9로 채움(켄번스), fit = 원본 전체 보이기(시비 등 글자 잘림 방지)
SCENES = [
    ("title", "783c445a-image.jpg", 6.5, "시월의 어느 멋진 날에", "빅데이터 조사 과정 8개월을 마치며", None),
    ("photo", "54cecf94-image.jpg", 6.0, "8개월 동안 빅데이터 조사 과정을 배우며", "", "cover"),
    ("video", "2e764b03-20261012_115501.mp4", 9.4, "데이터의 중요성과", "활용 가능성을 깨달았습니다", None),
    ("photo", "83520179-image.jpg", 6.5, "2026 데이터·인공지능 현장 활용 경진대회", "최우수상의 기쁨", "fit"),
    ("photo", "932d9a62-image.jpg", 7.0, "함께 응원해 준 동료들이 있었기에", "가능했던 순간", "fit"),
    ("photo", "f030f540-image.jpg", 6.5, "데이터 기반 스마트농업 확산을 위한 아이디어", "그 결실을 함께 나눕니다", "fit"),
    ("photo", "80f093a6-image.jpg", 6.0, "한 줄의 숫자가 현장의 이야기가 되고", "", "cover"),
    ("photo", "993cc237-image.jpg", 6.0, "그 이야기가 농업의 내일을 그려갑니다", "", "cover"),
    ("photo", "7a1fce7a-image.jpg", 7.0, "강물이 바다로 흘러가듯", "배움은 또 다른 길로 이어집니다", "fit"),
    ("photo", "1a1db0fc-image.jpg", 7.0, "함께 고민하고 함께 웃었던 시간들", "", "fit"),
    ("photo", "0f24662b-image.jpg", 6.0, "시월의 햇살 아래", "8개월의 시간이 노랗게 물들었습니다", "cover"),
    ("video", "d3214c72-20261012_115648.mp4", 8.9, "함께해 주신 모든 분께", "진심으로 감사드립니다", None),
    ("outro", "f1eaf656-image.jpg", 8.0, "고맙습니다", "각자의 자리에서 데이터로 빛나시길 바랍니다", None),
]
DATE_LINE = "2026. 10. 12."


def font(d, name, size):
    return ImageFont.truetype(os.path.join(d, name), size)


def cover(im, w, h):
    return ImageOps.fit(im, (w, h), Image.LANCZOS, centering=(0.5, 0.5))


def fit_on_blur(im, w, h):
    """원본 전체를 보이게 하고 남는 좌우는 같은 사진 흐림 배경으로 채움."""
    bg = cover(im, w, h).filter(ImageFilter.GaussianBlur(40))
    bg = Image.blend(bg, Image.new("RGB", (w, h), (0, 0, 0)), 0.35)
    # 하단 자막 자리를 비워 두도록 위쪽 78% 영역에 배치
    fg = ImageOps.contain(im, (w, int(h * 0.78)), Image.LANCZOS)
    bg.paste(fg, ((w - fg.width) // 2, int(h * 0.03)))
    return bg


def shadow_text(draw_img, xy, text, fnt, fill=(255, 255, 255, 255), anchor="mm", blur=6):
    layer = Image.new("RGBA", draw_img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((xy[0] + 3, xy[1] + 4), text, font=fnt, fill=(0, 0, 0, 200), anchor=anchor)
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    draw_img.alpha_composite(layer)
    ImageDraw.Draw(draw_img).text(xy, text, font=fnt, fill=fill, anchor=anchor)


def caption_png(path, big, small, fd):
    """하단 자막(그라데이션 + 명조체)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    grad = Image.new("L", (1, 380))
    for y in range(380):
        grad.putpixel((0, y), int(170 * (y / 379) ** 1.6))
    img.paste((0, 0, 0, 255), (0, H - 380, W, H), grad.resize((W, 380)))
    if small:
        shadow_text(img, (W // 2, H - 185), big, font(fd, "NanumMyeongjoEB.ttf", 64))
        shadow_text(img, (W // 2, H - 100), small, font(fd, "NanumMyeongjo.ttf", 48), fill=(255, 244, 220, 255))
    else:
        shadow_text(img, (W // 2, H - 130), big, font(fd, "NanumMyeongjoEB.ttf", 64))
    img.save(path)


def title_frame(path, src, big, small, fd, outro=False):
    base = cover(ImageOps.exif_transpose(Image.open(src)).convert("RGB"), W, H)
    base = base.filter(ImageFilter.GaussianBlur(6 if outro else 12))
    base = Image.blend(base, Image.new("RGB", (W, H), (20, 12, 30)), 0.45).convert("RGBA")
    d = ImageDraw.Draw(base)
    cy = H // 2 - 40
    shadow_text(base, (W // 2, cy - 30), big, font(fd, "NanumMyeongjoEB.ttf", 120 if outro else 112))
    d.line([(W // 2 - 260, cy + 60), (W // 2 + 260, cy + 60)], fill=(255, 225, 235, 200), width=2)
    shadow_text(base, (W // 2, cy + 130), small, font(fd, "NanumMyeongjo.ttf", 54), fill=(255, 240, 225, 255))
    shadow_text(base, (W // 2, cy + 230), DATE_LINE + ("  수료를 기념하며" if outro else ""),
                font(fd, "NanumMyeongjo.ttf", 38), fill=(235, 225, 240, 255))
    base.convert("RGB").save(path, quality=95)


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def build(media, fd, out, music):
    tmp = tempfile.mkdtemp(prefix="farewell_")
    segs = []
    enc = ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an"]
    for i, (kind, src, dur, big, small, mode) in enumerate(SCENES):
        seg = os.path.join(tmp, f"seg{i:02d}.mp4")
        frames = int(dur * FPS)
        src_path = os.path.join(media, src)
        if kind in ("title", "outro"):
            still = os.path.join(tmp, f"still{i}.jpg")
            title_frame(still, src_path, big, small, fd, outro=(kind == "outro"))
            # 아주 느린 줌인
            vf = (f"scale=3840:2160,zoompan=z='1+0.04*on/{frames}':x='iw/2-(iw/zoom/2)':"
                  f"y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS}")
            run(["ffmpeg", "-y", "-loop", "1", "-i", still, "-vf", vf, "-t", str(dur), *enc, seg])
        else:
            cap = os.path.join(tmp, f"cap{i}.png")
            caption_png(cap, big, small, fd)
            fade = f"fade=t=in:st=0.8:d=0.9:alpha=1,fade=t=out:st={dur - 1.4:.2f}:d=0.6:alpha=1"
            if kind == "photo":
                im = ImageOps.exif_transpose(Image.open(src_path)).convert("RGB")
                big_im = (cover(im, 3840, 2160) if mode == "cover" else fit_on_blur(im, 3840, 2160))
                still = os.path.join(tmp, f"still{i}.jpg")
                big_im.save(still, quality=95)
                # 켄번스: cover는 줌인 + 살짝 이동, fit은 아주 약한 줌(글자 보존)
                zmax = 0.10 if mode == "cover" else 0.03
                drift = "+(on/%d)*iw*0.02" % frames if i % 2 else "-(on/%d)*iw*0.02" % frames
                vf_bg = (f"zoompan=z='1+{zmax}*on/{frames}':x='iw/2-(iw/zoom/2){drift if mode == 'cover' else ''}':"
                         f"y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS}")
                inputs = ["-loop", "1", "-i", still]
            else:
                vf_bg = f"scale={W}:{H},fps={FPS}"
                inputs = ["-i", src_path]
            fc = f"[0:v]{vf_bg}[bg];[1:v]format=rgba,{fade}[cap];[bg][cap]overlay=0:0:format=auto,format=yuv420p[v]"
            run(["ffmpeg", "-y", *inputs, "-loop", "1", "-t", str(dur), "-i", cap,
                 "-filter_complex", fc, "-map", "[v]", "-t", str(dur), *enc, seg])
        segs.append((seg, dur))
        print(f"  [{i + 1}/{len(SCENES)}] {big}")

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
    total = sum(d for _, d in segs) - XF * (len(segs) - 1)
    chain += f"[{prev}]fade=t=in:st=0:d=1.2,fade=t=out:st={total - 2:.2f}:d=2[v]"

    if music:
        args += ["-i", music]
        a = len(segs)
        chain += f";[{a}:a]atrim=0:{total:.2f},afade=t=in:d=2,afade=t=out:st={total - 4:.2f}:d=4[a]"
        amap = ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    else:
        amap = []
    run(["ffmpeg", "-y", *args, "-filter_complex", chain, "-map", "[v]", *amap,
         "-c:v", "libx264", "-preset", "slow", "-crf", "23", "-maxrate", "9M", "-bufsize", "18M", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", out])
    print(f"완료: {out}  ({total:.1f}초)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--media", required=True)
    ap.add_argument("--font-dir", required=True)
    ap.add_argument("--out", default="farewell.mp4")
    ap.add_argument("--music", help="배경음 파일(mp3 등). 직접 구매·보유한 음원 사용")
    a = ap.parse_args()
    build(a.media, a.font_dir, a.out, a.music)
