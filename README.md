# ARKAON Pattern Foundry

현재 #039는 tenant-scoped 대상 API와 인증된 한국어 운영·검토 콘솔 shell을 제공한다.
검토·후보 live adapter, 외부 서명 검증 수신, 운영 IAM 연동 전까지 제품 상태는
`PRODUCT_IMPLEMENT_HOLD`이며 Intent_DNA 변경, MJN 쓰기, 자동 자산 승격은 잠겨 있다.

에테르니언과 아르카온이 허가된 시스템을 구조적으로 분석하여 재사용 가능한 설계자산을 생산하는 지식제조 엔진입니다.

> 복제 기술 자체를 금지하지 않습니다. 소유·명시적 허가·라이선스 범위에서는 코드와 소재를 재사용하고 의무를 승계하며, 공개 관찰물은 기능·구조를 추출해 실질적으로 개선합니다. 개인정보·비밀정보 취득과 접근통제 우회는 금지합니다.

## v0.1 목표

- 자체 플랫폼 3개 완전 분석: MJN, 노가다뉴스, 부업장터
- 플랫폼 유형 5개 정의
- 공통 설계패턴 30개 심사·승격 및 재사용 증명 (목표, 현재 미달성)
- 재사용 기능모듈 10개 확정
- 신규 사업아이디어 1개에 자산 재사용
- 기존 대비 기획시간 50% 단축
- 출처 불명·고객 전용정보 공용혼입 0건

## 핵심 흐름

```
REGISTER → AUTHORIZE → SNAPSHOT → EXTRACT_INTENT_DNA → ANALYZE
→ ABSTRACT → VALIDATE → APPROVE → PUBLISH → REUSE → LEARN
```

모든 자동학습 결과는 검증과 승인 후에만 공식 자산이 됩니다. 권한·보안·결제·정산·개인정보 규칙은 자율변경 대상이 아닙니다.

## 설계문서

