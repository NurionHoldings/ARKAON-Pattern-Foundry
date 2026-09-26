"""Unified mailbox: ARKAON stores needs; visitors deliver to user; approval queues fulfillment."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from hashlib import sha256
from pathlib import Path


class MailboxRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class MailboxItemStatus(str, Enum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    USER_APPROVED = "USER_APPROVED"
    FULFILLED = "FULFILLED"
    REJECTED = "REJECTED"


class VisitorKind(str, Enum):
    ETERNIAN = "eternian"
    BEOM = "beom"


class FulfillmentAssignee(str, Enum):
    ETERNIAN = "eternian"
    BEOM = "beom"


@dataclass(frozen=True)
class MailboxDeliveryPolicy:
    automatic_fulfill_allowed: bool = False
    production_change_allowed: bool = False
    visitor_role_eternian: str = "reviewer"
    visitor_role_beom: str = "operator"
    user_recipient_role: str = "operator"

    @classmethod
    def load(cls, path: Path) -> MailboxDeliveryPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.arkaon-mailbox-delivery/v1":
            raise MailboxRejected("POLICY_SCHEMA", "unsupported mailbox delivery schema")
        if document.get("automatic_fulfill_allowed") or document.get("production_change_allowed"):
            raise MailboxRejected("POLICY_FORBIDDEN", "mailbox delivery must remain approval-gated")
        roles = document.get("visitor_roles") or {}
        return cls(
            automatic_fulfill_allowed=bool(document.get("automatic_fulfill_allowed")),
            production_change_allowed=bool(document.get("production_change_allowed")),
            visitor_role_eternian=str(roles.get("eternian", "reviewer")),
            visitor_role_beom=str(roles.get("beom", "operator")),
            user_recipient_role=str(document.get("user_recipient_role", "operator")),
        )


@dataclass(frozen=True)
class MailboxItem:
    item_id: str
    source_packet_id: str
    inbox_stage: str
    platform_id: str
    summary: str
    schema_version: str
    status: MailboxItemStatus
    created_at: datetime
    payload_path: str
    assignee: FulfillmentAssignee

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.mailbox-item/v1",
            "item_id": self.item_id,
            "source_packet_id": self.source_packet_id,
            "inbox_stage": self.inbox_stage,
            "platform_id": self.platform_id,
            "summary": self.summary,
            "source_schema_version": self.schema_version,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "payload_path": self.payload_path,
            "assignee": self.assignee.value,
        }


@dataclass(frozen=True)
class DeliveryMessage:
    message_id: str
    visitor: VisitorKind
    recipient: str
    item_ids: tuple[str, ...]
    body: str
    delivered_at: datetime
    message_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.delivery-message/v1",
            "message_id": self.message_id,
            "visitor": self.visitor.value,
            "recipient": self.recipient,
            "item_ids": list(self.item_ids),
            "body": self.body,
            "delivered_at": self.delivered_at.isoformat(),
            "message_digest": self.message_digest,
            "awaiting_user_response": True,
        }


@dataclass(frozen=True)
class FulfillmentTask:
    task_id: str
    item_id: str
    assignee: FulfillmentAssignee
    platform_id: str
    instruction: str
    approval_digest: str
    approved_at: datetime
    status: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.fulfillment-task/v1",
            "task_id": self.task_id,
            "item_id": self.item_id,
            "assignee": self.assignee.value,
            "platform_id": self.platform_id,
            "instruction": self.instruction,
            "approval_digest": self.approval_digest,
            "approved_at": self.approved_at.isoformat(),
            "status": self.status,
            "automatic_fulfill_allowed": False,
        }


def _assignee_for_stage(stage: str) -> FulfillmentAssignee:
    if stage == "operator-decision":
        return FulfillmentAssignee.BEOM
    return FulfillmentAssignee.ETERNIAN


def _item_id_for_packet(packet_id: str) -> str:
    return sha256(packet_id.encode()).hexdigest()[:16]


class ArkaonMailbox:
    def __init__(self, *, foundry_root: Path, policy: MailboxDeliveryPolicy | None = None) -> None:
        self.foundry_root = foundry_root.resolve()
        config = self.foundry_root / "config" / "arkaon-mailbox-delivery.json"
        self.policy = policy or MailboxDeliveryPolicy.load(config)
        self.items_root = self.foundry_root / "state" / "mailbox" / "items"
        self.delivery_root = self.foundry_root / "state" / "mailbox" / "delivery-messages"
        self.fulfillment_root = self.foundry_root / "state" / "mailbox" / "fulfillment-queue"
        for path in (self.items_root, self.delivery_root, self.fulfillment_root):
            path.mkdir(parents=True, exist_ok=True)

    def sync_from_inbox(self, *, now: datetime) -> tuple[MailboxItem, ...]:
        if now.tzinfo is None:
            raise MailboxRejected("TIMESTAMP", "timezone-aware timestamp required")
        inbox = self.foundry_root / "inbox"
        synced: list[MailboxItem] = []
        for stage in ("research", "eternian-review", "operator-decision"):
            stage_dir = inbox / stage
            if not stage_dir.is_dir():
                continue
            for path in sorted(stage_dir.glob("*.json")):
                try:
                    document = json.loads(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
                packet_id = str(document.get("packet_id", path.stem))
                item_id = _item_id_for_packet(packet_id)
                existing = self._load_item(item_id)
                if existing is not None and existing.status is not MailboxItemStatus.PENDING:
                    synced.append(existing)
                    continue
                item = MailboxItem(
                    item_id=item_id,
                    source_packet_id=packet_id,
                    inbox_stage=stage,
                    platform_id=str(document.get("platform_id", "UNKNOWN")),
                    summary=str(document.get("summary", ""))[:2000],
                    schema_version=str(document.get("schema_version", "unknown")),
                    status=MailboxItemStatus.PENDING,
                    created_at=existing.created_at if existing else now,
                    payload_path=path.relative_to(self.foundry_root).as_posix(),
                    assignee=_assignee_for_stage(stage),
                )
                self._persist_item(item)
                synced.append(item)
        return tuple(synced)

    def list_items(self, *, status: MailboxItemStatus | None = None) -> tuple[MailboxItem, ...]:
        items: list[MailboxItem] = []
        for path in sorted(self.items_root.glob("*.json")):
            item = self._load_item(path.stem)
            if item is None:
                continue
            if status is None or item.status is status:
                items.append(item)
        return tuple(items)

    def deliver_on_visitor_connect(
        self,
        *,
        visitor: VisitorKind,
        now: datetime,
        recipient: str = "user",
    ) -> DeliveryMessage | None:
        if now.tzinfo is None:
            raise MailboxRejected("TIMESTAMP", "timezone-aware timestamp required")
        pending = list(self.list_items(status=MailboxItemStatus.PENDING))
        target_assignee = (
            FulfillmentAssignee.BEOM
            if visitor is VisitorKind.BEOM
            else FulfillmentAssignee.ETERNIAN
        )
        pending = [item for item in pending if item.assignee is target_assignee]
        if not pending:
            return None
        visitor_label = "에테르니언" if visitor is VisitorKind.ETERNIAN else "범"
        lines = []
        for item in pending[:10]:
            lines.append(
                f"• [{item.platform_id}] {item.summary[:240]} "
                f"(담당: {'범' if item.assignee is FulfillmentAssignee.BEOM else '에테르니언'})"
            )
            self._persist_item(replace(item, status=MailboxItemStatus.DELIVERED))
        body = (
            f"{visitor_label}이(가) ARKAON 우편함을 확인했습니다. "
            f"아르카온이 발견한 필요 조치 {len(pending[:10])}건을 전달합니다.\n\n"
            + "\n".join(lines)
            + "\n\n승인하시면 담당(에테르니언/범)이 후속 확보·반영을 진행합니다. 거부 시 REJECTED로 기록됩니다."
        )
        message_id = secrets.token_hex(8)
        digest_payload = {
            "message_id": message_id,
            "visitor": visitor.value,
            "item_ids": [item.item_id for item in pending[:10]],
            "delivered_at": now.isoformat(),
        }
        message = DeliveryMessage(
            message_id=message_id,
            visitor=visitor,
            recipient=recipient,
            item_ids=tuple(item.item_id for item in pending[:10]),
            body=body,
            delivered_at=now,
            message_digest=sha256(json.dumps(digest_payload, sort_keys=True).encode()).hexdigest(),
        )
        target = self.delivery_root / f"{now.strftime('%Y-%m-%d')}-{message_id}.json"
        target.write_text(
            json.dumps(message.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return message

    def user_approve_delivery(
        self,
        *,
        message_id: str,
        approval_digest: str,
        now: datetime,
    ) -> tuple[FulfillmentTask, ...]:
        if now.tzinfo is None:
            raise MailboxRejected("TIMESTAMP", "timezone-aware timestamp required")
        if len(approval_digest) != 64:
            raise MailboxRejected("INVALID_DIGEST", "approval digest must be sha256 hex")
        message = self._load_delivery_message(message_id)
        if message is None:
            raise MailboxRejected("MESSAGE_NOT_FOUND", "delivery message not found")
        tasks: list[FulfillmentTask] = []
        for item_id in message.item_ids:
            item = self._load_item(item_id)
            if item is None or item.status not in (MailboxItemStatus.DELIVERED, MailboxItemStatus.PENDING):
                continue
            self._persist_item(replace(item, status=MailboxItemStatus.USER_APPROVED))
            task_id = secrets.token_hex(8)
            instruction = (
                f"사용자 승인됨: {item.summary[:500]}. "
                f"payload={item.payload_path}. "
                f"{'범' if item.assignee is FulfillmentAssignee.BEOM else '에테르니언'}이(가) 확보·반영."
            )
            task = FulfillmentTask(
                task_id=task_id,
                item_id=item_id,
                assignee=item.assignee,
                platform_id=item.platform_id,
                instruction=instruction,
                approval_digest=approval_digest,
                approved_at=now,
                status="QUEUED",
            )
            target = self.fulfillment_root / f"{task_id}.json"
            target.write_text(
                json.dumps(task.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            tasks.append(task)
        delivered_doc = self._load_delivery_message(message_id)
        if delivered_doc:
            doc = delivered_doc.to_document()
            doc["awaiting_user_response"] = False
            doc["user_approval_digest"] = approval_digest
            doc["approved_at"] = now.isoformat()
            for path in self.delivery_root.glob(f"*-{message_id}.json"):
                path.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return tuple(tasks)

    def user_reject_delivery(self, *, message_id: str, now: datetime) -> None:
        message = self._load_delivery_message(message_id)
        if message is None:
            raise MailboxRejected("MESSAGE_NOT_FOUND", "delivery message not found")
        for item_id in message.item_ids:
            item = self._load_item(item_id)
            if item is None:
                continue
            self._persist_item(replace(item, status=MailboxItemStatus.REJECTED))

    def list_fulfillment_queue(
        self, *, assignee: FulfillmentAssignee | None = None
    ) -> tuple[FulfillmentTask, ...]:
        tasks: list[FulfillmentTask] = []
        for path in sorted(self.fulfillment_root.glob("*.json")):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if document.get("status") != "QUEUED":
                continue
            task = FulfillmentTask(
                task_id=str(document["task_id"]),
                item_id=str(document["item_id"]),
                assignee=FulfillmentAssignee(str(document["assignee"])),
                platform_id=str(document["platform_id"]),
                instruction=str(document["instruction"]),
                approval_digest=str(document["approval_digest"]),
                approved_at=datetime.fromisoformat(str(document["approved_at"])),
                status=str(document["status"]),
            )
            if assignee is None or task.assignee is assignee:
                tasks.append(task)
        return tuple(tasks)

    def complete_fulfillment(self, *, task_id: str, now: datetime, completion_note: str) -> FulfillmentTask:
        if now.tzinfo is None:
            raise MailboxRejected("TIMESTAMP", "timezone-aware timestamp required")
        path = self.fulfillment_root / f"{task_id}.json"
        if not path.is_file():
            raise MailboxRejected("TASK_NOT_FOUND", "fulfillment task not found")
        document = json.loads(path.read_text(encoding="utf-8"))
        document["status"] = "COMPLETED"
        document["completed_at"] = now.isoformat()
        document["completion_note"] = completion_note[:2000]
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        item = self._load_item(str(document["item_id"]))
        if item is not None:
            self._persist_item(replace(item, status=MailboxItemStatus.FULFILLED))
        return FulfillmentTask(
            task_id=str(document["task_id"]),
            item_id=str(document["item_id"]),
            assignee=FulfillmentAssignee(str(document["assignee"])),
            platform_id=str(document["platform_id"]),
            instruction=str(document["instruction"]),
            approval_digest=str(document["approval_digest"]),
            approved_at=datetime.fromisoformat(str(document["approved_at"])),
            status="COMPLETED",
        )

    def list_delivery_messages(self, *, limit: int = 20) -> tuple[DeliveryMessage, ...]:
        messages: list[DeliveryMessage] = []
        for path in sorted(self.delivery_root.glob("*.json"), reverse=True)[:limit]:
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            messages.append(
                DeliveryMessage(
                    message_id=str(document["message_id"]),
                    visitor=VisitorKind(str(document["visitor"])),
                    recipient=str(document["recipient"]),
                    item_ids=tuple(str(value) for value in document.get("item_ids") or ()),
                    body=str(document["body"]),
                    delivered_at=datetime.fromisoformat(str(document["delivered_at"])),
                    message_digest=str(document["message_digest"]),
                )
            )
        return tuple(messages)

    def _persist_item(self, item: MailboxItem) -> None:
        target = self.items_root / f"{item.item_id}.json"
        target.write_text(
            json.dumps(item.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _load_item(self, item_id: str) -> MailboxItem | None:
        path = self.items_root / f"{item_id}.json"
        if not path.is_file():
            return None
        document = json.loads(path.read_text(encoding="utf-8"))
        return MailboxItem(
            item_id=str(document["item_id"]),
            source_packet_id=str(document["source_packet_id"]),
            inbox_stage=str(document["inbox_stage"]),
            platform_id=str(document["platform_id"]),
            summary=str(document["summary"]),
            schema_version=str(document.get("source_schema_version", document.get("schema_version", ""))),
            status=MailboxItemStatus(str(document["status"])),
            created_at=datetime.fromisoformat(str(document["created_at"])),
            payload_path=str(document["payload_path"]),
            assignee=FulfillmentAssignee(str(document["assignee"])),
        )

    def _load_delivery_message(self, message_id: str) -> DeliveryMessage | None:
        for path in self.delivery_root.glob(f"*-{message_id}.json"):
            document = json.loads(path.read_text(encoding="utf-8"))
            return DeliveryMessage(
                message_id=str(document["message_id"]),
                visitor=VisitorKind(str(document["visitor"])),
                recipient=str(document["recipient"]),
                item_ids=tuple(str(value) for value in document.get("item_ids") or ()),
                body=str(document["body"]),
                delivered_at=datetime.fromisoformat(str(document["delivered_at"])),
                message_digest=str(document["message_digest"]),
            )
        return None

    @staticmethod
    def visitor_for_console_role(role: str, policy: MailboxDeliveryPolicy) -> VisitorKind | None:
        if role == policy.visitor_role_eternian:
            return VisitorKind.ETERNIAN
        if role == policy.visitor_role_beom:
            return VisitorKind.BEOM
        return None

    @staticmethod
    def assignee_for_console_role(role: str, policy: MailboxDeliveryPolicy) -> FulfillmentAssignee | None:
        if role == policy.visitor_role_eternian:
            return FulfillmentAssignee.ETERNIAN
        if role == policy.visitor_role_beom:
            return FulfillmentAssignee.BEOM
        return None
