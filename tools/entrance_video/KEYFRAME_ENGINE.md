# ARKAON Keyframe Entrance Engine — first implementation

기존 전체 화면 확대/흔들림 방식 대신 **순서가 있는 정지 이미지 4~8장**을 사용해 8초 진입 영상을 생성하는 로컬 도구입니다.

## 입력
`frames/001.png`, `002.png`, `003.png`, `004.png` 등 순서대로 배치합니다. 모두 같은 눈·동일한 구도·1280×720 이상을 권장합니다.

권장 장면: (1) 어둠 속 눈 윤곽, (2) 홍채 활성화, (3) 반도체 회로 점등, (4) 각성 완료/브랜드 노출. **키프레임 이미지는 아직 자동 생성하지 않습니다.** 각 장면을 별도로 준비해야 합니다.

## 로컬 실행
```powershell
python tools/entrance_video/keyframe_engine.py --frames-dir "C:\\ARKAON\\frames" --output "arkaon-keyframes.mp4"
```
승인 문구: `ARKAON KEYFRAMES APPROVED`

## 현재 구현
- FFmpeg의 `xfade`로 장면 간 0.5초 디졸브
- 화면 전체 확대·흔들림 없음
- 1280×720 / 24fps / 8초 / H.264 MP4
- 로컬 대화형 승인 필수, 기존 출력 덮어쓰기 차단
- 외부 GPU 대여·원격 업로드·운영 배포 없음

## 다음 개선
원본 눈 이미지 기반 요소별 마스크(홍채/동공/회로/광원), 단계별 이미지 생성 및 일관성 검사, optical-flow/RIFE 보간, 실제 프레임 수·시각 QA, 원클릭 검토 브랜치 업로드를 추가해야 합니다. 지금의 디졸브는 **프레임 보간 또는 이미지 생성 AI가 아닙니다.**
