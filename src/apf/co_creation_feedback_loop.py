"""W3: feedback revision lineage, proposal diff, operator bridge, evolution snapshot."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from .arkaon_self_evolution_compare import ArkaonSelfEvolutionCompareEngine, ImprovementContributor
from .conversational_co_creation import CoCreationPolicy, CoCreationProposal
from .conversational_co_creation_bridge import bridge_co_creation_proposal


class CoCreationFeedbackRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CoCreationFeedbackLoopPolicy:
    enabled: bool = True
    emit_operator_revision_packet: bool = True
    record_evolution_snapshot: bool = True
    max_revisions_per_session: int = 12

    @classmethod
    def load(cls, path: Path) -> CoCreationFeedbackLoopPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.co-creation-feedback-loop/v1":
            raise CoCreationFeedbackRejected("POLICY_SCHEMA", "unsupported feedback loop schema")
        return cls(
            enabled=bool(document.get("enabled", True)),
            emit_operator_revision_packet=bool(document.get("emit_operator_revision_packet", True)),
            record_evolution_snapshot=bool(document.get("record_evolution_snapshot", True)),
            max_revisions_per_session=max(1, int(document.get("max_revisions_per_session", 12))),
        )


@dataclass(frozen=True)
class ProposalRevisionDiff:
    parent_proposal_id: str
    revision_proposal_id: str
    revision_number: int
    sections_added: tuple[str, ...]
    sections_removed: tuple[str, ...]
    routes_added: tuple[str, ...]
    routes_removed: tuple[str, ...]
    diff_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.co-creation-proposal-revision-diff/v1",
            "parent_proposal_id": self.parent_proposal_id,
            "revision_proposal_id": self.revision_proposal_id,
            "revision_number": self.revision_number,
            "sections_added": list(self.sections_added),
            "sections_removed": list(self.sections_removed),
            "routes_added": list(self.routes_added),
            "routes_removed": list(self.routes_removed),
            "diff_digest": self.diff_digest,
        }


@dataclass(frozen=True)
class FeedbackLoopState:
    session_id: str
    root_proposal_id: str
    latest_proposal_id: str
    revision_count: int
    sandbox_id: str | None
    revisions: tuple[dict[str, object], ...]

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.co-creation-feedback-loop/v1",
            "session_id": self.session_id,
            "root_proposal_id": self.root_proposal_id,
            "latest_proposal_id": self.latest_proposal_id,
            "revision_count": self.revision_count,
            "sandbox_id": self.sandbox_id,
            "revisions": list(self.revisions),
        }


def _section_ids(proposal: dict[str, object]) -> frozenset[str]:
    return frozenset(
        str(item.get("section_id", ""))
        for item in proposal.get("template_blueprint") or []
        if isinstance(item, dict) and item.get("section_id")
    )


def _route_refs(proposal: dict[str, object]) -> frozenset[str]:
    return frozenset(
        str(item.get("route_ref", ""))
        for item in proposal.get("platform_blueprint") or []
        if isinstance(item, dict) and item.get("route_ref")
    )


def compare_proposal_documents(
    *,
    parent: dict[str, object],
    revision: dict[str, object],
    revision_number: int,
) -> ProposalRevisionDiff:
    parent_sections = _section_ids(parent)
    revision_sections = _section_ids(revision)
    parent_routes = _route_refs(parent)
    revision_routes = _route_refs(revision)
    body = {
        "parent_proposal_id": parent.get("proposal_id"),
        "revision_proposal_id": revision.get("proposal_id"),
        "revision_number": revision_number,
        "sections_added": sorted(revision_sections - parent_sections),
        "sections_removed": sorted(parent_sections - revision_sections),
        "routes_added": sorted(revision_routes - parent_routes),
        "routes_removed": sorted(parent_routes - revision_routes),
    }
    diff_digest = sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    return ProposalRevisionDiff(
        parent_proposal_id=str(parent.get("proposal_id", "")),
        revision_proposal_id=str(revision.get("proposal_id", "")),
        revision_number=revision_number,
        sections_added=tuple(body["sections_added"]),
        sections_removed=tuple(body["sections_removed"]),
        routes_added=tuple(body["routes_added"]),
        routes_removed=tuple(body["routes_removed"]),
        diff_digest=diff_digest,
    )


class CoCreationFeedbackLoopEngine:
    def __init__(self, *, foundry_root: Path, policy: CoCreationFeedbackLoopPolicy | None = None) -> None:
        self.foundry_root = foundry_root.resolve()
        config = self.foundry_root / "config" / "arkaon-co-creation-feedback-loop.json"
        self.policy = policy or CoCreationFeedbackLoopPolicy.load(config)
        self.proposal_root = self.foundry_root / "state" / "co-creation" / "proposals"
        self.loop_root = self.foundry_root / "state" / "co-creation" / "feedback-loops"
        self.diff_root = self.foundry_root / "state" / "co-creation" / "revision-diffs"
        self.loop_root.mkdir(parents=True, exist_ok=True)
        self.diff_root.mkdir(parents=True, exist_ok=True)

    def _load_proposal_document(self, proposal_id: str) -> dict[str, object]:
        path = self.proposal_root / f"{proposal_id}.json"
        if not path.is_file():
            raise CoCreationFeedbackRejected("PROPOSAL_NOT_FOUND", "proposal not found")
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_proposal_document(self, document: dict[str, object]) -> None:
        proposal_id = str(document["proposal_id"])
        path = self.proposal_root / f"{proposal_id}.json"
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def _load_loop_state(self, session_id: str) -> FeedbackLoopState | None:
        path = self.loop_root / f"{session_id}.json"
        if not path.is_file():
            return None
        document = json.loads(path.read_text(encoding="utf-8"))
        return FeedbackLoopState(
            session_id=str(document["session_id"]),
            root_proposal_id=str(document["root_proposal_id"]),
            latest_proposal_id=str(document["latest_proposal_id"]),
            revision_count=int(document.get("revision_count", 0)),
            sandbox_id=document.get("sandbox_id"),
            revisions=tuple(document.get("revisions") or ()),
        )

    def _save_loop_state(self, state: FeedbackLoopState) -> None:
        path = self.loop_root / f"{state.session_id}.json"
        path.write_text(
            json.dumps(state.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def process_revision(
        self,
        *,
        parent_proposal_id: str,
        revision: CoCreationProposal,
        sandbox_id: str | None,
        feedback_message: str,
        now: datetime,
    ) -> tuple[ProposalRevisionDiff, FeedbackLoopState, dict[str, object] | None]:
        if now.tzinfo is None:
            raise CoCreationFeedbackRejected("TIMESTAMP", "timezone-aware timestamp required")
        if not self.policy.enabled:
            raise CoCreationFeedbackRejected("DISABLED", "feedback loop is disabled")

        parent = self._load_proposal_document(parent_proposal_id)
        loop = self._load_loop_state(revision.session_id)
        revision_number = 1 if loop is None else loop.revision_count + 1
        if revision_number > self.policy.max_revisions_per_session:
            raise CoCreationFeedbackRejected("REVISION_LIMIT", "maximum revisions per session exceeded")

        revision_doc = revision.to_document()
        revision_doc["parent_proposal_id"] = parent_proposal_id
        revision_doc["revision_number"] = revision_number
        revision_doc["root_proposal_id"] = (
            loop.root_proposal_id if loop else parent_proposal_id
        )
        revision_doc["feedback_message"] = feedback_message.strip()[:4000]
        revision_doc["review_status"] = "PROPOSED"
        self._save_proposal_document(revision_doc)

        diff = compare_proposal_documents(parent=parent, revision=revision_doc, revision_number=revision_number)
        diff_path = self.diff_root / f"{diff.revision_proposal_id}.json"
        diff_path.write_text(json.dumps(diff.to_document(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

        revision_entry = {
            "revision_number": revision_number,
            "parent_proposal_id": parent_proposal_id,
            "revision_proposal_id": revision.proposal_id,
            "diff_digest": diff.diff_digest,
            "feedback_message": feedback_message.strip()[:500],
            "recorded_at": now.isoformat(),
        }
        root_id = loop.root_proposal_id if loop else parent_proposal_id
        state = FeedbackLoopState(
            session_id=revision.session_id,
            root_proposal_id=root_id,
            latest_proposal_id=revision.proposal_id,
            revision_count=revision_number,
            sandbox_id=sandbox_id,
            revisions=(*(loop.revisions if loop else ()), revision_entry),
        )
        self._save_loop_state(state)

        evolution_report = None
        if self.policy.record_evolution_snapshot:
            evolution = ArkaonSelfEvolutionCompareEngine(foundry_root=self.foundry_root)
            before = evolution.capture_snapshot(
                contributor=ImprovementContributor.TENANT_FEEDBACK,
                improvement_ref=parent_proposal_id,
                improvement_summary=f"before feedback revision {revision_number}",
                now=now,
            )
            after = evolution.capture_snapshot(
                contributor=ImprovementContributor.TENANT_FEEDBACK,
                improvement_ref=revision.proposal_id,
                improvement_summary=f"after feedback: {feedback_message.strip()[:120]}",
                now=now,
            )
            evolution_report = evolution.compare(
                baseline_snapshot_id=before.snapshot_id,
                candidate_snapshot_id=after.snapshot_id,
                now=now,
            ).to_document()

        inbox_path = None
        if self.policy.emit_operator_revision_packet:
            chat_policy = CoCreationPolicy.load(
                self.foundry_root / "config" / "arkaon-conversational-co-creation.json"
            )
            paths = bridge_co_creation_proposal(
                foundry_root=self.foundry_root,
                proposal=revision,
                policy=chat_policy,
                run_id=f"rev{revision_number}-{revision.proposal_id}",
                now=now,
                dry_run=False,
            )
            inbox_path = paths[0] if paths else None

        result = {
            "diff": diff.to_document(),
            "feedback_loop": state.to_document(),
            "evolution_comparison": evolution_report,
            "operator_inbox_path": inbox_path,
        }
        return diff, state, result
