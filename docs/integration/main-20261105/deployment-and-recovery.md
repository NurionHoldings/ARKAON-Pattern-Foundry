# 2–5단계 실행·검토·운영 검증·반영 준비

검증 코드 SHA: `daadc407c6588a4668ef72d0b5dd5cba06125a4d`.
일반·PG·Windows·컨테이너·브랜드·기본틀 CI success. run/ZIP digest는 release-readiness.json 참조.
이후 증거 문서 커밋은 실행 코드 SHA를 바꾸어 부르지 않는다.

## 2. 아르카온 실행 연결 — BLOCKED

#131에 새 main 기준 후보를 전달한다. 현재 worker ACK/worker_id/execution_id가 없다.
main의 relay는 PC→GitHub 전달과 승인 queue 생성까지다. queue 생성은 코드 실행이 아니다.
ArkaonWorkerRuntime은 주입된 WorkerExecutor를 호출하는 틀이지만 실제 개발·검증 executor와
외부 요청을 수신하는 기동 경로가 확인되지 않았다. concrete execute 구현은 합성 benchmark용이다.
현재 Netlify 배포는 정적 파일이며 worker Function/Server가 없다.
기존 worktree helper는 Python/pytest/Ruff 실행파일 이름만 허용하므로 Node 브랜드 시험도
그대로 연결할 수 없다. 이를 우회하거나 Node 임의 명령을 허용하지 않는다.

실제 연결에는 승인·scope 원장 확인 → 고정 task/명령 allowlist → 별도 worktree 작업자 →
관측 가능한 ACK/결과 제출이 필요하다. 이 세션에서 PC 예약 작업·프로세스를 직접 기동할 수 없다.
이 문서/이슈/CI를 ARKAON 실행으로 표시하지 않는다. 개발용 새 executor 연결은 별도 검토 대상이다.

## 3. 최종 독립 검토 — NOT_RUN

이번 통합과 시험은 에테르니언 직접 작업이다. 스스로 작성한 코드를 독립 감사 완료로 표기하지 않는다.
ARKAON 별도 1차 실행, 변경 SHA/전체 산출물 검증 및 작성자와 분리된 검토 결과가 필요하다.
검토 대상: source-selection의 45개 파일과 통합 조정7개, 로컬 보관 경계, 계정 재편집 링크,
HTML 내보내기, Blob iframe/입력 escaping, 회귀·대비 및 실패 입력 처리.
기존 mobile 긴 폼/빈 약자 자동 생성/저장 실패 안내 개선은 이번 1단계 밖의 남은 UX 위험이다.
기존 UI 패턴 시험의 자동 PASS는 전체 접근성·실기기·유료 서비스 품질 인증이 아니다.

## 4. 운영과 같은 환경 시험 — 정적 UI 범위 PASS

Netlify deploy-preview `6aebe3a4a4cb6328df09a833`는 정확한 코드 SHA를 배포했다.
https://deploy-preview-132--arkaonfoundry.netlify.app/services/site-builder.html
가상 입력→더아리랑형→상세3항목→저장→내 작업→이어서 편집에서 선택·입력 복원을 관찰했다.
브랜드도 가상 사업 입력→자연스러운 문구→지평선 선택→저장→내 작업→재편집에서 선택·문구 복원을 관찰했다.
다판다/더아리랑360·390·1440, HTML export/계정 링크/서버 API 미호출은 별도 CI6회로 검사했다.
실제 운영본은 main a26baa7이며 변경하지 않았다. 운영 URL5개 HTTP200을 읽기 전용으로 확인했다.
기존 진입 영상과 서비스 설정 JSON은 운영·preview 모두200, 새 JS는 preview200이며 운영404가 정상이다.
Preview와 production의 브라우저 저장소는 서로 다르다. 고객 원본 작업을 이동·삭제하지 않는다.
서버 세션/동의/결제/PC학습/실기기와 production 후보 반영 후 smoke는 미실행이다.

## 5. 배포·복구 준비 — PREPARED, 미실행

현재 운영 deploy id: `6ad5a7ade2234c92d1630a5c`, source a26baa7.
보존 source: baseline-a26baa7.zip / candidate-daadc407.zip. SHA-256·크기는 release-readiness.json.
기준선과 후보 원본은 GitHub commit에서도 다시 확보할 수 있다. 런타임/비밀값은 archive에 넣지 않는다.
DB migration과 서버 환경변수 변경은 없다. 같은 localStorage 키를 사용하고 기존 작업을 일괄 재작성하지 않는다.

반영 전 필수: 2/3 차단 해소 또는 별도 범위 결정, 사용자 최종 병합·운영 승인, 최신 main과 충돌 재확인,
정확한 최종 배포 SHA의 CI, 실제 publish 디렉터리/production branch/자동 게시 설정 확인.
main push가 운영 빌드를 유발할 수 있으므로 승인 없이 main 병합으로 우회하지 않는다.
승인 후에만 기존 연결을 통해 배포하고 home/video/config/브랜드/홈페이지/계정·기존 초안 smoke를 수행한다.
실패한 배포는 운영본을 바꾸지 않으므로 이전 운영본을 유지한다.
잘못 공개된 변경은 승인된 revert PR로 되돌린 소스를 CI 후 다시 배포한다(fix forward).
merge commit이면 실제 merge SHA 기준 `git revert -m 1`, squash이면 실제 squash SHA 기준 `git revert`를
검토 브랜치에서 준비한다. 아직 발생하지 않은 merge SHA를 임의로 채우거나 현재 revert를 실행하지 않는다.
복구 때에도 고객 localStorage는 지우지 않는다. 운영 배포 완료·복구 시험 완료로 표시하지 않는다.
