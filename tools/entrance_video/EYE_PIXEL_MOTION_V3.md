# ARKAON v3 — 눈동자 픽셀 변형 엔진

2차 엔진의 문제: 원본 이미지 위에 회로/동공 모양을 덧그리기만 해 실제 눈동자 텍스처는 움직이지 않았음.

3차 개선: 이미지 중심의 **원본 픽셀을 국소적으로 변형**하여 동공 수축/확장과 미세한 시선 이동을 구현. 외부 배경은 고정하고 홍채 주변만 마스크 합성. 프레임별 차이 수치를 `motion-report.json`으로 저장.

## 사용
현재 브랜치를 받아온 뒤 일반 PowerShell에서:

```powershell
python tools/entrance_video/eye_pixel_motion_v3.py --image "C:\\ARKAON\\approved-eye.png" --frames-dir "C:\\ARKAON\\frames-eye-v3"
```
승인 문구 `ARKAON EYE PIXEL MOTION APPROVED`

```powershell
ffmpeg -framerate 24 -i "C:\\ARKAON\\frames-eye-v3\\%06d.png" -c:v libx264 -pix_fmt yuv420p -crf 19 -movflags +faststart "arkaon-eye-v3.mp4"
start .\\arkaon-eye-v3.mp4
```

## 정렬
기본 홍채 중심은 이미지 정중앙(50%,50%), 홍채 반경은 이미지 짧은 변의 12%. 원본 이미지가 다르면 `--center-x 0.52 --center-y 0.48 --iris-radius 0.15`와 같이 조절. 숫자는 이미지에 맞춰 육안 확인 후 변경.

## 한계
- 자동 홍채/동공 탐지는 아직 없음. 사용자 이미지에 맞춰 수동 좌표 교정 필요.
- 픽셀 워프는 실제 해부학적 눈꺼풀 애니메이션이나 AI 생성 프레임 보간이 아님.
- 영상의 자연스러움은 PC에서 시각 검증 필요. 단순 픽셀 변화 통계는 품질 보증이 아님.
- 유료 GPU, 자동 학습, 외부 API 호출, GitHub 업로드/운영 배포 없음.
- 출력 디렉터리가 비어 있지 않으면 덮어쓰지 않고 중단.
