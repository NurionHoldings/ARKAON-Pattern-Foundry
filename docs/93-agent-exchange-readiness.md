# 코딩·감사 작업자의 교신과 준비 상태

## 실제 준비 상태 (2026-11-06)

| 항목 | 확인 결과 | 사용자 준비 |
|---|---|---|
| GitHub 연결 도구 | 저장소 조회·브랜치·PR 제출 정상 | 저장소 권한 재승인 불필요 |
| 연결 브라우저의 GitHub | 로그인 시 `Incorrect username or password.` | 보안 입력으로 재인증하거나 본인 브라우저에서 초기 CI 2건 취소 |
| Netlify 프로젝트 | arkaonfoundry, Pro 프로젝트 조회됨 | 새 사이트 생성 불필요 |
| 원격 작업자 CLI | 공식 로그인 후 list/create/show 실제 성공 | 재로그인 불필요 |
| 첫 유료 작업 | 6aed6e8190dc980edf8ee86c 종료, 기능 시험 전 HOLD | 추가 실행은 별도 비용 승인 필요 |
| 상시 중계 호스트 | 현재 사용자 PC 접근/설치 상태 미확인 | 기존 15초 relay PC가 켜진 상태로 지속 실행할지 확인 |
| 결과 인증 | 역할별 HMAC 검사 구현, 운영 키 미설정 | 호스트가 정해진 뒤 별도 키를 안전 설정. 키를 채팅/저장소에 넣지 않음 |

브라우저 로그아웃은 코드 작업의 전체 권한 부재가 아니다. 연결 브라우저 로그인과 GitHub 앱 연결, Netlify 앱 연결과 CLI 인증은 각각 다르다. 사용자의 일반 브라우저 로그인은 이 연결 브라우저로 자동 전달되지 않는다. 직접 GitHub에서 run 42145894280·42146070154를 취소하면 브라우저 연동 없이도 초기 실행 정리가 가능하다. 코드 개발은 계속 가능하다.

## 구현된 교신 코드

- `apf.agent_exchange.prepare`: 기존 SELF_IMPROVEMENT_REQUEST의 request_id·scope_digest·기준 SHA를 결속한 원격 코딩/감사 작업과 정확한 Netlify CLI 명령 생성.
- `submit`: GitHub 원격 branch의 실제 HEAD를 API로 대조해 이동 시 과금 전에 중단한다. `AUTHORIZE_ONE_BILLABLE_TASK`와 task/command digest·승인자·승인시각·만료시각이 일치하는 **단일 실행**만 시작. API 호출 없이 문서화된 `netlify agents:create` 사용. 격리 작업공간에서 편집하고 Netlify가 결과 branch·commit을 관리한다. 작업자의 Git 쓰기는 금지한다. 시간초과/응답 불명은 claim을 유지하며 재과금을 막기 위해 자동 재제출하지 않음.
- `poll`/`watch`: 문서화된 `netlify agents:show`로 확인하고 상태 변화만 inbox에 보존. 기본 15초. 완료된 작업은 다시 조회하지 않음. 구현자/감사자 역할 키·DB 비밀정보는 CLI 환경에서 제외.
- `record`/`accept_result`: 역할별 host-side HMAC, 요청/scope/작업·실행 SHA·별도 worker·별도 증거 결속 확인. 인증된 제출물도 독립 감사 최종 승인으로 자동 인정하지 않음.
- ARKAON은 Codex 실행, ETERNIAN_AUDIT_WORKER는 별도 Claude 실행으로 구분. 모델/계정 이름만으로 독립 감사를 인정하지 않음. 감사는 실제 구현 결과의 SHA·worker·근거를 확인한 뒤 준비.

**이 코드는 ChatGPT 현재 대화창을 자동으로 깨우지 않는다.** 외부 감사 작업자는 별도 실행 인스턴스다. 본 세션에서 에테르니언이 직접 검토하는 행위와 외부 감사 worker의 서명을 구분한다.

## 최초 실행 준비물

