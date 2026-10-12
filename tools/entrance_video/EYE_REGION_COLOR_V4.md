# ARKAON v4 Color Layers

3차 엔진의 기존 홍채 픽셀 움직임을 보존하고, 생성된 PNG 위에 독립적인 색상/발광 레이어를 합성합니다. **실제 회로 자동 검출은 아직 없으며 방사형 회로 표현은 예시 효과입니다.**

## 로컬 실행

```powershell
python tools/entrance_video/eye_region_color_v4.py --frames-dir "C:\\ARKAON\\frames-eye-v3" --output-dir "C:\\ARKAON\\frames-eye-v4"
```

관리자 승인: `ARKAON COLOR LAYERS APPROVED`

```powershell
ffmpeg -framerate 24 -i "C:\\ARKAON\\frames-eye-v4\\%06d.png" -c:v libx264 -pix_fmt yuv420p -crf 19 -movflags +faststart "arkaon-eye-v4.mp4"
start .\\arkaon-eye-v4.mp4
```

색상 강도 조정 예: `--iris-alpha 80 --circuit-alpha 110 --outer-alpha 15 --glow-strength 0.4`.
홍채 위치 보정 예: `--center-x 0.52 --center-y 0.48 --iris-radius 0.13`.
원본 및 v3 프레임은 변경하지 않습니다. 기존 출력 폴더가 비어 있지 않으면 중단합니다.
