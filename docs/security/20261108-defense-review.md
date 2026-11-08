# 2026-11-08 에테르니언 방어 보강 및 우편함 검토

사용자가 요청한 홈·메뉴 개선, 버튼 전환, 보안 보강과 해당 변경의 병합·운영 배포 범위다.
다른 미병합 PR이나 전체 제품 HOLD 해제, 결제 개통, 실행기 권한 확대를 포함하지 않는다.

## 사례와 대응

공식 사례를 `knowledge/security/ai-threat-brief-20261108.json`에 기록했다.
- Anthropic 2025-11-13 사건: 보안 업무 사칭과 공격 분할, 도구로 정찰·자격증명 수집·유출.
  https://www.anthropic.com/news/disrupting-AI-espionage
- Anthropic containment 연구의 2026년 2월 내부 실험: 협업 메일 속 프롬프트가 비밀파일 접근과 송신을 유도.
  https://www.anthropic.com/research/how-we-contain-claude
- 외부 문서에 숨겨진 지시는 신뢰 경계 문제다.
  https://www.anthropic.com/research/prompt-injection-defenses

기존 learning_safety 호출부에서 역할 사칭·기존 지시 무시·승인 우회·비밀파일 유출 지시의
알려진 패턴을 탐지한다. NFKC 및 보이지 않는 포맷 문자 정규화를 적용한다.
결과는 원문 대신 코드로 기록한다. 이는 휴리스틱으로, 난독화·분할·다국어 공격의 완전 탐지를
보장하지 않는다. 정상 보안 설명도 탐지될 수 있으므로 차단 자료는 별도 검토 대상이며
승인됐다는 이유만으로 검사기를 자동 우회하지 않는다.

실제 배포 보호:
- 작업 제목·자가진단 결과·우편함 내용을 textContent로 표시.
- 개인 페이지 링크의 프로토콜·자격증명 검증, API URL의 HTTPS 검증.
- 사용자 생성 미리보기 iframe의 스크립트·동일 출처 권한 제거.
- 정적 배포는 allowlist 파일만 dist로 복사. src/inbox/state/승인·증거·비밀파일은 제외.
- CSP는 외부·인라인 임의 스크립트를 제한하고 기존 인라인 스크립트만 해시로 허용.
  스타일은 기존 UI 호환을 위해 인라인을 허용한다. API 주소 직접 설정을 지원하므로
  connect-src는 HTTPS 전체를 허용하며, 이는 외부 송신 allowlist 방화벽이 아니다.
- 기존 실행 정책의 비밀·네트워크 작업 금지를 유지. 정책 선언·attestation만으로
  OS 격리나 실제 네트워크 차단을 검증했다고 간주하지 않는다.

Netlify는 정적 화면만 배포한다. Python 학습 검사기의 실제 서버 반영과 ARKAON 실행기 수신·ACK,
OS 수준 비밀 마운트 차단·송신 제한은 별도 서버 운영 근거가 필요하다.
실제 모델 학습을 수행했거나 독립 ARKAON 실행이 완료됐다고 표시하지 않는다.

## 우편함

저장소 inbox/research, inbox/eternian-review, inbox/operator-decision 및 state에
검토할 JSON이 없었다. 읽기 전용 maintenance 결과 pending/deliver/invalid=0이다.
이는 사용자 PC나 서버의 실시간 우편함이 비었다는 증거가 아니다.
현재 공개 API 설정에는 운영 서버 주소가 없고 인증된 콘솔 세션도 제공되지 않았다.
새 우편함 화면은 GET만 수행하며 미연결·권한 부족·응답 오류를 0건과 구분한다.

GitHub에서 확인한 미해결 요청:
- #131: 학습→브랜드·플랫폼 기본 틀 보완. 실제 executor 연결/worker ACK 미확인.
  #128~130의 별도 검증·학습 환류·기본 틀 구현을 본 디자인 배포에 섞지 않는다.
- #76: Railway API 준비 상태 및 세션 비밀값 누락에 관한 운영 차단 보고.
  과거 이슈의 내용이며 이번 세션에서 Railway 실상태를 확인한 것은 아니다.
- #73: MACOL 통화·메뉴 동기화 요청. 별도 제품 범위다.

## 검증

학습 안전성·클라이언트 악성 링크/저장형 XSS·배포 allowlist/CSP 해시·우편함·sandbox 관련
회귀시험과 저장소 CI를 확인한다. 실제 새 공격 전부를 시험했다는 의미가 아니다.
브라우저에서는 미리보기 및 배포 후 홈·분류·기능 저장·우편함의 미연결 표시를 확인한다.
