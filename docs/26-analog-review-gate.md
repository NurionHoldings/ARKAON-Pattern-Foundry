# #037 #031 에테르니언 검토 게이트

`src/apf/analog_review.py`는 #031의 세 유사 합성 후보를 다시 검증하고 후보별 결정적
검토 패킷을 만든다. 패킷은 요청, 후보 내용, 출처 lineage, 정책 버전, Git revision과
다음 일곱 검사를 결합한다.

- lineage 독립성
- 공식 근거
- 유사성 경계
- 출처 누출 방지
- 권리·라이선스 태세
- 보안 경계
- 합성 테스트

ARKAON 측 `AnalogReviewEvaluator`에는 Ed25519 공개키만 주어진다. 개인키를 가진 외부
에테르니언 검토자가 `APPROVE`, `REVIEW`, `DENY` 중 하나를 서명한다. 서명은 request,
packet, candidate, content, lineage, policy, revision, expiry, nonce에 묶이며 변조·다른
후보/키/리비전 사용·만료·재사용은 실패한다.

`APPROVE`의 의미는 `APPROVED_FOR_PATTERN_PROMOTION`이다. 이것은 다음 심사 단계로
이동할 자격일 뿐이며 `OWNED_ASSET`이 아니다. 어떤 결과도 Intent_DNA를 변경하거나
MJN에 쓰지 않는다. 현재 저장소에는 실제 외부 서명 결정이 체크인되어 있지 않으므로
#031 후보는 여전히 검토 대기 상태다.
