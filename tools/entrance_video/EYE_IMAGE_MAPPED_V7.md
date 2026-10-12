# ARKAON V7 — 원본 이미지 기반 영역별 발광

사용자가 제공한 1536×1024 포스터에서 확인한 눈꺼풀 상단·하단, 좌우 반도체 부품, 회로 일부를 **수동 추정 좌표**로 지정했습니다. 홍채 움직임은 V5 프레임을 입력받아 보존합니다. 눈꺼풀 청색→보라→금백색, AI 칩과 회로의 시간차 점등을 구현합니다. 이미지 하단 ARKAON 텍스트는 효과 영역에서 제외합니다.

자동 세그멘테이션은 아닙니다. 사용자 원본과 다른 이미지에는 사용하지 마세요. 실사 자연스러움과 정렬은 PC에서 영상 확인이 필요합니다.

```powershell
git fetch origin feat/eye-image-mapped-v7
git switch --track origin/feat/eye-image-mapped-v7
python tools/entrance_video/eye_image_mapped_v7.py --frames-dir "C:\\ARKAON\\frames-eye-v5" --output-dir "C:\\ARKAON\\frames-eye-v7" --intensity 0.75
```

승인: `ARKAON V7 IMAGE MAPPED APPROVED`

```powershell
ffmpeg -framerate 24 -i "C:\\ARKAON\\frames-eye-v7\\%06d.png" -c:v libx264 -pix_fmt yuv420p -crf 19 -movflags +faststart "arkaon-eye-v7.mp4"
start .\\arkaon-eye-v7.mp4
```

V5 프레임이 없으면 V5 생성부터 진행하세요. 더 은은한 빛은 `--intensity 0.45`로 새 출력 폴더에 생성합니다.
