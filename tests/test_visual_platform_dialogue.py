import json
from uuid import uuid4

import pytest

from apf.visual_platform_dialogue import (
    PlatformBrief,
    RevisionFeedback,
    RevisionSubmission,
    UnderstandingConfirmation,
    VisualDialogueError,
    VisualPlatformDialogueStore,
)

CONFIRMATIONS = {
    "purpose", "audience", "screen_flow", "data_permissions", "cost_and_payment"
}


def brief():
    return PlatformBrief(
        name="부업장터", purpose="지속 가능한 벌거리를 연결한다.",
        audience=["일거리 제공자", "참여자"],
        required_capabilities=["벌거리 탐색", "지원", "정산"],
        constraints=["모바일 우선", "개인정보 최소화"],
    )


def revision(base=None, title="홈"):
    return RevisionSubmission(
        based_on_revision_digest=base,
        change_summary="핵심 이용 흐름을 화면으로 구성",
        screens=[{
            "screen_id": "home", "title": title, "purpose": "맞춤 벌거리 탐색",
            "components": ["검색", "추천 벌거리", "내 지원 현황"],
        }],
    )


def setup(tmp_path):
    store = VisualPlatformDialogueStore(tmp_path)
    tenant, owner = str(uuid4()), str(uuid4())
    created = store.create(tenant_id=tenant, owner_principal_id=owner, brief=brief())
    return store, tenant, owner, created["dialogue_id"]


def test_visual_revision_feedback_regeneration_and_seal(tmp_path):
    store, tenant, owner, dialogue_id = setup(tmp_path)
    first = store.submit_revision(dialogue_id, tenant_id=tenant, submission=revision())
    image = store.image(dialogue_id, 1, tenant_id=tenant)
    assert b"<svg" in image and "부업장터".encode() in image

    store.add_feedback(
        dialogue_id, tenant_id=tenant, owner_principal_id=owner,
        feedback=RevisionFeedback(
            revision_digest=first["revision_digest"], instruction="정산 현황을 홈에 추가"
        ),
    )
    second = store.submit_revision(
        dialogue_id, tenant_id=tenant,
        submission=revision(first["revision_digest"], title="홈·정산"),
    )
    assert second["based_on_revision_digest"] == first["revision_digest"]
    assert second["image_digest"] != first["image_digest"]

    confirmation = store.confirm(
        dialogue_id, tenant_id=tenant, owner_principal_id=owner,
        confirmation=UnderstandingConfirmation(
            revision_digest=second["revision_digest"], confirmed_items=CONFIRMATIONS
        ),
    )
    manifest = store.seal(
        dialogue_id, tenant_id=tenant, owner_principal_id=owner
    )
    assert manifest["confirmation_digest"] == confirmation["confirmation_digest"]
    assert manifest["implementation_allowed"] is False
    assert manifest["deployment_allowed"] is False
    assert store.get(dialogue_id, tenant_id=tenant)["state"] == "SPEC_SEALED"


def test_stale_revision_and_incomplete_understanding_are_blocked(tmp_path):
    store, tenant, owner, dialogue_id = setup(tmp_path)
    first = store.submit_revision(dialogue_id, tenant_id=tenant, submission=revision())
    with pytest.raises(VisualDialogueError, match="NOT_EXPECTED"):
        store.submit_revision(dialogue_id, tenant_id=tenant, submission=revision())
    with pytest.raises(VisualDialogueError, match="INCOMPLETE"):
        store.confirm(
            dialogue_id, tenant_id=tenant, owner_principal_id=owner,
            confirmation=UnderstandingConfirmation(
                revision_digest=first["revision_digest"], confirmed_items={"purpose"}
            ),
        )
    with pytest.raises(VisualDialogueError, match="NOT_CONFIRMABLE"):
        store.seal(dialogue_id, tenant_id=tenant, owner_principal_id=owner)


def test_tenant_owner_and_image_tamper_boundaries(tmp_path):
    store, tenant, _, dialogue_id = setup(tmp_path)
    first = store.submit_revision(dialogue_id, tenant_id=tenant, submission=revision())
    with pytest.raises(VisualDialogueError, match="NOT_FOUND"):
        store.get(dialogue_id, tenant_id=str(uuid4()))
    with pytest.raises(VisualDialogueError, match="OWNER_MISMATCH"):
        store.add_feedback(
            dialogue_id, tenant_id=tenant, owner_principal_id=str(uuid4()),
            feedback=RevisionFeedback(
                revision_digest=first["revision_digest"], instruction="권한 없는 수정"
            ),
        )
    image_path = tmp_path / "state/visual-platform-images" / dialogue_id / "v1.svg"
    image_path.write_text("tampered", encoding="utf-8")
    with pytest.raises(VisualDialogueError, match="IMAGE_TAMPERED"):
        store.image(dialogue_id, 1, tenant_id=tenant)


def test_dialogue_ledger_tamper_is_detected(tmp_path):
    store, tenant, _, dialogue_id = setup(tmp_path)
    path = tmp_path / "state/visual-platform-dialogues" / f"{dialogue_id}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["automatic_deployment"] = True
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(VisualDialogueError, match="TAMPERED"):
        store.get(dialogue_id, tenant_id=tenant)
    assert store.list_for_owner(tenant_id=tenant, owner_principal_id=str(uuid4())) == []


def test_duplicate_screen_identity_is_rejected(tmp_path):
    store, tenant, _, dialogue_id = setup(tmp_path)
    duplicate = RevisionSubmission(
        based_on_revision_digest=None,
        change_summary="중복 화면",
        screens=[
            {"screen_id": "home", "title": "홈1", "purpose": "탐색", "components": ["검색"]},
            {"screen_id": "home", "title": "홈2", "purpose": "정산", "components": ["정산"]},
        ],
    )
    with pytest.raises(VisualDialogueError, match="SCREEN_ID_DUPLICATE"):
        store.submit_revision(dialogue_id, tenant_id=tenant, submission=duplicate)
