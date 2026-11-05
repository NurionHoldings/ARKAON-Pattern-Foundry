# 아르카온 검증 실행 연결부

이 기능은 승인된 고정 시험을 실행하는 실제 자동화 작업자다. 임의 코드를 작성하는 AI 개발 에이전트,
전체 1차 검증, 에테르니언 독립 감사, 개선 인정 또는 병합·배포로 바꾸어 부르지 않는다.

## 연결

1. `requests/verification/<id>.json`에 base/candidate full SHA·고정 프로필·읽기 범위를 기록한다.
2. 사용자의 실행 연결 지시를 근거로 별도 `approvals/self-improvement/<id>.json`을 기록한다.
   현재 승인 기록은 대화 지시를 저장한 것이며 암호학적 사용자 서명/외부 신원 인증이 아니다.
3. CLI가 지정된 승인 commit에서 두 JSON을 읽고 기존 approval ledger와 OWNER_APPROVED queue에 결속한다.
4. 소비자는 queue↔ledger의 digest를 재산출하고 승인 commit의 원문과 다시 대조한다.
5. 후보 diff가 승인 경로 안인지 확인하고 candidate SHA의 별도 detached worktree를 생성한다.
6. 기존 `ArkaonWorkerRuntime`이 VERIFY 과제를 claim하고 `DockerVerificationExecutor`를 호출한다.
7. ACK/실행 ID/실제 SHA/시각/명령·로그 hash/프로필 결과/증거 digest를 run별로 반환한다.
8. 자동 시험이 성공해도 `first_verification_complete=false`, `independent_audit_status=NOT_RUN`,
   `improvement_accepted=false`, merge/deployment false로 멈춘다.

실행 결과는 `state/verification-worker/runs/<execution_id>/`에 보관한다. 완료 인덱스는
`completed/<request_id>.json`이며 같은 승인 작업을 반복 실행하지 않는다. checksum 불일치는 차단한다.
중단된 claim·잠금은 자동 삭제/재점유하지 않는다. 실패도 자동 재실행하지 않는다.
승인받은 새 요청 ID 또는 중단 상황을 확인한 별도 복구 절차가 필요하다.
기존 일반 승인 queue에는 verification plan이 없으므로 건너뛰며 새 검증을 굶기지 않는다.
손상 queue 하나가 뒤의 정상 작업 소비를 막지 않으며 원본 queue/ledger를 이동·삭제하지 않는다.

## 고정 프로필과 격리

- isolation: 네트워크 도달 불가·read-only mount·capability 0·no-new-privileges·호스트 자격정보 미주입 실제 확인
- learning: 근본 학습/근거/환류 오류 시험
- brand: 브랜드 렌더링·대비·한국어 시험
- platform: 기존 스튜디오와 다판다/더아리랑 기본 틀 시험

명령은 소스 코드의 allowlist에서만 선택하고 profile_digests로 실제 argv까지 승인 범위에 결속한다. 명령 변경 시 기존 승인은 거절한다. CLI는 worker 모듈의 실제 위치와 src/apf의 tracked 수정 여부도 확인한다. request에 임의 command/셸/Python 코드/빌드 작업을 넣을 수 없다.
기존 worktree helper에 Node 임의 실행 권한을 추가하지 않는다. 새 executor는 로컬 image content ID로만 실행한다.
컨테이너에 network=none/read-only/cap-drop ALL/no-new-privileges/UID65534/메모리·CPU·PID·시간·출력 제한을 둔다.
후보는 read-only로 mount하고 host Docker socket·HOME·토큰·시크릿·state를 mount하지 않는다.
실행 로그는 호스트가 수집한다. rootfs나 후보에 쓰지 못하며 writable /tmp는 크기 제한이 있다.
이미지 준비의 apt/pip는 네트워크를 쓰지만 실제 과제 실행은 분리된 offline 컨테이너다.
전용 dockerignore와 선택 COPY로 PC의 .env/state/private 자료가 image build에 들어가지 않게 한다.
Docker가 없거나 image가 준비되지 않으면 호스트 직접 실행으로 우회하지 않는다.
호스트 Git/consumer 및 Docker 관리자는 신뢰 경계다. checksum은 관리자 변조 방지 서명이 아니다.

