# ARKAON V10 — 영역별 점진적 발광색 변화

9차 MP4에 별도 합성 레이어를 적용합니다. 금속 링 2개, 눈꺼풀 2개, AI 칩 8개, 좌우 회로 2개, ARKAON 글자 1개 등 총 15개 영역의 색상을 서로 다른 위상과 속도로 바꿉니다. 기존 원본의 명암과 질감은 최대한 유지합니다.

## Windows PowerShell

```powershell
python -m pip install opencv-python numpy
python tools/entrance_video/gradual_region_color_v10.py --input "arkaon-eye-v9.mp4" --output "arkaon-eye-v10.mp4" --intensity 0.9
start .\\arkaon-eye-v10.mp4
```

입력은 승인된 ARKAON 포스터 비율(3:2)의 MP4여야 합니다. 기존 파일 덮어쓰기를 거부합니다. 강도를 낮추려면 `--intensity 0.5`를 사용하고 다른 출력 파일명을 지정하세요.

**제한:** 마스크는 원본 이미지에서 수동으로 추정한 위치입니다. 자동 AI 부품 인식은 아닙니다. 하단 글자 마스크도 정밀 글리프 마스크가 아닌 사각 윤곽으로, 주변 밝은 부분에 약한 색 변화가 생길 수 있습니다. 실제 렌더링의 시각적 검수가 필요합니다. 오디오 트랙은 보존하지 않습니다.
