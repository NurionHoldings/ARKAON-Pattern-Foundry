# ARKAON V6 — 눈 전체 점화·확산·호흡 발광

5차 프레임을 변경하지 않고 별도 디렉터리에 6차 프레임을 생성합니다. 홍채 중심에서 눈 전체로 빛이 퍼지고, 호흡하듯 밝기가 변화하며, 마지막에 잔광이 남습니다. 원본 텍스처를 보존하도록 약한 스크린 합성과 흐린 발광을 사용합니다.

**현재 눈 영역은 자동 검출이 아니라 타원형 마스크입니다.** 원본 이미지에 맞게 좌표·가로세로 크기를 조정해야 합니다.

## PowerShell

```powershell
git fetch origin feat/whole-eye-glow-v6
git switch --track origin/feat/whole-eye-glow-v6
python tools/entrance_video/whole_eye_glow_v6.py --frames-dir "C:\\ARKAON\\frames-eye-v5" --output-dir "C:\\ARKAON\\frames-eye-v6"
```

승인: `ARKAON WHOLE EYE GLOW APPROVED`

```powershell
ffmpeg -framerate 24 -i "C:\\ARKAON\\frames-eye-v6\\%06d.png" -c:v libx264 -pix_fmt yuv420p -crf 19 -movflags +faststart "arkaon-eye-v6.mp4"
start .\\arkaon-eye-v6.mp4
```

눈 영역 조정 예: `--center-x 0.5 --center-y 0.5 --eye-width 0.54 --eye-height 0.32 --intensity 0.8`.

실사 느낌이 약하면 `--intensity 0.5`로 낮춰 새 출력 폴더에 생성합니다. 기존 출력 디렉터리는 덮어쓰지 않습니다.

실제 눈 윤곽 자동 마스크, 조명 반사에 따른 광학적 재합성, 회로 자동 검출은 후속 개발 항목입니다. 사용자 로컬 PC 실행 검증과 운영 배포는 별도 단계입니다.
