from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree

from apf.name_at import Media, NameAtRegistry, ProfileError


def registry(path: Path) -> NameAtRegistry:
    return NameAtRegistry(path / "profiles.sqlite3", origin="https://profiles.example", media_host="media.example")


def test_owner_approval_search_collision_and_withdrawal():
    with TemporaryDirectory() as directory:
        service = registry(Path(directory))
        first = service.save_draft(tenant_id="tenant", owner_id="a", display_name="홍길동",
                                   introduction="목공 작업", images=[Media("https://media.example/a.jpg", "작업 사진")])
        second = service.save_draft(tenant_id="tenant", owner_id="b", display_name="홍길동",
                                    introduction="영상 제작", images=[])
        assert service.search("홍길동@") == []
        for owner, item in (("a", first), ("b", second)):
            service.publish(tenant_id="tenant", owner_id=owner, profile_id=item["id"],
                            expected_revision=1, approved_digest=service.digest(item))
        assert len(service.search("홍길동@")) == 2
        assert len(ElementTree.fromstring(service.sitemap())) == 2
        service.withdraw(tenant_id="tenant", owner_id="a", profile_id=first["id"])
        assert len(service.search("홍길동@")) == 1
        assert service.discovery_jobs(first["id"])[0]["action"] == "deleted"


def test_stale_or_other_owner_approval_cannot_publish():
    with TemporaryDirectory() as directory:
        service = registry(Path(directory))
        draft = service.save_draft(tenant_id="tenant", owner_id="a", display_name="김하나",
                                   introduction="소개", images=[])
        for owner, digest in (("b", service.digest(draft)), ("a", "sha256:" + "0" * 64)):
            try:
                service.publish(tenant_id="tenant", owner_id=owner, profile_id=draft["id"],
                                expected_revision=1, approved_digest=digest)
            except ProfileError:
                pass
            else:
                raise AssertionError("unapproved publication")
        assert service.search("김하나@") == []


def test_media_limit_and_host_restriction():
    with TemporaryDirectory() as directory:
        service = registry(Path(directory))
        for images in ([Media("https://media.example/a", "a")] * 4,
                       [Media("https://other.example/a", "a")]):
            try:
                service.save_draft(tenant_id="t", owner_id="a", display_name="이름",
                                   introduction="소개", images=images)
            except ProfileError:
                pass
            else:
                raise AssertionError("invalid media accepted")
