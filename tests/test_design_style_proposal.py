from uuid import uuid4

import pytest

from apf.design_style_proposal import (
    PublicObservation,
    StyleDecision,
    StyleProposalError,
    StyleProposalRequest,
    StyleProposalStore,
    inject_preview_style,
    render_style_css,
)


def test_observations_generate_preview_then_apply_with_owner_binding(tmp_path):
    store = StyleProposalStore(tmp_path)
    subject, tenant, owner = str(uuid4()), str(uuid4()), str(uuid4())
    ref = str(uuid4())
    digest = "sha256:" + "a" * 64
    references = {"set_digest": digest, "references": [{"reference_id": ref}]}
    request = StyleProposalRequest(
        based_on_set_digest=digest,
        observations=[PublicObservation(
            reference_id=ref, background="#faf8f1", text="#192b3d",
            accent="#217963", layout="split", density="airy",
        )],
    )
    proposal = store.propose(
        "platform_dialogue", subject, tenant_id=tenant,
        owner_principal_id=owner, references=references, request=request,
    )
    css = render_style_css(proposal["tokens"])
    assert "javascript:" not in css
    assert "grid-template-columns" in css
    assert "<style>" + css + "</style></head>" in inject_preview_style(
        "<html><head></head><body></body></html>", css
    )
    with pytest.raises(StyleProposalError, match="STYLE_NOT_FOUND"):
        store.get("platform_dialogue", subject, tenant_id=tenant,
                  owner_principal_id=str(uuid4()), reference_set_digest=digest)
    with pytest.raises(StyleProposalError, match="STYLE_REFERENCES_STALE"):
        store.get("platform_dialogue", subject, tenant_id=tenant,
                  owner_principal_id=owner, reference_set_digest="sha256:" + "b" * 64)
    applied = store.decide(
        "platform_dialogue", subject, tenant_id=tenant, owner_principal_id=owner,
        reference_set_digest=digest,
        decision=StyleDecision(proposal_digest=proposal["proposal_digest"], decision="APPLY"),
    )
    assert applied["status"] == "APPLIED"
    with pytest.raises(StyleProposalError, match="STYLE_DECISION_STALE"):
        store.decide("platform_dialogue", subject, tenant_id=tenant,
                     owner_principal_id=owner, reference_set_digest=digest,
                     decision=StyleDecision(proposal_digest=proposal["proposal_digest"],
                                            decision="REJECT"))


def test_proposal_rejects_unregistered_reference_and_stale_set(tmp_path):
    store = StyleProposalStore(tmp_path)
    subject, tenant, owner = str(uuid4()), str(uuid4()), str(uuid4())
    digest = "sha256:" + "a" * 64
    request = StyleProposalRequest(
        based_on_set_digest=digest,
        observations=[PublicObservation(reference_id=uuid4(), background="#ffffff",
                                        text="#ffffff", accent="#ffffff")],
    )
    with pytest.raises(StyleProposalError, match="STYLE_REFERENCE_UNKNOWN"):
        store.propose("site_draft", subject, tenant_id=tenant, owner_principal_id=owner,
                      references={"set_digest": digest, "references": []}, request=request)
    with pytest.raises(StyleProposalError, match="STYLE_REFERENCES_STALE"):
        store.propose("site_draft", subject, tenant_id=tenant, owner_principal_id=owner,
                      references={"set_digest": "sha256:" + "b" * 64, "references": []},
                      request=request)