1. [책임과 경계](docs/01-responsibility-boundary.md)
2. [전체 도메인 모델](docs/02-domain-model.md)
3. [에테르니언↔아르카온 교신 프로토콜](docs/03-communication-protocol.md)
4. [분석대상 수집·등록](docs/04-target-ingestion.md)
5. [Pattern Package 표준](docs/05-pattern-package.md)
6. [출처·라이선스·공용화 정책](docs/06-provenance-policy.md)
7. [분석·검증·승인 상태머신](docs/07-state-machine.md)
8. [지식저장소와 검색](docs/08-knowledge-repository.md)
9. [자체 플랫폼 분석 절차](docs/09-owned-platform-analysis.md)
10. [v0.1 API·DB·화면·테스트 명세](docs/10-v0.1-product-spec.md)
11. [Intent_DNA 기법](docs/11-intent-dna.md)
12. [실행계획과 설계 잠금](docs/12-execution-plan.md)
13. [ARKAON 실전 역할 검증·효율 계측](docs/13-role-benchmark.md)
14. [증거 기반 실전 벤치마크 캠페인](docs/14-evidence-benchmark-campaign.md)
15. [안전 합성 개발과제 캠페인](docs/15-synthetic-role-campaign.md)
16. [실전 관측 원장·파일럿 준비](docs/16-pilot-observation-ledger.md)
17. [실전 관측 증거 번들·독립 검증](docs/17-pilot-evidence-bundle.md)
18. [MJN 읽기 전용 분석 파일럿](docs/18-mjn-readonly-analysis-pilot.md)
19. [Clean-room 유사 플랫폼 재구현](docs/19-clean-room-analog-synthesis.md)
20. [사용자 매개 인증요청·외부 자산획득 게이트](docs/20-mediated-auth-acquisition.md)
21. [권한 기반 소재 수집·복제·개선](docs/21-authorized-material-acquisition.md)
22. [자산획득 작업 오케스트레이터](docs/22-acquisition-job-orchestrator.md)
23. [재시작 안전 영속 저장소·에테르니언 검토 큐](docs/23-durable-review-queue.md)
24. [v0.1 출시준비 인증 실행서](docs/24-release-readiness.md)
25. [v0.1 로컬 출시준비 보고서](docs/25-v0.1-release-report.md)
26. [#031 에테르니언 검토 게이트](docs/26-analog-review-gate.md)
27. [PostgreSQL Repository 및 실연결 게이트](docs/27-postgresql-repository.md)
28. [운영·검토 콘솔](docs/28-operations-review-console.md)
29. [노가다뉴스·부업장터 메타데이터 파일럿](docs/29-owned-platform-metadata-pilots.md)
30. [공용 Pattern 후보 30개와 승격·재사용 증명](docs/30-public-pattern-catalog.md)
31. [ARKAON 지도 연동 역량](docs/31-arkaon-map-integration-capability.md)
32. [ARKAON 진화 경계](docs/32-arkaon-evolution-boundary.md)
33. [ARKAON 정확도 보증](docs/33-arkaon-accuracy-assurance.md)
34. [ARKAON 단계적 롤아웃](docs/34-arkaon-staged-rollout.md)
35. [라이더 경로 선택권·안전·비용 투명성](docs/35-route-choice-safety-cost.md)
36. [ARKAON 지도역량 정확도 평가](docs/36-arkaon-map-competency-evaluation.md)
37. [라이더 모빌리티 광장 기반계층](docs/37-rider-mobility-plaza-foundation.md)
38. [중앙 ARKAON 오케스트레이터](docs/38-central-arkaon-orchestrator.md)
39. [ARKAON 화면·콘텐츠·운영 정합성 감사](docs/39-arkaon-experience-operations-audit.md)
40. [ARKAON 통제된 성찰학습·교훈기억](docs/40-arkaon-reflective-learning.md)
41. [우편함 유지관리](docs/41-mailbox-maintenance.md)
42. [승인 기반 자기개선 실행](docs/42-self-improvement-execution.md)
43. [신규사업 사전준비 지능](docs/69-venture-preflight-intelligence.md)

## 중앙 오케스트레이터

Pattern Foundry는 다중 플랫폼 ARKAON의 본거지입니다. PC 로그인 시 등록된 플랫폼만
순차 분석하고, 결과는 `inbox/eternian-review`에 격리합니다. 승인 전 코드·운영 반영은
하지 않습니다.

```powershell
powershell.exe -ExecutionPolicy Bypass -File "D:\ARKAON_Pattern Foundry\orchestrator\arkaon-launcher.ps1"
powershell.exe -File "D:\ARKAON_Pattern Foundry\orchestrator\arkaon-startup.ps1"
powershell.exe -ExecutionPolicy Bypass -File "D:\ARKAON_Pattern Foundry\orchestrator\register-startup-task.ps1"
```

## 구현 게이트

현재 상태는 **#047 CENTRAL ARKAON ORCHESTRATOR FOUNDATION / PRODUCT IMPLEMENTATION HOLD**입니다. 정확히 30개 후보와 검증·외부서명 승격·재사용 proof harness가 있지만, 모든 후보는 `ETHERNIAN_REVIEW_REQUIRED`이며 운영 승격은 0건입니다. 테스트 전용 서명은 `TEST_VECTOR`일 뿐 운영 승인이 아닙니다. PostgreSQL 대상 저장소와 CI 경로는 구현됐지만 live Green 증거 및 PostgreSQL 검토·후보 어댑터는 아직 없습니다. 노가다뉴스·부업장터는 제공된 구조 메타데이터 기반 읽기 전용 파일럿만 구현됐고 실제 저장소 연결·코드 분석은 `NOT_RUN_UNAVAILABLE`입니다. UI 상세 렌더링, 외부 서명에 의한 30개 개별 승격과 실제 재사용 증명도 미완료입니다. 상세 상태는 `knowledge/readiness/v0.1-readiness.json`이 기준입니다.

## 공개 저장소 정책

이 저장소에는 공용 설계문서와 합성 예제만 둡니다. 고객 원본, 운영 DB, 개인정보, 자격증명, 비공개 소스, 내부 가격·계약정보는 저장하지 않습니다.
