# 주거형 요양시설 검산과 이미지 생성 요청

사용자 요구 → 정원·화장실 검산 → 필수·요청 공간 검토 → 면적 예산 → 사용자 구성 확인 → 장면별 이미지 요청 → 결과 대조를 하나의 제안 흐름으로 연결한다.

## 실행

- 인증된 콘솔 `/console`에서 요양원 설계 검산 링크 → `/console/care-facility`.
- 인증과 CSRF가 적용된 `POST /v1/console/care-facility/plan`.
- CLI `python -m apf.care_facility_design examples/thearirang-care-49-brief.json`.
- 첫 결과의 `brief_digest`를 사용자가 확인한 후 `--confirmed-digest DIGEST`와 `--scene overview|bedroom|staff_support|kitchen_bathing`을 전달한다.

정원 불일치·전용WC 누락·검토 공간 누락·알려진 면적 초과는 요청문 생성을 막는다. 요구 변경 시 이전 digest는 일치하지 않는다. 승인 digest는 입력 구성 확인이며 법적 승인·결제권한·프로젝트 권한·배포권한 증명이 아니다.

`known_budget_m2`는 화장실과 침실, 조리실과 식당을 중복 산정하지 않는다. 일부 면적이 없으면 `area_budget_complete=false`이며 잔여 면적을 확정하지 않는다. 총면적 여유가 있어도 실제 배치, 외기창, 화장실 접근, 계단·피난·배관을 검증했다고 표시하지 않는다.

기본 검토 목록은 법정 예외를 자동 해석하는 법규 엔진이 아니다. 직원 휴게·탈의와 남녀 목욕 구분은 프로젝트 요청을 포함한 보수적인 준비 목록이다. 공식 최신 근거·관할 해석은 별도 확인한다.

프로젝트 사례는 `examples/`에, 재사용 사고 과정은 `knowledge/workflows/`에 분리한다. 고객 전용 사례를 공식 공용 자산이나 학습 완료 모델로 자동 승격하지 않는다. 이 구현은 결정론적 검산과 프롬프트 패킷 생성이며 모델 가중치 학습이 아니다.

본 기능은 로컬 입력만 계산하며 영속 저장·외부 이미지 제공자 호출·자동 배포·Intent_DNA 변경·HOLD 해제를 하지 않는다. 기존 이미지 생성 실행 경로로 넘길 때 해당 경로의 권한·승인·출처·이용범위 검사를 그대로 적용해야 한다.
