import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_home_services_catalog_links_exist() -> None:
    catalog_path = ROOT / "config" / "arkaon-home-services.json"
    document = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert document["schema_version"] == "apf.home-services/v1"
    assert len(document["services"]) == 8
    for service in document["services"]:
        href = service["href"]
        assert href.startswith("/")
        relative = href.lstrip("/")
        target = ROOT / relative
        assert target.is_file(), f"missing page for {service['id']}: {href}"
