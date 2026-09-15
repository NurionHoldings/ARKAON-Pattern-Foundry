from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TenantRow(Base):
    __tablename__ = "tenants"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AnalysisTargetRow(Base):
    __tablename__ = "analysis_targets"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_target_tenant_name"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    target_type: Mapped[str] = mapped_column(String(40))
    classification: Mapped[str] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(40), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditEventRow(Base):
    __tablename__ = "audit_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True)
    aggregate_type: Mapped[str] = mapped_column(String(80))
    aggregate_id: Mapped[UUID] = mapped_column(index=True)
    event_type: Mapped[str] = mapped_column(String(100))
    actor_id: Mapped[UUID]
    correlation_id: Mapped[UUID] = mapped_column(index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

