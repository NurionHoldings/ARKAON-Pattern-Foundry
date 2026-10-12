# ARKAON 진입 영상 — 로컬 관리자 승인 제작·업로드

이 패키지는 누리온홀딩스 Windows PC에서 **관리자가 직접 승인한 경우에만** 한 번 실행하는 도구입니다. 실행 결과를 검토 브랜치에 업로드할 수 있으며, **운영 사이트 배포는 별도 PR 승인/병합**을 거칩니다.

## 사전 준비
1. 승인된 인간 홍채 + AI 회로 원본 이미지를 로컬 PC에 저장합니다. 이미지 원본은 GitHub 저장소에 자동으로 존재하지 않습니다.
2. Windows에서 Python 3.10 이상과 FFmpeg를 설치하고 `ffmpeg -version`을 확인합니다.
3. GitHub에 영상 업로드용 별도 **검토 브랜치**를 생성합니다. main 직접 업로드는 스크립트에서 거부합니다.
4. 업로드 시에는 최소 범위의 GitHub 토큰(대상 저장소 Contents: Read and write)을 환경변수 `ARKAON_GITHUB_TOKEN`으로 설정합니다. 토큰을 코드나 채팅에 붙이지 않습니다.

## 로컬에서 1회 제작
PowerShell에서 저장소 루트로 이동한 뒤:

```powershell
python tools/entrance_video/local_render_upload.py --image "C:\\ARKAON\\approved-eye.png" --output "arkaon-awakening.mp4"
```

관리자는 `ARKAON LOCAL RENDER APPROVED`를 직접 입력해야 제작이 시작됩니다. 관리자 본인 확인은 **로컬 물리적 확인에 의존**하며, 중앙 서버 인증을 대체하지 않습니다.

## 제작과 검토 브랜치 업로드를 함께 진행
```powershell
python tools/entrance_video/local_render_upload.py --image "C:\\ARKAON\\approved-eye.png" --output "arkaon-awakening.mp4" --upload --branch "feat/local-approved-entrance-video-upload"
```

영상 제작 승인과 업로드 승인은 별도입니다. 업로드할 때는 `ARKAON UPLOAD APPROVED`를 추가로 입력해야 합니다. 원격에 같은 파일이 있으면 자동 덮어쓰지 않습니다.

## 구현 범위와 한계
- FFmpeg로 8초 / 1280×720 / 24fps / 무음 / H.264 MP4 제작
- 승인된 원본 이미지에 부드러운 확대·축소와 밝기·채도 보정을 적용하는 **영상 합성**입니다. 홍채의 개별 움직임, 반도체 점등, 입자 연출을 별도 AI 모델로 생성하는 것은 아닙니다.
- GPU 모델 추론을 요구하지 않으므로 RTX 2080 SUPER를 필수 사용하지 않습니다. FFmpeg의 기본 인코딩은 CPU이며, GPU 가속은 향후 선택적으로 도입할 수 있습니다.
- GitHub API에 승인된 영상 파일을 업로드하는 기능 포함. 20 MiB 초과 파일은 거부합니다.
- 인터넷에 로컬 PC 포트를 열거나 상시 작업자를 실행하지 않습니다.
- 웹사이트 자동 반영, 영상 품질 검사, 진입 화면 영상 플레이어 연결, 관리자 계정 인증은 **아직 구현되지 않았습니다**.
- GitHub에 업로드한 영상은 PR 병합 전에는 운영 사이트에 반영되지 않습니다.

## 배포 전 검증
모바일 재생, 자동재생 정책(음소거/playsinline), 정지 이미지 대체, 모션 감소, 영상 용량, 저작권, 브라우저 검증 후 관리자 최종 승인 필요.
