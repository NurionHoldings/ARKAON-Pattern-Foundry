# 아르카온 전용 GitHub 코딩 작업자

사용자가 GitHub 저장소에서 직접 구현하도록 지시한 연결 작업이다.

## 구성

- `.github/agents/arkaon.agent.md`: GitHub Copilot cloud agent에서 선택하는 ARKAON 프로필.
- `.github/copilot-instructions.md`: 기본 Copilot로 시작해도 ARKAON_TASK를 처리하는 작업 지침.
- 이슈 양식: 요청 목표·완료 기준·참고자료. 등록만으로 유료 실행하지 않는다.
- `requests/github-coding/<task-id>.json`: 에테르니언이 사용자 지시에 따라 default branch에
  등록한 허용 변경 범위, 출처 파일 blob, 만료, 변경 예산. 주제 목록을 제한하지 않는다.
- `ARKAON worker scope`: trusted default branch 코드만으로 PR의 변경 파일·작업자·출처·
  만료·범위·symlink·제어부 변경을 검사한다. PR 코드를 실행하거나 secret을 전달하지 않는다.

프로필의 read/search/edit/execute는 코딩에 필요한 도구다. 외부 웹 검색 도구 별칭은 GitHub
cloud에서 지원되지 않으므로 지원한다고 표시하지 않는다. 외부 자료 접근은 제공자의 네트워크
정책에 따르며, 불가능한 자료는 접근 가능한 공식 자료와 독자 구현으로 대체한다.

## 첫 실제 과제

이슈 #140, task_id `arkaon-github-smoke-20261108-01`.
공백뿐인 작업 요청의 저장을 막고 기존 입력을 보존하는 실제 버그를 ARKAON에게 맡긴다.
에테르니언은 이 설정 작업에서 해당 버그 해결 코드를 작성하지 않는다.
허용 파일은 공동작업 HTML·services.js·Node 회귀시험의 3개다.

## 실행

프로필을 default branch에 반영한 뒤, GitHub에서 이슈에 Copilot 코딩 작업자를 할당한다.
가능하면 ARKAON custom agent를 선택한다. 연결 도구가 agent_assignment 메타데이터를 지원하지
않으면 기본 agent도 저장소 instructions를 따라 같은 작업 지침을 적용하지만, custom profile이
실제로 선택됐다고 표시하지 않는다.

담당자 할당 응답만으로 실행 성공이라 하지 않는다. 실제 세션·agent PR·변경 코드·시험 로그와
실행 SHA를 확인한다. 완료한 제공자 task 상태도 독립 코드 검사와 구분한다.

GitHub cloud agent에는 유료 Copilot 플랜과 저장소에서의 사용 허용이 필요하다.
사용자의 과제 실행 지시는 새 구독 구매나 과금 한도 확대를 승인하지 않는다. 사용 가능 여부를
확인하고 지원되지 않는 인증·플랜 상태는 우회하지 않는다. 계정정보·토큰은 채팅·저장소에 넣지 않는다.

## 통제의 실제 경계

- 이전 ImprovementGrantAuthority는 Python 호스트 실행기에 적용되는 별도 장치다. GitHub의
  hosted agent에 해당 메모리 token이 저절로 주입되는 것으로 표시하지 않는다.
- 프로필은 지침, scope workflow는 PR 사후 검사다. 작업 중 OS 수준 파일 접근을 막는
  sandbox 또는 branch protection을 대신하지 않는다.
- scope check가 병합의 필수 조건이 되려면 저장소 ruleset/branch protection에서 해당 check를
  required로 지정해야 한다. 이 코드 추가만으로 해당 설정이 변경됐다고 주장하지 않는다.
- 에테르니언은 실제 변경 범위·시험을 확인하기 전 ARKAON PR을 병합하지 않는다.
  worker는 운영 배포·추가 유료 작업·자기 지침 변경 권한을 받지 않는다.
- `pull_request_target` job은 default branch guard만 실행한다. head 코드 checkout·head test·
  head script 실행·캐시·쓰기 token 사용을 추가하지 않는다. 기능 시험은 기존 읽기 token CI다.
- 첫 과제 manifest는 2026-11-10 00:00 UTC에 만료한다. 대기 중 만료되면 에테르니언이 범위를
  재확인한 뒤 갱신한다. 자동 재승인·자동 과금 재시작은 없다.

## 공식 근거

- https://docs.github.com/en/copilot/how-tos/use-copilot-agents/cloud-agent/use-cloud-agent-via-the-api
- https://docs.github.com/en/copilot/reference/custom-agents-configuration
- https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/create-custom-agents
