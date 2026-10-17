# 시월의 어느 멋진 날에 — 빅데이터 조사 과정 8개월의 여정

- 1920×1080 / 30fps / 약 1분 55초, 13개 장면, 장면 사이 1초 크로스페이드
- 자막 서체: 나눔명조 ExtraBold (SIL OFL), 모든 줄 같은 크기로 균형
- 자막 길이는 초당 약 4.5음절(보통 사람이 편하게 읽는 속도) 기준으로 장면 길이를 자동 계산
- 시비 「강 2」·「광장」은 글씨 부분을 화면 높이 가득 확대하고, 자막은 오른쪽에 배치
- 배경음악: `make_music.py`로 직접 작곡·합성한 G장조 3/4박 피아노 왈츠(현악 패드 포함) — 저작권 걱정 없음

## 만들기

```bash
L=$(python make_video.py --media <사진·영상 폴더> --print-length)   # 영상 길이(초)
python make_music.py --seconds $L --out bgm.wav                     # 길이에 맞춘 배경음악
python make_video.py --media <사진·영상 폴더> --font-dir <폰트 폴더> --music bgm.wav --out farewell.mp4
```

다른 음원을 쓰려면 `--music`에 mp3 등을 주면 됩니다. 영상 길이에 맞춰 잘리고 끝 4초는 페이드아웃됩니다.
자막 문구·순서는 `make_video.py`의 `SCENES` 목록에서 고칩니다.
