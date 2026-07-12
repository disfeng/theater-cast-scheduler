from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import DesignationType, LeaveStatus, PerformanceStatus, RatingLevel, UserRole


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
    default_weekly_template: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    group_name: Mapped[str | None] = mapped_column(String(120), nullable=True)


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

    id: Mapped[int] = mapped_column(primary_key=True)
    theater_id: Mapped[int] = mapped_column(ForeignKey("theaters.id"))
    performance_date: Mapped[date] = mapped_column(Date, index=True)
    slot: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[PerformanceStatus] = mapped_column(
        Enum(PerformanceStatus), default=PerformanceStatus.DRAFT
    )
    theater: Mapped[Theater] = relationship()


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
    role: Mapped[Role] = relationship()
    actor: Mapped[Actor] = relationship()
    target_performance: Mapped[Performance | None] = relationship()


class Wish(Base):
    __tablename__ = "wishes"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_name: Mapped[str] = mapped_column(String(120))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("actors.id"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[Role] = relationship()
    actor: Mapped[Actor] = relationship()


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
