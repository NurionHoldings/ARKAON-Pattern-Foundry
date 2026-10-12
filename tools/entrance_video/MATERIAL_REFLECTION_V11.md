# ARKAON V11 — 재질별 이동 반사광

기존 V10의 수동 지정 영역 15개에 대해 표면 재질을 별도 지정합니다.

- 금속 링: 좁고 강한 하이라이트
- 눈꺼풀 코팅: 넓고 부드러운 반사
- AI 칩: 모서리와 밝은 면의 국소 반사
- 회로: 얇은 이동 하이라이트
- ARKAON 글자: 약한 광택

**물리적 재질 추론이나 실제 3D 레이트레이싱이 아닙니다.** 2D 영상에서 명암의 기울기와 재질별 반사 계수를 이용하는 근사 모델입니다. 홍채에는 직접 반사 마스크를 추가하지 않습니다.

## Windows PowerShell

```powershell
git fetch origin feat/material-aware-reflection-v11
git switch --track origin/feat/material-aware-reflection-v11
python -m pip install numpy opencv-python
python tools/entrance_video/material_reflection_v11.py --input "arkaon-eye-v10.mp4" --output "arkaon-eye-v11.mp4" --intensity 0.8
start .\\arkaon-eye-v11.mp4
```

V10 파일이 없으면 먼저 V10을 생성해야 합니다. 반사광을 더 자연스럽게 낮추려면 `--intensity 0.5`로 새 파일명에 출력하세요. 원본 영상은 덮어쓰지 않으며, 입력 영상의 오디오는 보존하지 않습니다. 효과의 정렬과 자연스러움은 로컬에서 재생하여 검증해야 합니다.
