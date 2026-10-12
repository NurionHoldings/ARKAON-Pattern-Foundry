# Logo Evolution Engine — 동작형 프런트엔드 시안

## 실행
저장소 루트에서 `python -m http.server 8080` 후
`http://localhost:8080/prototypes/logo-evolution/` 접속.

- 레벨 1~5 슬라이더, 로고 유형, 강도, 지원 가능한 효과 필터링
- 실제 원본 로고 사용 시 `<arkaon-logo-evolution logo-src="/approved-logo.png"></arkaon-logo-evolution>`
- `logo-evolution-change` 이벤트의 `detail`에 설정값 전달
- 접근성: 키보드 슬라이더, 상태 텍스트, reduced-motion 대응
- 원본 로고 변경 및 네트워크 호출 없음

**주의**: 현재 CSS 광택·확대는 UI 개념 검증용이며, 영상 생성, 고품질 프리뷰, 업로드, 회원 인증, 결제 및 실제 로고 구조 분석은 미구현. 로고 유형은 사용자가 선택하며 자동 판정은 향후 단계.
