from uuid import uuid4

import pytest
from pydantic import ValidationError

from apf.design_reference_urls import (
    DesignReferenceBatch,
    DesignReferenceError,
    DesignReferenceInput,
    DesignReferenceStore,
    canonical_public_url,
)


def batch(*urls, digest=None):
    return DesignReferenceBatch(
        urls=[DesignReferenceInput(url=url, focus="색상·간격") for url in urls],
        based_on_digest=digest,
    )


def test_urls_append_in_four_at_a_time_with_owner_and_revision_binding(tmp_path):
    store = DesignReferenceStore(tmp_path)
    subject, tenant, owner = str(uuid4()), str(uuid4()), str(uuid4())
    first = store.append(
        "site_draft", subject, tenant_id=tenant, owner_principal_id=owner,
        batch=batch("https://example.com/", "https://other.example.com/a",
                    "https://third.example.com/", "https://fourth.example.com/"),
    )
    assert len(first["references"]) == 4
    assert first["capture_performed"] is False and first["style_applied"] is False
    second = store.append(
        "site_draft", subject, tenant_id=tenant, owner_principal_id=owner,
        batch=batch("https://fifth.example.com/", digest=first["set_digest"]),
    )
    assert len(second["references"]) == 5
    with pytest.raises(DesignReferenceError, match="STALE"):
        store.append(
            "site_draft", subject, tenant_id=tenant, owner_principal_id=owner,
            batch=batch("https://sixth.example.com/", digest=first["set_digest"]),
        )
    with pytest.raises(DesignReferenceError, match="NOT_FOUND"):
        store.get(
            "site_draft", subject, tenant_id=tenant, owner_principal_id=str(uuid4())
        )
    with pytest.raises(ValidationError):
        batch(*(f"https://{n}.example.com/" for n in range(5)))


@pytest.mark.parametrize("url", [
    "http://example.com/",
    "https://localhost/",
    "https://127.0.0.1/",
    "https://[::1]/",
    "https://example.local/",
    "https://user:pass@example.com/",
    "https://example.com/?token=secret",
    "https://example.com:8443/",
    "javascript:alert(1)",
    "https://example.com/\nHost:local",
])
def test_public_https_only(url):
    with pytest.raises(DesignReferenceError):
        canonical_public_url(url)


def test_duplicate_and_limit_fail_without_partial_write(tmp_path):
    store = DesignReferenceStore(tmp_path)
    subject, tenant, owner = str(uuid4()), str(uuid4()), str(uuid4())
    doc = store.append(
        "platform_dialogue", subject, tenant_id=tenant, owner_principal_id=owner,
        batch=batch("https://example.com/"),
    )
    with pytest.raises(DesignReferenceError, match="DUPLICATE"):
        store.append(
            "platform_dialogue", subject, tenant_id=tenant, owner_principal_id=owner,
            batch=batch("https://example.com/#top", digest=doc["set_digest"]),
        )
    assert store.get(
        "platform_dialogue", subject, tenant_id=tenant, owner_principal_id=owner
    )["set_digest"] == doc["set_digest"]
