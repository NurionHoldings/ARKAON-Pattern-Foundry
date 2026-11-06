# 코딩·감사 작업자의 교신과 준비 상태

## 실제 준비 상태 (2026-11-06)

| 항목 | 확인 결과 | 사용자 준비 |
|---|---|---|
| GitHub 연결 도구 | 저장소 조회·브랜치·PR 제출 정상 | 저장소 권한 재승인 불필요 |
| 연결 브라우저의 GitHub | 로그인 시 `Incorrect username or password.` | 보안 입력으로 재인증하거나 본인 브라우저에서 초기 CI 2건 취소 |
| Netlify 프로젝트 | arkaonfoundry, Pro 프로젝트 조회됨 | 새 사이트 생성 불필요 |
| 원격 작업자 CLI | 실제 `agents:list --project arkaonfoundry --json` → `Not authorized to access project "arkaonfoundry"` | CLI가 프로젝트 소유 팀에 접근하도록 인증 확인 |
| 크레딧·작업 실행 비용 | 잔액/사용 한도 미확인, 유료 작업 미시작 | 사용 가능 크레딧과 최초 코딩 작업 1회 비용 사용 승인 |
| 상시 중계 호스트 | 현재 사용자 PC 접근/설치 상태 미확인 | 기존 15초 relay PC가 켜진 상태로 지속 실행할지 확인 |
| 결과 인증 | 역할별 HMAC 검사 구현, 운영 키 미설정 | 호스트가 정해진 뒤 별도 키를 안전 설정. 키를 채팅/저장소에 넣지 않음 |

브라우저 로그아웃은 코드 작업의 전체 권한 부재가 아니다. 연결 브라우저 로그인과 GitHub 앱 연결, Netlify 앱 연결과 CLI 인증은 각각 다르다. 사용자의 일반 브라우저 로그인은 이 연결 브라우저로 자동 전달되지 않는다. 직접 GitHub에서 run 42145894280·42146070154를 취소하면 브라우저 연동 없이도 초기 실행 정리가 가능하다. 코드 개발은 계속 가능하다.

## 구현된 교신 코드

- `apf.agent_exchange.prepare`: 기존 SELF_IMPROVEMENT_REQUEST의 request_id·scope_digest·기준 SHA를 결속한 원격 코딩/감사 작업과 정확한 Netlify CLI 명령 생성.
- `submit`: GitHub 원격 branch의 실제 HEAD를 API로 대조해 이동 시 과금 전에 중단한다. `AUTHORIZE_ONE_BILLABLE_TASK`와 task/command digest·승인자·승인시각·만료시각이 일치하는 **단일 실행**만 시작. API 호출 없이 문서화된 `netlify agents:create` 사용. 원격 작업은 새 branch에 작성. 시간초과/응답 불명은 claim을 유지하며 재과금을 막기 위해 자동 재제출하지 않음.
- `poll`/`watch`: 문서화된 `netlify agents:show`로 확인하고 상태 변화만 inbox에 보존. 기본 15초. 완료된 작업은 다시 조회하지 않음. 구현자/감사자 역할 키·DB 비밀정보는 CLI 환경에서 제외.
- `record`/`accept_result`: 역할별 host-side HMAC, 요청/scope/작업·실행 SHA·별도 worker·별도 증거 결속 확인. 인증된 제출물도 독립 감사 최종 승인으로 자동 인정하지 않음.
- ARKAON은 Codex 실행, ETERNIAN_AUDIT_WORKER는 별도 Claude 실행으로 구분. 모델/계정 이름만으로 독립 감사를 인정하지 않음. 감사는 실제 구현 결과의 SHA·worker·근거를 확인한 뒤 준비.

**이 코드는 ChatGPT 현재 대화창을 자동으로 깨우지 않는다.** 외부 감사 작업자는 별도 실행 인스턴스다. 본 세션에서 에테르니언이 직접 검토하는 행위와 외부 감사 worker의 서명을 구분한다.

## 최초 실행 준비물

`requests/agent-exchange/brand-gallery-first-verify.json`과 `brand-gallery-arkaon-task.json`에 #135의 실제 원격 branch 및 기준 SHA를 고정했다. 준비 상태는 PREPARED_NOT_SUBMITTED다. `task.command`는 추상 예제가 아닌 정확한 원격 명령 배열이며 유료 실행 전에 검토할 수 있다. 원격 작업자는 푸시된 코드만 본다.

상시 호스트에서 Netlify CLI 설치·인증을 하고 같은 계정/팀으로 arkaonfoundry 접근을 확인한다. 프로젝트 조회 연결만으로 CLI 인증이 된 것으로 간주하지 않는다. 접근 오류를 숨기거나 다른 endpoint로 우회하지 않는다.

```sh
python -m apf.agent_exchange preflight
# 폴링만 수행: 새로운 유료 작업을 만들지 않음
python -m apf.agent_exchange watch --foundry-root /persistent/foundry --seconds 15
```

Windows: `orchestrator/arkaon-agent-exchange.ps1`. 기존 작업의 등록·재시작은 이 PR에서 하지 않았다. 운영 키 설정 전에는 인증 결과의 record 경로는 차단한다. 역할 키는 호스트에서 검증한 결과에 서명하기 위한 별도 키이며 원격 AI 프롬프트에 전달하지 않는다.

한 번의 비용 승인을 받으면 호스트의 gitignore된 로컬 승인 파일에 task/command digest·승인자·승인시각·짧은 만료를 기록해 submit에 전달한다. 이 파일은 로컬 운영자 진술이며 GitHub 사용자 전자서명 검증을 대신하지 않는다. 상시 무제한 유료 작업 권한으로 확대하지 않는다. 지속적인 비용 예산 정책은 추후 명시 승인 범위다.

## 완료로 보지 않는 것

- 실제 원격 AI 실행: CLI 접근권한·크레딧·1회 비용 승인 대기.
- Netlify 실제 응답 JSON과 adapter의 id/status mapping: 최초 실제 실행에서 재검증 필요. 예측하지 못한 응답은 재조회/재과금 대신 reconciliation으로 정지.
- 원격 생성 branch/manifest 회수·실제 Git diff 경로 검사·시험 재현·호스트 서명·다음 감사 작업의 자동 제출을 잇는 전체 완주: 아직 미검증. provider done은 코드·시험 PASS가 아님.
- 인터넷 endpoint나 webhook을 새로 개방하지 않았다. 파일 기반 courier가 먼저 준비된 상태다. 유료 submission과 감사 완료 자동 연쇄는 아직 활성화하지 않았다.
- 운영 호스트의 영속 디스크/자격증명 보호/단일 submitter가 전제. GitHub Actions 임시 디스크로 실행 간 exactly-once를 주장하지 않음.
- 별도 키가 같은 호스트에 있다는 것만으로 조직·실행환경 독립성이 확보되는 것은 아니다.

병합·운영반영 HOLD 유지. 이 PR의 단위 시험은 TEST_DOUBLE이며 실제 AI가 구현/독립 감사한 증거가 아니다.
