# 자산획득 작업 오케스트레이터 (#034)

## 목적

`AcquisitionJob`은 사용자 매개 인증 게이트(#032)와 권한 기반 소재 처리(#033)를 하나의 재시작 가능한 작업으로 결합한다. 네트워크 클라이언트나 자격증명 저장소가 아니라 검증·순서·감사 경계다.

## 결합 경계

- 불변 `request_fingerprint`는 tenant, principal, correlation, idempotency, 인증요청 및 소재요청을 포함한다.
- `job_fingerprint`는 request 지문과 job ID를 포함한다.
- 각 preflight, user-action, rights, collection, sanitized-input, originality 증거에는 외부 검토자의 `JobEvidenceBinding`을 추가한다.
- 결합 서명은 job/request/tenant/principal/stage/evidence/expiry/nonce를 포괄한다. 다른 작업이나 고객의 증거는 재사용할 수 없다.
- 오케스트레이터에는 공개키만 주입한다. 서명용 개인키와 원문 인증정보를 제공하지 않는다.

## 상태

정상 경로는 다음과 같다.

`QUEUED → AUTH_PREFLIGHT_REQUIRED → USER_ACTION_REQUIRED(필요시) → RIGHTS_REVIEW → COLLECTION_REVIEW → READY_TO_CAPTURE → SANITIZE → NORMALIZE → ORIGINALITY_REVIEW → ASSET_CANDIDATE`

인증이 필요 없는 작업은 `QUEUED`에서 `RIGHTS_REVIEW`로 진행한다. 검토·거부·격리·만료·취소·실패 상태는 각각 `ETHERNIAN_REVIEW`, `DENIED`, `QUARANTINED`, `EXPIRED`, `CANCELLED`, `FAILED`로 분리한다. 취소와 다른 terminal 상태는 재개할 수 없다.

## 수집 인터페이스

오케스트레이터는 외부 웹 요청을 실행하지 않는다. 승인된 수집기가 만든 `SanitizedInputEnvelope`만 받는다. envelope에는 제거 처리가 끝난 본문·HAR·DOM·source map과 다음 두 항목만 포함한다.

- `quarantine:<uuid>` 형식의 일시 격리 참조
- `sha256:<digest>` 형식의 원문 해시

원문, ID, 비밀번호, cookie, bearer token 및 세션은 이벤트 원장에 기록하지 않는다. 비정제 envelope는 격리 처리한다.

## 원장과 복구

- 이벤트는 sequence, 이전 이벤트 해시, 작업 지문, 상태, version, timestamp 및 비밀이 아닌 payload 지문으로 해시 체인을 이룬다.
- command ID와 payload 지문이 같으면 기존 receipt를 반환한다. 같은 ID의 다른 payload는 충돌로 거부한다.
- 예상 version이 다르면 stale update로 거부한다.
- 명령은 작업, 인증 게이트, 소재 파이프라인, nonce, 증거 만료목록 및 receipt를 하나의 원자적 변경 단위로 처리한다. 입력·서명·순서 검증 실패 시 이 전부와 event/version은 명령 전 상태로 복구되므로 같은 command ID와 교정된 입력으로 재시도할 수 있다.
- 권리 거부, 비밀·개인정보 유출, 만료처럼 정책이 terminal 상태를 요구하는 실패만 rollback 후 `COMMAND_REJECTED` 이벤트 하나로 확정한다. 이 경우 재개하지 않고 새 작업을 요청해야 한다.
- 유효하게 서명된 검토 결과가 `REVIEW`이면 검증된 nonce와 해당 내부 게이트의 검토 상태를 보존하고 `COMMAND_REVIEW_REQUIRED` 이벤트 하나로 `ETHERNIAN_REVIEW`를 확정한다. 같은 명령의 재실행은 원장을 추가하지 않고 상태 규칙으로 차단한다.
- 하위 인증 게이트의 `REVOKED`는 job의 `CANCELLED` 정책 결과로 매핑되어 있으나, 현재 공개 명령 API는 하위 게이트를 직접 revoke하지 않으므로 실제 취소는 `AcquisitionJob.cancel()` 경로만 사용한다.
- 복구 시 전체 원장의 변조·절단·순서와 현재 만료시간을 다시 검증한다.
- 이벤트 metadata에는 소재 본문이 아니라 증거 지문만 기록한다.

## 승격 제한

오케스트레이터의 최종 산출물은 라이선스 의무와 출처 해시를 가진 `CANDIDATE_NOT_OWNED_ASSET`이다. 소유 자산 승격 상태와 API는 의도적으로 제공하지 않는다.