`requests/agent-exchange/brand-gallery-first-verify.json`과 `brand-gallery-arkaon-task.json`에 #135의 실제 원격 branch 및 기준 SHA를 고정했다. v1은 실제 첫 실행 HOLD 이력으로 보존하며 재과금은 거부한다. 새 v2 요청은 brand-gallery-managed-retry.json, 정확한 명령은 brand-gallery-managed-task.json이며 미제출 상태다. `task.command`는 추상 예제가 아닌 정확한 원격 명령 배열이며 유료 실행 전에 검토할 수 있다. 원격 작업자는 푸시된 코드만 본다.

상시 호스트에서 Netlify CLI 설치·인증을 하고 같은 계정/팀으로 arkaonfoundry 접근을 확인한다. 프로젝트 조회 연결만으로 CLI 인증이 된 것으로 간주하지 않는다. 접근 오류를 숨기거나 다른 endpoint로 우회하지 않는다.

```sh
python -m apf.agent_exchange preflight
# 폴링만 수행: 새로운 유료 작업을 만들지 않음
python -m apf.agent_exchange watch --foundry-root /persistent/foundry --seconds 15
```

Windows: `orchestrator/arkaon-agent-exchange.ps1`. 기존 작업의 등록·재시작은 이 PR에서 하지 않았다. 운영 키 설정 전에는 인증 결과의 record 경로는 차단한다. 역할 키는 호스트에서 검증한 결과에 서명하기 위한 별도 키이며 원격 AI 프롬프트에 전달하지 않는다.

한 번의 비용 승인을 받으면 호스트의 gitignore된 로컬 승인 파일에 task/command digest·승인자·승인시각·짧은 만료를 기록해 submit에 전달한다. 이 파일은 로컬 운영자 진술이며 GitHub 사용자 전자서명 검증을 대신하지 않는다. 상시 무제한 유료 작업 권한으로 확대하지 않는다. 지속적인 비용 예산 정책은 추후 명시 승인 범위다.

## 완료로 보지 않는 것

- 실제 첫 원격 AI 실행은 완료했으나 Git 작업 지시가 제공자 제한과 충돌해 HOLD. 수정·시험 미실행. docs/evidence/agent-exchange/first-paid-20261106/review.json은 호스트 검토 기록이며 원본 transcript 바이트 증거가 아니다.
- 실제 응답 id/state를 확인하고 state 지원과 Node proxy 환경 전달을 보완했다. 단위 회귀는 실제 AI 기능 검증을 대신하지 않는다.
- 원격 생성 branch/manifest 회수·실제 Git diff 경로 검사·시험 재현·호스트 서명·다음 감사 작업의 자동 제출을 잇는 전체 완주: 아직 미검증. provider done은 코드·시험 PASS가 아님.
- 인터넷 endpoint나 webhook을 새로 개방하지 않았다. 파일 기반 courier가 먼저 준비된 상태다. 유료 submission과 감사 완료 자동 연쇄는 아직 활성화하지 않았다.
- 운영 호스트의 영속 디스크/자격증명 보호/단일 submitter가 전제. GitHub Actions 임시 디스크로 실행 간 exactly-once를 주장하지 않음.
- 별도 키가 같은 호스트에 있다는 것만으로 조직·실행환경 독립성이 확보되는 것은 아니다.

병합·운영반영 HOLD 유지. 이 PR의 단위 시험은 TEST_DOUBLE이며 실제 AI가 구현/독립 감사한 증거가 아니다.


## 제공자 관리 작업공간 v2

v2는 Git 쓰기를 요구하지 않는다. source HEAD·시험 파일·로그 SHA-256을 기록하고 Netlify가 이후 생성하는 최종 commit SHA를 추정하지 않는다. 호스트가 최종 결과 파일 바이트를 시험 해시와 대조해 별도 결속해야 한다. 이 회수·대조의 자동 완주는 아직 미구현/미검증이며 수동 독립 검토가 필요하다. v1은 이력 조회만 가능하고 새 유료 실행은 거부한다. 새로운 v2 요청·task digest의 재실행은 미승인·미제출이다. 제공자 기본 비운영 Preview는 작업자에게 운영 배포 권한을 부여하는 의미가 아니다.
