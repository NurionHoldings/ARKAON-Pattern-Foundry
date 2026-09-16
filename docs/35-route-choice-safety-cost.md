# 라이더 경로 선택권·안전·비용 투명성 (Pattern Foundry)

조회일: 2026-09-16
상태: NARANG RIDER `feat/068` 아날로그. 최단거리 강요와 이탈 제재는 **금지**. 운영 활성화는 **BLOCKED**.

## 원칙

라이더는 매 배송마다 경로를 고른다. ARKAON은 안전·균형·최저비용·최단 기준의 설명 가능한
추천만 제공한다. 최단거리 대안이 있어도 자동 선택하지 않고, 예상경로 이탈을 부정행위나
보수 삭감 근거로 쓰지 않는다. 수락된 보수는 하한이며 추가비용은 검토용 보충액으로만
표시한다.

오토바이 적합성은 공식 확인이 없으면 거부한다. 허위·만료 위험고지와 묶음배송 우회 한도
초과는 fail-closed다. 오프라인 안내는 주소·좌표·타일을 저장하지 않고 자동 선택하지 않는다.

## 추적성

| 요구사항 | 구현 | 시험 |
|---|---|---|
| 비용 투명·보수 하한 | RouteChoiceService.evaluate | test_transparent_cost_return_and_supplement_never_cut_accepted_pay |
| 다중 비교·최단 미강요 | compare | test_rider_objective_controls_ranking_and_shortest_is_never_forced |
| 이탈 비제재 | assess_deviation | test_route_deviation_is_never_a_penalty |
