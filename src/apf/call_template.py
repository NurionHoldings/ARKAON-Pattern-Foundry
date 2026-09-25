"""Deterministic, reviewable template assets for a shared voice-and-screen session.

The module generates a specification. It neither places calls nor publishes a page.
"""

from __future__ import annotations

import json
import re
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, Field, model_validator

_SLUG = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
_MENU_IDS = ("introduction", "purpose", "materials", "next_step")


class CallTemplateError(ValueError):
    """A template cannot be compiled without a safe, coherent contract."""


class CallTemplateRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    owner_id: str = Field(min_length=1, max_length=128)
    slug: str = Field(min_length=1, max_length=40)
    display_name: str = Field(min_length=1, max_length=80)
    introduction: str = Field(min_length=1, max_length=500)
    purpose_prompts: list[str] = Field(min_length=1, max_length=8)
    material_titles: list[str] = Field(default_factory=list, max_length=12)
    allow_call_request: bool = True

    @model_validator(mode="after")
    def validate_content(self) -> CallTemplateRequest:
        if not _SLUG.fullmatch(self.slug):
            raise ValueError("INVALID_SLUG")
        values = [self.display_name, self.introduction, *self.purpose_prompts, *self.material_titles]
        if any(
            not value.strip() or len(value) > 500 or "<" in value or ">" in value
            for value in values
        ):
            raise ValueError("EMPTY_OR_MARKUP_CONTENT")
        if any(len(value) > 120 for value in [self.display_name, *self.purpose_prompts, *self.material_titles]):
            raise ValueError("LABEL_TOO_LONG")
        if len({value.strip() for value in self.purpose_prompts}) != len(self.purpose_prompts):
            raise ValueError("DUPLICATE_PURPOSE")
        if len({value.strip() for value in self.material_titles}) != len(self.material_titles):
            raise ValueError("DUPLICATE_MATERIAL")
        return self


class MenuAsset(BaseModel):
    menu_id: str
    title: str
    synchronization: Literal["shared_navigation"] = "shared_navigation"
    visibility: Literal["both"] = "both"
    actions: list[str]


class CallTemplateAsset(BaseModel):
    schema_version: Literal["apf.call-template/1.0"] = "apf.call-template/1.0"
    tenant_id: str
    owner_id: str
    slug: str
    display_name: str
    introduction: str
    purpose_prompts: list[str]
    material_titles: list[str]
    menus: list[MenuAsset]
    session_contract: dict[str, object]
    publication_state: Literal["DRAFT"] = "DRAFT"
    telephony_state: Literal["NOT_CONNECTED"] = "NOT_CONNECTED"
    implementation_allowed: bool = False
    deployment_allowed: bool = False
    content_digest: str


def build_call_template(request: CallTemplateRequest) -> CallTemplateAsset:
    """Compile an owner-scoped draft; the digest identifies exact content."""
    menus = [
        MenuAsset(menu_id="introduction", title="소개", actions=["read"]),
        MenuAsset(menu_id="purpose", title="용건", actions=["visitor_write", "owner_read"]),
        MenuAsset(menu_id="materials", title="자료", actions=["read", "user_initiated_download"]),
        MenuAsset(menu_id="next_step", title="다음 단계", actions=["request_call", "owner_decide"]
        if request.allow_call_request
        else ["leave_message", "owner_decide"]),
    ]
    if tuple(menu.menu_id for menu in menus) != _MENU_IDS:
        raise CallTemplateError("MENU_CONTRACT_INVALID")
    document = {
        "schema_version": "apf.call-template/1.0",
        "tenant_id": request.tenant_id,
        "owner_id": request.owner_id,
        "slug": request.slug,
        "display_name": request.display_name.strip(),
        "introduction": request.introduction.strip(),
        "purpose_prompts": [value.strip() for value in request.purpose_prompts],
        "material_titles": [value.strip() for value in request.material_titles],
        "menus": [menu.model_dump(mode="json") for menu in menus],
        "session_contract": {
            "participants": ["owner", "visitor"],
            "menu_navigation": "server_authorized_broadcast_to_both",
            "form_editing": "field_role_authorized",
            "conflict_resolution": "explicit_review_required",
            "file_download": "each_participant_explicit_action",
            "reconnect": "requires_session_reauthorization",
        },
        "publication_state": "DRAFT",
        "telephony_state": "NOT_CONNECTED",
        "implementation_allowed": False,
        "deployment_allowed": False,
    }
    encoded = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return CallTemplateAsset(**document, content_digest="sha256:" + sha256(encoded.encode()).hexdigest())
