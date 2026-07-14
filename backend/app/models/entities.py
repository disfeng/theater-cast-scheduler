from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    BatchStatus,
    DesignationType,
    DraftItemKind,
    DraftValidationStatus,
    ImportDraftStatus,
    LeaveStatus,
    PerformanceStatus,
    RatingLevel,
    UserRole,
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("actors.id"), nullable=True)
    actor: Mapped[Actor | None] = relationship(back_populates="user")


class Theater(Base):
    __tablename__ = "theaters"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    slots: Mapped[list[TheaterSlot]] = relationship(
        back_populates="theater", cascade="all, delete-orphan", order_by="TheaterSlot.sort_order"
    )
    weekly_template_entries: Mapped[list[TheaterWeeklyTemplateEntry]] = relationship(
        back_populates="theater", cascade="all, delete-orphan"
    )


class TheaterSlot(Base):
    __tablename__ = "theater_slots"
    __table_args__ = (UniqueConstraint("theater_id", "name", name="uq_theater_slots_theater_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    theater_id: Mapped[int] = mapped_column(ForeignKey("theaters.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    start_time: Mapped[time] = mapped_column(Time)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    theater: Mapped[Theater] = relationship(back_populates="slots")


class TheaterWeeklyTemplateEntry(Base):
    __tablename__ = "theater_weekly_template_entries"
    __table_args__ = (
        UniqueConstraint("theater_id", "weekday", "theater_slot_id", name="uq_weekly_template_entry"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    theater_id: Mapped[int] = mapped_column(ForeignKey("theaters.id"), index=True)
    weekday: Mapped[str] = mapped_column(String(12))
    theater_slot_id: Mapped[int] = mapped_column(ForeignKey("theater_slots.id"), index=True)
    theater: Mapped[Theater] = relationship(back_populates="weekly_template_entries")
    theater_slot: Mapped[TheaterSlot] = relationship()


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("theater_id", "name", name="uq_roles_theater_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    theater_id: Mapped[int] = mapped_column(ForeignKey("theaters.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    group_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    theater: Mapped[Theater] = relationship()


class Actor(Base):
    __tablename__ = "actors"

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    max_consecutive_performances: Mapped[int] = mapped_column(Integer, default=3)
    rating_level: Mapped[RatingLevel] = mapped_column(Enum(RatingLevel), default=RatingLevel.NORMAL)
    low_rating_monthly_cap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    user: Mapped[User | None] = relationship(back_populates="actor")
    role_capabilities: Mapped[list[ActorRoleCapability]] = relationship(
        back_populates="actor", cascade="all, delete-orphan"
    )


class ActorRoleCapability(Base):
    __tablename__ = "actor_role_capabilities"
    __table_args__ = (UniqueConstraint("actor_id", "role_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("actors.id"))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    actor: Mapped[Actor] = relationship(back_populates="role_capabilities")
    role: Mapped[Role] = relationship()


class Performance(Base):
    __tablename__ = "performances"
    __table_args__ = (
        UniqueConstraint(
            "theater_id", "performance_date", "theater_slot_id",
            name="uq_performance_theater_date_theater_slot",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    theater_id: Mapped[int] = mapped_column(ForeignKey("theaters.id"))
    theater_slot_id: Mapped[int] = mapped_column(ForeignKey("theater_slots.id"), index=True)
    performance_date: Mapped[date] = mapped_column(Date, index=True)
    slot_name_snapshot: Mapped[str] = mapped_column(String(80))
    start_time_snapshot: Mapped[time] = mapped_column(Time)
    status: Mapped[PerformanceStatus] = mapped_column(
        Enum(PerformanceStatus), default=PerformanceStatus.DRAFT
    )
    theater: Mapped[Theater] = relationship()
    theater_slot: Mapped[TheaterSlot] = relationship()


class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    __table_args__ = (UniqueConstraint("actor_id", "leave_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("actors.id"), index=True)
    leave_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[LeaveStatus] = mapped_column(Enum(LeaveStatus), default=LeaveStatus.PENDING)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[Actor] = relationship()


class Designation(Base):
    __tablename__ = "designations"

    id: Mapped[int] = mapped_column(primary_key=True)
    designation_type: Mapped[DesignationType] = mapped_column(Enum(DesignationType), index=True)
    player_name: Mapped[str] = mapped_column(String(120))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("actors.id"))
    target_performance_id: Mapped[int | None] = mapped_column(ForeignKey("performances.id"))
    submitted_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    included_in_batch: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    weekly_batch_id: Mapped[int | None] = mapped_column(ForeignKey("weekly_batches.id"), nullable=True)
    role: Mapped[Role] = relationship()
    actor: Mapped[Actor] = relationship()
    target_performance: Mapped[Performance | None] = relationship()
    weekly_batch: Mapped[WeeklyBatch | None] = relationship()


class Wish(Base):
    __tablename__ = "wishes"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_name: Mapped[str] = mapped_column(String(120))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("actors.id"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    weekly_batch_id: Mapped[int | None] = mapped_column(ForeignKey("weekly_batches.id"), nullable=True)
    role: Mapped[Role] = relationship()
    actor: Mapped[Actor] = relationship()
    weekly_batch: Mapped[WeeklyBatch | None] = relationship()


class ScheduleAssignment(Base):
    __tablename__ = "schedule_assignments"
    __table_args__ = (UniqueConstraint("performance_id", "role_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    performance_id: Mapped[int] = mapped_column(ForeignKey("performances.id"), index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("actors.id"), index=True)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    locked: Mapped[bool] = mapped_column(default=False)
    requires_approval: Mapped[bool] = mapped_column(default=False)
    approved: Mapped[bool] = mapped_column(default=False)
    performance: Mapped[Performance] = relationship()
    role: Mapped[Role] = relationship()
    actor: Mapped[Actor] = relationship()


class WeeklyBatch(Base):
    __tablename__ = "weekly_batches"
    __table_args__ = (UniqueConstraint("theater_id", "week_start"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    theater_id: Mapped[int] = mapped_column(ForeignKey("theaters.id"), index=True)
    week_start: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[BatchStatus] = mapped_column(Enum(BatchStatus), default=BatchStatus.DRAFT)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    theater: Mapped[Theater] = relationship()


class PersistentImportDraft(Base):
    __tablename__ = "import_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    weekly_batch_id: Mapped[int] = mapped_column(ForeignKey("weekly_batches.id"), index=True)
    raw_text: Mapped[str] = mapped_column(Text)
    status: Mapped[ImportDraftStatus] = mapped_column(
        Enum(ImportDraftStatus), default=ImportDraftStatus.DRAFT
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    weekly_batch: Mapped[WeeklyBatch] = relationship()
    items: Mapped[list[ImportDraftItem]] = relationship(
        back_populates="import_draft", cascade="all, delete-orphan"
    )


class ImportDraftItem(Base):
    __tablename__ = "import_draft_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    import_draft_id: Mapped[int] = mapped_column(ForeignKey("import_drafts.id"), index=True)
    item_kind: Mapped[DraftItemKind] = mapped_column(Enum(DraftItemKind))
    raw_line: Mapped[str | None] = mapped_column(Text, nullable=True)
    designation_type: Mapped[DesignationType | None] = mapped_column(
        Enum(DesignationType), nullable=True
    )
    player_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    actor_name_raw: Mapped[str | None] = mapped_column(String(120), nullable=True)
    role_name_raw: Mapped[str | None] = mapped_column(String(120), nullable=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("actors.id"), nullable=True)
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"), nullable=True)
    target_performance_id: Mapped[int | None] = mapped_column(ForeignKey("performances.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_status: Mapped[DraftValidationStatus] = mapped_column(
        Enum(DraftValidationStatus), default=DraftValidationStatus.INVALID
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    designation_id: Mapped[int | None] = mapped_column(ForeignKey("designations.id"), nullable=True)
    wish_id: Mapped[int | None] = mapped_column(ForeignKey("wishes.id"), nullable=True)

    import_draft: Mapped[PersistentImportDraft] = relationship(back_populates="items")
    actor: Mapped[Actor | None] = relationship()
    role: Mapped[Role | None] = relationship()
    target_performance: Mapped[Performance | None] = relationship()
    designation: Mapped[Designation | None] = relationship()
    wish: Mapped[Wish | None] = relationship()
