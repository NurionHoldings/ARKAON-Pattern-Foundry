# ARKAON 화면·콘텐츠·운영 정합성 감사 (Pattern Foundry #048)

조회일: 2026-09-17  
상태: NARANG_RIDER `feat/086-arkaon-experience-operations-audit` (`0695dd9`) clean-room analog.

## 역할

ARKAON은 단순 장애감시를 넘어 다음 역할을 함께 수행합니다.

- **콘텐츠 편집자**: 홈 문구, 정보 배치, 장문·중복·모순 안내
- **UX 감사자**: 제목·헤딩 계층, 역할별 핵심 행동, 대비 4.5:1, 터치 44px, 모바일 가로 넘침
- **경쟁기능 분석가**: 공식 HTTPS 근거의 유사 플랫폼 신규 기능 비교 (복제 금지)
- **운영 일관성 감시자**: Frontend–API–정책–페이지 경로 정합성, 끊어진 링크

## 심각도

| 심각도 | 예시 |
|--------|------|
| BLOCKER | 끊어진 경로, API·정책 불일치 |
| HIGH | 홈 필수기능 누락, 헤딩·접근성 문제 |
| MEDIUM | 장문 문구, 핵심 행동 중복 |
| LOW | 타 플랫폼 우수기능 비교 후보 |

## 즉시의 의미

즉시 = 운영화면 자동 변경 **아님**.  
관리자 검토함(`inbox/research`)에 **IMPROVEMENT_PROPOSAL** 제안서를 바로 생성합니다.

각 제안서에는 다음이 포함됩니다.

- 발견 위치
- 증거 SHA-256 (`evidence_digest`, `proposal_digest`)
- 사용자에게 미치는 영향
- 권장 수정안
- 필요한 합성시험
- 사람 검토 필요 여부

## 경계

- 최대 권한: `IMPROVEMENT_PROPOSAL`
- `operator-decision` 자동 이동 금지 (에테르니언 검토 선행)
- 공식 HTTPS 근거만 허용, 문구·디자인·코드·브랜드 복제 금지
- 인석형 승인·미리보기·시험계획 확인 후 검토 브랜치에만 반영

## 구현

```text
src/apf/experience_operations_audit.py   # 감사 엔진
src/apf/experience_audit_bridge.py       # 플랫폼 공개 메타 → 감사 입력
config/arkaon-experience-operations-audit.json
tests/test_experience_operations_audit.py
```

중앙 오케스트레이터는 플랫폼 분석 후 `candidate_commit`에 바인딩된 경험·운영 감사를 실행하고,
발견 시 `inbox/research`에 제안 JSON을 기록합니다.
