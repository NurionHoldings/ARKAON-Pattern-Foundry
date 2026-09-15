# ARKAON Pattern Foundry

에테르니언과 아르카온이 허가된 시스템을 구조적으로 분석하여 재사용 가능한 설계자산을 생산하는 지식제조 엔진입니다.

> 특정 서비스의 디자인·문구·소스코드를 복제하지 않습니다. 자체 시스템, 위임받은 시스템, 공식 문서, 라이선스가 확인된 오픈소스만 분석합니다.

## v0.1 목표

- 자체 플랫폼 3개 완전 분석: MJN, 노가다뉴스, 부업장터
- 플랫폼 유형 5개 정의
- 공통 설계패턴 30개 확보
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

## 구현 게이트

현재 상태는 **#030 MJN READ-ONLY ANALYSIS PILOT / ETHERNIAN REVIEW REQUIRED**입니다. MJN의 고정 snapshot에서 원문을 복제하지 않고 canonical source identity와 SHA-256 evidence ref만 남겼으며, 세 개의 추상 패턴은 모두 `CANDIDATE`입니다. Intent_DNA 변경과 `OWNED_ASSET` 승격은 금지되어 있고 에테르니언 검토가 필요합니다. 구현은 보호된 브랜치·PR·CI 절차로 진행합니다.

## 공개 저장소 정책

이 저장소에는 공용 설계문서와 합성 예제만 둡니다. 고객 원본, 운영 DB, 개인정보, 자격증명, 비공개 소스, 내부 가격·계약정보는 저장하지 않습니다.
