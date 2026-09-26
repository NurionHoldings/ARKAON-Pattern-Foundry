# ARKAON 공개 Surface 관찰·구조 디코딩 (Pattern Foundry #051)

조회일: 2026-09-17  
상태: 복제 목적이 아닌 **개선점 발견**을 위한 lawful indirect observation analog.

## 역할

ARKAON은 타 업체 코드·브랜드·문구를 **복제하지 않습니다**. 대신 공개 surface에서:

- OpenAPI·route·정책 참조
- 공개 frontend JS **구조** (import/export, route ref, fetch pattern)
- minified JS **난독화 해제(escape·comment strip·whitespace collapse)** 후 structure digest

만 기록해 “좋은 눈”을 제공합니다.

## 우회적 기술의 경계

| 허용 | 금지 |
|------|------|
| 공개 HTTPS·등록 workspace 파일 parser-only 분석 | 접근통제·인증 우회 |
| unicode/hex escape 디코딩 (구조 가독) | eval·Function 실행 |
| identifier shape 추상화 (idS/idM/idL) | 경쟁사 원문 verbatim 저장 |
| STRUCTURAL_OBSERVATION digest | member/order/location/payment 등 운영 데이터 |

`PUBLIC_OBSERVATION` rights posture. **copy_prohibited=true** 고정.

## 구현

```text
src/apf/static_js_normalizer.py       # parser-only de-obfuscation + structure digest
src/apf/public_surface_observer.py    # platform surface inventory
src/apf/public_surface_bridge.py      # inbox/research + optional reflective seed
config/arkaon-public-surface-observation.json
state/surface-observations/
tests/test_static_js_normalizer.py
tests/test_public_surface_observer.py
```

## 오케스트레이터

등록 플랫폼 분석 후 `observe_public_surface()` → `inbox/research/*-surface.json`.
