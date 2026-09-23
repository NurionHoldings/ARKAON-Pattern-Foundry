from uuid import uuid4
from xml.etree import ElementTree

import pytest

from apf.logo_draft import LogoDraftError, LogoDraftRequest, LogoDraftStore
from apf.logo_motion import animate_generated_logo


def test_animated_logo_is_owner_bound_and_reduced_motion_safe(tmp_path):
    store = LogoDraftStore(tmp_path)
    tenant, owner = str(uuid4()), str(uuid4())
    draft = store.create(
        tenant_id=tenant,
        owner_principal_id=owner,
        request=LogoDraftRequest(name="마루", tagline="편안한 하루", color="#2563eb", shape="orbit"),
    )
    static, _ = store.download(draft["draft_id"], tenant_id=tenant, owner_principal_id=owner)
    for motion in ("float", "pulse", "spin"):
        animated, filename = store.animated_download(
            draft["draft_id"], tenant_id=tenant, owner_principal_id=owner, motion=motion
        )
        ElementTree.fromstring(animated)
        assert "prefers-reduced-motion:reduce" in animated
        assert "@keyframes apf-logo-motion" in animated
        assert filename.endswith(f"-{motion}.svg")
    assert "apf-motion-mark" not in static
    with pytest.raises(LogoDraftError, match="NOT_FOUND"):
        store.animated_download(
            draft["draft_id"], tenant_id=tenant, owner_principal_id=str(uuid4()), motion="float"
        )
    with pytest.raises(ValueError, match="LOGO_MOTION_INVALID"):
        animate_generated_logo(static, "script")
