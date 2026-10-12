# ARKAON Frame Motion Engine v1 / 확장 로드맵

## 초기 엔진 (구현)
- 한 장의 승인된 원본 이미지에 **고정된 좌표**로 동공/홍채 광원/회로 점등 레이어를 합성
- 초당 24장 × 8초 = 192장 PNG 프레임 개별 생성
- 화면 전체 카메라 이동·줌·진동 제거
- 관리자 대화형 승인 필수, 기존 프레임 덮어쓰기 차단, 외부 호출 없음
- Pillow 필요: `python -m pip install Pillow`
- 실행: `python tools/entrance_video/frame_motion_engine.py --image "C:\\ARKAON\\approved-eye.png" --frames-dir "C:\\ARKAON\\frames-motion"`
- 영상 연결: `ffmpeg -framerate 24 -i "C:\\ARKAON\\frames-motion\\%06d.png" -c:v libx264 -pix_fmt yuv420p -crf 20 -movflags +faststart arkaon-motion.mp4`

**한계:** 동공·홍채 위치를 원본에서 자동 검출하지 않습니다. 중심좌표 기반의 예술적 오버레이이므로 이미지에 따라 정렬이 틀릴 수 있습니다. 사용자가 육안으로 검수해야 합니다. 실제 동공 형태를 변형하는 AI 영상은 아닙니다.

## 확장 엔진 (설계, 미구현)
1. 이미지 분석: 원본 눈의 홍채/동공/눈꺼풀/회로 마스크 수동 교정 UI + 세그멘테이션
2. 타임라인: 동공 수축/확장, 홍채 질감, 회로 점등, 광원 및 입자에 각각 독립 키프레임
3. 프레임 보간: OpenCV optical flow / RIFE를 **옵션형**으로 시험하고 실패 시 기본 엔진으로 폴백
4. GPU: 로컬 PC는 매 작업 관리자 승인, 외부 GPU는 별도 제공자 승인·최대 비용·영수증·사용량 제한
5. 품질 검사: 원본 동일성, 프레임 깜박임, 흔들림, FPS/코덱, 모바일 재생 및 축소 동작
6. 배포: 파일 SHA256, 승인자, 승인 시각, GitHub 검토 브랜치 업로드, PR 리뷰 후 Netlify 배포

## 외부 학습 기능 (1차: 안전한 지식 수집)
`external_knowledge.py`는 사람이 검토한 **HTTPS 허용 출처의 JSON 참고자료**만 로컬 JSONL에 기록합니다. 자동 웹 크롤링·모델 가중치 학습·외부 코드 다운로드/실행은 **하지 않습니다**. 향후 검색/검색증강(RAG)은 라이선스·출처·검토·샌드박스·버전 고정·관리자 승인 후 별도 구현합니다.

입력 JSON 예시:
```json
{"title":"Optical flow reference","source_url":"https://docs.opencv.org/","topic":"optical-flow","notes":"Reviewed summary and application ideas only","approved_by":"local-admin"}
```
명령: `python tools/entrance_video/external_knowledge.py --input reviewed.json`

## 보안
외부 참고 문서는 신뢰하지 않는 데이터로 취급합니다. 문서 속 명령·코드를 자동 실행하지 않으며, 지식 저장은 엔진 업데이트나 배포를 승인하는 행위가 아닙니다. 원본 이미지와 인증 토큰은 업로드하지 않습니다.
