# 중앙 ARKAON 오케스트레이터 (Pattern Foundry 본거지)

조회일: 2026-09-17
상태: 로컬 설치형 중앙 실행기 구현. PC 로그인 시 **자동 수집·분석**(`arkaon-startup.ps1`)이
기본이며, 등록은 **인석형 PC에서 1회** `register-startup-task.ps1` 실행으로 완료합니다.

## 디렉터리

```text
D:\ARKAON_Pattern Foundry\
├─ orchestrator\
│  ├─ arkaon-launcher.ps1
│  ├─ arkaon-startup.ps1
│  ├─ arkaon-orchestrator.py
│  ├─ register-startup-task.ps1
│  └─ arkaon.workspace.template.json
├─ config\
│  ├─ platforms.json
│  ├─ shared-policy.json
│  └─ resource-limits.json
├─ inbox\
│  ├─ research\
│  ├─ eternian-review\
│  └─ operator-decision\
├─ knowledge\
│  └─ shared-public-patterns\
├─ reports\YYYY-MM-DD\
├─ logs\
├─ quarantine\
└─ state\
```

각 플랫폼 폴더에는 연결파일 `arkaon.workspace.json`만 둡니다. 운영 데이터는 플랫폼 안에
남깁니다.

## 가동 전 확인

- `platforms.json`과 각 플랫폼 `arkaon.workspace.json`의 `platform_id` 일치
- 등록 경로 정규화 후 Foundry 밖·허용 분석 루트 밖으로 이탈 차단
- 심볼릭 링크·Junction 경로 우회 차단
- `.env`, 인증서, 토큰, 운영 DB, 개인정보 폴더 제외
- `state/orchestrator.run.lock` 중복 시작 방지
- 리소스 정책(`config/resource-limits.json` v2) — 기본 **무제한 축적·병렬 분석** (#060)
- 학습 축적 정책(`config/arkaon-accumulation-policy.json`)
- 플랫폼 분석 실패 격리(다른 플랫폼 계속 실행)
- 보고서에 `platform_id`, `candidate_commit`, `created_at`, `report_sha256` 기록
- `operator-decision`은 에테르니언 검토 전 이동 금지
- 인석형 승인 전 수정·커밋·PR·병합·배포 금지

합성 점검:

```powershell
Set-Location "D:\ARKAON_Pattern Foundry"
python -m pytest
python "orchestrator\arkaon-orchestrator.py" --dry-run
```

시작 작업 등록(1회, **예약 작업 + 시작프로그램 + 5분 워치독**):

```powershell
& "D:\ARKAON_Pattern Foundry\orchestrator\register-startup-task.ps1"
```

상태 진단:

```powershell
& "D:\ARKAON_Pattern Foundry\orchestrator\arkaon-autostart-diagnose.ps1"
```

재부팅 없이 시험:

```powershell
Start-ScheduledTask -TaskName "ARKAON_Pattern_Foundry"
```

## PC 로그인 흐름 (자동)

1. Windows 로그인 시 `arkaon-startup.ps1`이 **숨김 창**으로 자동 실행
2. 연속 수집 데몬(`arkaon-collector-daemon.ps1`)과 15분 주기 분석 데몬
   (`arkaon-analysis-daemon.ps1`)을 백그라운드로 기동
3. 중앙 오케스트레이터를 **즉시 1회** 실행
4. `config/platforms.json`에 등록·enabled된 폴더만 순차 확인
5. 플랫폼별 구조 분석(공개 src/docs/tests/config 경로의 파일명 목록 digest)
6. 화면·콘텐츠·운영 정합성 감사(`docs/39`) → `inbox/research`에 IMPROVEMENT_PROPOSAL 생성
7. 사전보완 가이드 생성
8. `inbox/research`와 `inbox/eternian-review`에 격리 저장
9. 에테르니언·운영자 승인 전까지 코드·운영환경 미반영

수동 ❤ 실행 버튼 UI가 필요할 때만:

```powershell
powershell.exe -ExecutionPolicy Bypass -File "D:\ARKAON_Pattern Foundry\orchestrator\arkaon-launcher.ps1"
```

## 설치 (인석형 PC, 1회)

관리자 권한 없이도 동작하도록, 작업 스케줄러 등록이 거부되면 **시작프로그램
바로가기**로 자동 대체됩니다.

```powershell
powershell.exe -ExecutionPolicy Bypass -File "D:\ARKAON_Pattern Foundry\orchestrator\register-startup-task.ps1"
```

시작프로그램만 쓰려면:

```powershell
powershell.exe -ExecutionPolicy Bypass -File "D:\ARKAON_Pattern Foundry\orchestrator\register-startup-task.ps1" -Method StartupFolder
```

수동 1회 실행:

```powershell
powershell.exe -File "D:\ARKAON_Pattern Foundry\orchestrator\arkaon-startup.ps1"
```

경로에 공백이 있으므로 반드시 전체 경로를 따옴표로 감쌉니다.

## 플랫폼 등록

`config/platforms.json` 예:

```json
{
  "schema_version": "apf.central-platforms/v1",
  "foundry_root": "D:\\ARKAON_Pattern Foundry",
  "platforms": [
    {"id": "NARANG_RIDER", "path": "D:\\narangrider", "enabled": true}
  ]
}
```

등록되지 않은 폴더는 호출하지 않습니다.

## knowledge 경계

Foundry `knowledge/`에는 공개자료, 정책, 스키마, 합성시험 패턴, 일반화된 개발지식만
둡니다. 회원·주문·위치·정산·계약·본인인증 자료는 각 플랫폼 내부에 격리합니다.