## 실제 클라우드 트리거

새 `ARKAON verification worker` workflow는 검증 연결 PR의 정확한 head를 checkout하고,
새 image를 준비한 후 승인된 #132 후보 `2f9f4694e2e3f1ffaf36db96c1e932da8a401c5a`를 실행한다.
worker_id=arkaon-ci-verifier이며 실행 ID/ACK/result/로그/ledger/queue는 별도 artifact로 제출한다.
두 번째 소비는 already_completed여야 한다. 일반 pytest fixture의 TEST-DOUBLE은 실제 실행 증거가 아니다.
GitHub workflow 토큰은 contents:read만 사용하며 외부 댓글·배포·merge 권한을 부여하지 않는다.
새 요청은 새 승인 commit과 명시적 intake를 사용한다. 이 workflow는 모든 연구자료의 자동 코드 구현기가 아니다.

## Windows PC 연결

업데이트된 코드와 Docker Desktop의 Linux container 모드가 필요하다. 이 세션은 사용자 PC를 원격 기동하지 않는다.
PC에서 다음 명령은 image 준비→현재 승인 작업 실행→relay 연결 설정을 한 번에 수행한다.

```powershell
powershell.exe -File orchestrator/arkaon-verification-worker.ps1 -BuildImage -ConnectRelay
```

이후 현재 코드로 시작한 기존 15초 relay는 `state/verification-worker-connection.json`을 매 주기 읽고
검증 프로세스를 별도로 호출한다. 기존 실행 중인 구버전 relay는 코드 업데이트 뒤 한 번 다시 시작해야 한다.
예약 작업 재등록이나 Windows 권한 확대를 자동 수행하지 않는다. 본 스크립트 자체에 watch를 지정할 수도 있다.

```powershell
powershell.exe -File orchestrator/arkaon-verification-worker.ps1 -WatchSeconds 15
```

Docker image가 content ID로 로컬에 준비되어야 한다. 이 ID는 비밀값이 아니다.
연결 설정이 없으면 기존 relay 동작을 유지한다. 잘못된 설정은 BLOCKED로 보고하고 우편함 처리는 계속한다.
클라우드 성공은 PC 설치·예약 작업 기동 완료가 아니다. PC ACK가 오기 전에는 PC 실행 완료를 표시하지 않는다.

## 검증과 반영

단위시험은 승인/원장/queue 변조·불완전 claim·중복 실행·금지 명령·Docker 부재·레거시 job·실패 격리와
relay 비동기 호출을 확인한다. 실제 컨테이너 검증은 별도 workflow 결과로 판단한다.
본 변경은 #132 위 별도 PR이다. 아직 main 병합·운영 반영·전체 독립 감사는 하지 않는다.
롤백은 연결 설정 제거 후 기존 relay/consumer를 정상 종료하고 feature revert한다.
결과/원장/미완료 claim과 고객 초안은 삭제하지 않는다. 임의 오래된 잠금 제거로 실행을 재개하지 않는다.

## 첫 실제 실행 보완

초기 request `main-integration-20261105-verify`는 #132에 이미 포함된 tools 경로를 빠뜨려
CANDIDATE_OUTSIDE_SCOPE로 실행 전에 차단되었다(run41969994301). 이를 성공으로 표기하지 않는다.
v2 요청은 같은 후보·같은 프로필에 기존 도구 경로만 반영한다. 원본 요청/승인은 보존하고 새 ID를 사용한다.
새 preflight가 승인/원장/후보 전체 범위를 image 준비 전에 확인하며 preflight PASS는 실행 ACK가 아니다.
