# ARKAON V5 — 홍채 움직임 + 실회로 좌표 조명 + 실사 질감 보존

v5는 v3의 **원본 픽셀 변형**을 유지하고 v4의 임의 방사형 회로선을 제거합니다. 회로가 원본 어디에 있는지 검수된 좌표 JSON을 제공할 때만 해당 경로를 따라 점등합니다. 자동 객체 탐지나 AI 모델 학습은 **아직 구현되지 않았습니다**.

## 로컬 실행 (Windows PowerShell)

```powershell
git fetch origin feat/eye-semantic-motion-v5
git switch --track origin/feat/eye-semantic-motion-v5
python tools/entrance_video/eye_semantic_motion_v5.py --image "C:\\ARKAON\\approved-eye.png" --output-dir "C:\\ARKAON\\frames-eye-v5"
```
관리자 승인: `ARKAON V5 LOCAL RENDER APPROVED`

```powershell
ffmpeg -framerate 24 -i "C:\\ARKAON\\frames-eye-v5\\%06d.png" -c:v libx264 -pix_fmt yuv420p -crf 19 -movflags +faststart "arkaon-eye-v5.mp4"
start .\\arkaon-eye-v5.mp4
```

## 실제 회로 경로 입력

원본 이미지를 육안으로 확인한 뒤 0..1 비율 좌표로 회로 중심선을 표시합니다. `circuit-map.json` 예시:

```json
{"paths":[[[0.62,0.40],[0.68,0.36],[0.75,0.35]],[[0.36,0.60],[0.29,0.64],[0.23,0.70]]]}
```

위 숫자는 **실제 원본 분석 결과가 아닌 형식 예시**입니다. 실사 정렬을 위해 원본 이미지에 맞는 좌표가 필요합니다.

```powershell
python tools/entrance_video/eye_semantic_motion_v5.py --image "C:\\ARKAON\\approved-eye.png" --output-dir "C:\\ARKAON\\frames-eye-v5-mapped" --circuit-map "C:\\ARKAON\\circuit-map.json"
```

원본 홍채 중심이 정중앙이 아니면 `--center-x`, `--center-y`, `--iris-radius`를 수정합니다. `--circuit-opacity 70`으로 발광을 줄일 수 있습니다. 입력 이미지는 변경하지 않고 새 프레임 디렉터리에만 출력합니다.

## 검증 및 한계

- `quality-report.json`은 프레임별 차이 수치 및 실제 적용된 회로 경로 개수를 기록합니다. 영상의 자연스러움은 시각 검증이 필요합니다.
- 회로 좌표를 제공하지 않으면 회로 조명은 **꺼집니다**. 임의 위치를 실제 회로로 오인하지 않도록 하기 위함입니다.
- 자동 영역 분리, AI 프레임 생성, 학습, GPU 대여, GitHub 업로드, 운영 배포는 포함하지 않습니다.
