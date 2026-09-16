"""Tenant/branch hierarchy used by ARKAON staged rollout.

Slim analog of NARANG RIDER branch registry. Ledger, personal data, and
scope-authorizer surfaces are not transplanted.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum


class BranchType(StrEnum):
    HEADQUARTERS = "HEADQUARTERS"
    REGIONAL_BRANCH = "REGIONAL_BRANCH"
    LOCAL_HUB = "LOCAL_HUB"


class BranchStatus(StrEnum):
    PROVISIONING = "PROVISIONING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


@dataclass(frozen=True)
class ServiceArea:
    area_code: str
    province_code: str
    municipality_code: str

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (self.area_code, self.province_code, self.municipality_code)
        ):
            raise ValueError("SERVICE_AREA_IDENTITY_REQUIRED")


@dataclass(frozen=True)
class Branch:
    branch_id: str
    branch_type: BranchType
    name: str
    parent_branch_id: str | None
    status: BranchStatus
    service_areas: tuple[ServiceArea, ...]
    policy_version: int
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.branch_id.strip() or not self.name.strip() or self.created_at.tzinfo is None:
            raise ValueError("BRANCH_IDENTITY_REQUIRED")
        if self.policy_version < 1:
            raise ValueError("BRANCH_POLICY_VERSION_REQUIRED")
        if self.branch_type is BranchType.HEADQUARTERS and self.parent_branch_id is not None:
            raise ValueError("HEADQUARTERS_CANNOT_HAVE_PARENT")
        if self.branch_type is not BranchType.HEADQUARTERS and not self.parent_branch_id:
            raise ValueError("NON_HEADQUARTERS_PARENT_REQUIRED")


class BranchRegistry:
    def __init__(self) -> None:
        self._branches: dict[str, Branch] = {}
        self._area_owner: dict[str, str] = {}

    def register(self, branch: Branch) -> Branch:
        if branch.branch_id in self._branches:
            raise ValueError("DUPLICATE_BRANCH")
        if branch.parent_branch_id is not None:
            parent = self.get(branch.parent_branch_id)
            if branch.branch_type is BranchType.REGIONAL_BRANCH:
                if parent.branch_type is not BranchType.HEADQUARTERS:
                    raise ValueError("REGIONAL_BRANCH_REQUIRES_HEADQUARTERS")
            elif parent.branch_type is not BranchType.REGIONAL_BRANCH:
                raise ValueError("LOCAL_HUB_REQUIRES_REGIONAL_BRANCH")
        for area in branch.service_areas:
            if area.area_code in self._area_owner:
                raise ValueError("OVERLAPPING_SERVICE_AREA")
        self._branches[branch.branch_id] = branch
        for area in branch.service_areas:
            self._area_owner[area.area_code] = branch.branch_id
        return branch

    def activate(self, *, branch_id: str, expected_policy_version: int) -> Branch:
        branch = self.get(branch_id)
        if branch.policy_version != expected_policy_version:
            raise ValueError("BRANCH_POLICY_VERSION_CONFLICT")
        if branch.status is BranchStatus.SUSPENDED:
            raise ValueError("SUSPENDED_BRANCH_REQUIRES_HUMAN_REINSTATEMENT")
        activated = replace(branch, status=BranchStatus.ACTIVE)
        self._branches[branch_id] = activated
        return activated

    def get(self, branch_id: str) -> Branch:
        try:
            return self._branches[branch_id]
        except KeyError as exc:
            raise ValueError("BRANCH_NOT_FOUND") from exc

    def descendants(self, branch_id: str) -> tuple[str, ...]:
        descendants: list[str] = []
        pending = [branch_id]
        while pending:
            parent = pending.pop()
            children = sorted(
                branch.branch_id
                for branch in self._branches.values()
                if branch.parent_branch_id == parent
            )
            descendants.extend(children)
            pending.extend(children)
        return tuple(descendants)
