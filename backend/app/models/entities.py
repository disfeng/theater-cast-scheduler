from __future__ import annotations

from datetime import date, datetime, time
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Index,
    String,
    Text,
    Time,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.db.base import Base
from app.core.time import utc_now
from app.models.enums import (
    ActorNotificationTaskStatus,
    ActorNotificationType,
    BatchStatus,
    DesignationType,
    DraftItemKind,
    DraftValidationStatus,
    EntitlementEventType,
    EntitlementItemCategory,
    EntitlementItemStatus,
    EntitlementSourceType,
    EntitlementGrantMode,
    GrantBatchStatus,
    ImportDraftStatus,
    LeaveStatus,
    PerformanceStatus,
    RatingLevel,
    SmsDeliveryStatus,
    PlayerStatus,
    UserRole,
    BoardChangeType,
    BoardItemKind,
    BoardParserType,
    BoardRevisionStatus,
    BoardValidationStatus,
    AuditEventCategory,
    AuditResult,
    AuditRiskLevel,
)


class PlayerProfile(Base):
    __tablename__ = "player_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120))
    normalized_name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    status: Mapped[PlayerStatus] = mapped_column(
        Enum(PlayerStatus), default=PlayerStatus.ACTIVE, server_default=PlayerStatus.ACTIVE.name
    )
    merged_into_id: Mapped[int | None] = mapped_column(
        ForeignKey("player_profiles.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, server_default=func.now()
    )
    aliases: Mapped[list[PlayerAlias]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )
    entitlement_items: Mapped[list[EntitlementItem]] = relationship(back_populates="owner")


class EncryptedAiParserSettings(Base):
    __tablename__ = "ai_parser_settings"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    endpoint: Mapped[str] = mapped_column(String(500), default="https://api.openai.com/v1")
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str] = mapped_column(String(120), default="gpt-4.1-mini")
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    prompt_version: Mapped[str] = mapped_column(String(80), default="board-v1")
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_test_message: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AiParserSettingsAudit(Base):
    __tablename__ = "ai_parser_settings_audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(30))
    changed_fields: Mapped[list | None] = mapped_column(JSON, nullable=True)
    key_replaced: Mapped[bool] = mapped_column(Boolean, default=False)
    provider_host: Mapped[str | None] = mapped_column(String(253), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    outcome: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now()
    )


class EncryptedActorNotificationSettings(Base):
    __tablename__ = "actor_notification_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    sms_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    actor_portal_url: Mapped[str] = mapped_column(
        String(500), default="http://localhost:7003/actor"
    )
    encrypted_access_key_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_access_key_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    sign_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    template_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    endpoint: Mapped[str] = mapped_column(
        String(253), default="dysmsapi.aliyuncs.com", server_default="dysmsapi.aliyuncs.com"
    )


class PlayerAlias(Base):
    __tablename__ = "player_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("player_profiles.id"), index=True)
    alias: Mapped[str] = mapped_column(String(120))
    normalized_alias: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    player: Mapped[PlayerProfile] = relationship(back_populates="aliases")


class EntitlementItemType(Base):
    __tablename__ = "entitlement_item_types"
    __table_args__ = (
        CheckConstraint("priority >= 0", name="ck_entitlement_item_types_priority_non_negative"),
        CheckConstraint("default_validity_days > 0", name="ck_entitlement_types_validity_positive"),
        CheckConstraint(
            "(category = 'DESIGNATION' AND designation_type IS NOT NULL) OR "
            "(category = 'GENERAL' AND designation_type IS NULL)",
            name="ck_entitlement_types_category_binding",
        ),
        UniqueConstraint("theater_id", "code", name="uq_entitlement_types_theater_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    theater_id: Mapped[int | None] = mapped_column(
        ForeignKey("theaters.id"), nullable=True, index=True
    )
    code: Mapped[str] = mapped_column(String(40), index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    category: Mapped[EntitlementItemCategory] = mapped_column(
        Enum(EntitlementItemCategory), default=EntitlementItemCategory.GENERAL, index=True
    )
    designation_type: Mapped[DesignationType | None] = mapped_column(
        Enum(DesignationType), nullable=True, index=True
    )
    priority: Mapped[int] = mapped_column(Integer)
    default_validity_days: Mapped[int] = mapped_column(Integer)
    color: Mapped[str] = mapped_column(String(7), default="#409eff", server_default="#409eff")
    icon: Mapped[str | None] = mapped_column(String(80), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    binds_beneficiary: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    binds_actor: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    binding_locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    theater: Mapped[Theater | None] = relationship()
    items: Mapped[list[EntitlementItem]] = relationship(back_populates="item_type")

    @property
    def default_validity_months(self) -> int:
        return max(1, round(self.default_validity_days / 30))

    @default_validity_months.setter
    def default_validity_months(self, value: int) -> None:
        self.default_validity_days = value * 30


class EntitlementGrantBatch(Base):
    __tablename__ = "entitlement_grant_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    grant_mode: Mapped[EntitlementGrantMode] = mapped_column(
        Enum(EntitlementGrantMode),
        default=EntitlementGrantMode.BY_PLAYER,
        server_default=EntitlementGrantMode.BY_PLAYER.name,
        index=True,
    )
    theater_id: Mapped[int | None] = mapped_column(
        ForeignKey("theaters.id"), nullable=True, index=True
    )
    source_type: Mapped[EntitlementSourceType] = mapped_column(
        Enum(EntitlementSourceType), default=EntitlementSourceType.OTHER, index=True
    )
    source_month: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    source_label: Mapped[str] = mapped_column(String(120))
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    grant_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    default_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[GrantBatchStatus] = mapped_column(
        Enum(GrantBatchStatus),
        default=GrantBatchStatus.DRAFT,
        server_default=GrantBatchStatus.DRAFT.name,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now()
    )
    granted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    bound_actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("actors.id"), nullable=True, index=True
    )
    theater: Mapped[Theater | None] = relationship()
    bound_actor: Mapped[Actor | None] = relationship()
    items: Mapped[list[EntitlementItem]] = relationship(back_populates="grant_batch")
    draft_items: Mapped[list[EntitlementGrantDraftItem]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


class EntitlementGrantDraftItem(Base):
    __tablename__ = "entitlement_grant_draft_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("entitlement_grant_batches.id"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("player_profiles.id"), index=True)
    item_type_id: Mapped[int] = mapped_column(ForeignKey("entitlement_item_types.id"), index=True)
    source_month: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    bound_actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("actors.id"), nullable=True, index=True
    )
    batch: Mapped[EntitlementGrantBatch] = relationship(back_populates="draft_items")
    player: Mapped[PlayerProfile] = relationship()
    item_type: Mapped[EntitlementItemType] = relationship()
    bound_actor: Mapped[Actor | None] = relationship()


class EntitlementItem(Base):
    __tablename__ = "entitlement_items"
    __table_args__ = (
        Index("ix_entitlement_items_theater_owner_status", "theater_id", "owner_id", "status"),
        Index(
            "ix_entitlement_items_theater_type_status_expiry",
            "theater_id",
            "item_type_id",
            "status",
            "expires_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    theater_id: Mapped[int | None] = mapped_column(
        ForeignKey("theaters.id"), nullable=True, index=True
    )
    serial_number: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("player_profiles.id"), index=True)
    item_type_id: Mapped[int] = mapped_column(ForeignKey("entitlement_item_types.id"), index=True)
    grant_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("entitlement_grant_batches.id"), nullable=True, index=True
    )
    source_type: Mapped[EntitlementSourceType] = mapped_column(
        Enum(EntitlementSourceType), default=EntitlementSourceType.OTHER, index=True
    )
    source_month: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    source_label: Mapped[str] = mapped_column(String(120))
    granted_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[EntitlementItemStatus] = mapped_column(
        Enum(EntitlementItemStatus),
        default=EntitlementItemStatus.AVAILABLE,
        server_default=EntitlementItemStatus.AVAILABLE.name,
        index=True,
    )
    current_designation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    bound_actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("actors.id"), nullable=True, index=True
    )
    binds_beneficiary_snapshot: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )
    binds_actor_snapshot: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    theater: Mapped[Theater | None] = relationship()
    owner: Mapped[PlayerProfile] = relationship(back_populates="entitlement_items")
    item_type: Mapped[EntitlementItemType] = relationship(back_populates="items")
    grant_batch: Mapped[EntitlementGrantBatch | None] = relationship(back_populates="items")
    bound_actor: Mapped[Actor | None] = relationship()
    ledger_entries: Mapped[list[EntitlementLedgerEntry]] = relationship(back_populates="item")

    @property
    def bound_actor_name(self) -> str | None:
        return self.bound_actor.display_name if self.bound_actor is not None else None


class EntitlementLedgerEntry(Base):
    __tablename__ = "entitlement_ledger_entries"
    __table_args__ = (Index("ix_entitlement_ledger_theater_id", "theater_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    theater_id: Mapped[int | None] = mapped_column(
        ForeignKey("theaters.id"), nullable=True, index=True
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("entitlement_items.id"), index=True)
    event_type: Mapped[EntitlementEventType] = mapped_column(Enum(EntitlementEventType), index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now(), index=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    from_status: Mapped[EntitlementItemStatus | None] = mapped_column(
        Enum(EntitlementItemStatus), nullable=True
    )
    to_status: Mapped[EntitlementItemStatus | None] = mapped_column(
        Enum(EntitlementItemStatus), nullable=True
    )
    performance_id: Mapped[int | None] = mapped_column(ForeignKey("performances.id"), nullable=True)
    designation_id: Mapped[int | None] = mapped_column(ForeignKey("designations.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(200), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    operator_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reverses_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("entitlement_ledger_entries.id"), nullable=True, unique=True
    )
    item: Mapped[EntitlementItem] = relationship(back_populates="ledger_entries")
    theater: Mapped[Theater | None] = relationship()


class EntitlementLedgerImmutableError(RuntimeError):
    pass


@event.listens_for(Session, "before_flush")
def prevent_entitlement_ledger_mutation(session: Session, *_: object) -> None:
    changed_entries = {
        entry
        for entry in session.dirty.union(session.deleted)
        if isinstance(entry, EntitlementLedgerEntry) and entry not in session.new
    }
    if changed_entries:
        raise EntitlementLedgerImmutableError("entitlement ledger entries are append-only")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(
        String(120), default="管理员", server_default="管理员"
    )
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", index=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("actors.id"), nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_failed_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    actor: Mapped[Actor | None] = relationship(back_populates="user")
    theater_scopes: Mapped[list[UserTheaterScope]] = relationship(
        foreign_keys="UserTheaterScope.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserTheaterScope(Base):
    __tablename__ = "user_theater_scopes"
    __table_args__ = (UniqueConstraint("user_id", "theater_id", name="uq_user_theater_scope"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    theater_id: Mapped[int] = mapped_column(ForeignKey("theaters.id"), index=True)
    granted_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now()
    )
    user: Mapped[User] = relationship(foreign_keys=[user_id], back_populates="theater_scopes")
    theater: Mapped[Theater] = relationship()
    granted_by: Mapped[User] = relationship(foreign_keys=[granted_by_user_id])


class LoginThrottle(Base):
    __tablename__ = "login_throttles"
    __table_args__ = (
        UniqueConstraint("identifier_hash", "ip_address", name="uq_login_throttle_identity_ip"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    identifier_hash: Mapped[str] = mapped_column(String(64), index=True)
    ip_address: Mapped[str] = mapped_column(String(64), index=True)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_failed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_theater_occurred", "theater_id", "occurred_at"),
        Index("ix_audit_logs_operator_occurred", "operator_user_id", "occurred_at"),
        Index("ix_audit_logs_module_action", "module", "action"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now(), index=True
    )
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    operator_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    operator_name_snapshot: Mapped[str | None] = mapped_column(String(120), nullable=True)
    operator_role_snapshot: Mapped[str | None] = mapped_column(String(40), nullable=True)
    theater_id: Mapped[int | None] = mapped_column(
        ForeignKey("theaters.id"), nullable=True, index=True
    )
    event_category: Mapped[AuditEventCategory] = mapped_column(Enum(AuditEventCategory))
    module: Mapped[str] = mapped_column(String(60), index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    target_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    result: Mapped[AuditResult] = mapped_column(Enum(AuditResult), index=True)
    risk_level: Mapped[AuditRiskLevel] = mapped_column(Enum(AuditRiskLevel), index=True)
    summary: Mapped[str] = mapped_column(String(500))
    before_data: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    after_data: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    affected_objects: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(120), nullable=True)


class AuditLogImmutableError(RuntimeError):
    pass


@event.listens_for(Session, "before_flush")
def prevent_audit_log_mutation(session: Session, *_: object) -> None:
    changed_entries = {
        entry
        for entry in session.dirty.union(session.deleted)
        if isinstance(entry, AuditLog) and entry not in session.new
    }
    if changed_entries:
        raise AuditLogImmutableError("audit logs are append-only")


class Theater(Base):
    __tablename__ = "theaters"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    reveal_days_before: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    reveal_time: Mapped[time] = mapped_column(Time, default=time(21, 0), server_default="21:00:00")
    actor_sms_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
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
        UniqueConstraint(
            "theater_id", "weekday", "theater_slot_id", name="uq_weekly_template_entry"
        ),
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
    phone_number: Mapped[str | None] = mapped_column(
        String(20), nullable=True, unique=True, index=True
    )
    max_consecutive_performances: Mapped[int] = mapped_column(Integer, default=3)
    rating_level: Mapped[RatingLevel] = mapped_column(Enum(RatingLevel), default=RatingLevel.NORMAL)
    low_rating_monthly_cap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    user: Mapped[User | None] = relationship(back_populates="actor")
    role_capabilities: Mapped[list[ActorRoleCapability]] = relationship(
        back_populates="actor", cascade="all, delete-orphan"
    )
    theater_memberships: Mapped[list[ActorTheaterMembership]] = relationship(
        back_populates="actor", cascade="all, delete-orphan"
    )


class ActorTheaterMembership(Base):
    __tablename__ = "actor_theater_memberships"
    __table_args__ = (
        UniqueConstraint("actor_id", "theater_id", name="uq_actor_theater_membership"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("actors.id"), index=True)
    theater_id: Mapped[int] = mapped_column(ForeignKey("theaters.id"), index=True)
    is_entry_theater: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    actor: Mapped[Actor] = relationship(back_populates="theater_memberships")
    theater: Mapped[Theater] = relationship()


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
            "theater_id",
            "performance_date",
            "theater_slot_id",
            name="uq_performance_theater_date_theater_slot",
        ),
        Index(
            "ix_performances_theater_date_status",
            "theater_id",
            "performance_date",
            "status",
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


class PerformanceBoard(Base):
    __tablename__ = "performance_boards"
    __table_args__ = (
        UniqueConstraint("performance_id", "id", name="uq_performance_board_scope"),
        ForeignKeyConstraint(
            ["id", "current_revision_id"],
            ["performance_board_revisions.board_id", "performance_board_revisions.id"],
            name="fk_performance_boards_current_revision_scope",
            use_alter=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement="ignore_fk")
    performance_id: Mapped[int] = mapped_column(
        ForeignKey("performances.id"), unique=True, index=True
    )
    current_revision_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_revision_number: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, server_default=func.now()
    )
    performance: Mapped[Performance] = relationship()
    revisions: Mapped[list["PerformanceBoardRevision"]] = relationship(
        back_populates="board",
        foreign_keys="PerformanceBoardRevision.board_id",
        cascade="all, delete-orphan",
        order_by="PerformanceBoardRevision.revision_number",
    )
    current_revision: Mapped["PerformanceBoardRevision | None"] = relationship(
        foreign_keys=[current_revision_id], post_update=True
    )


class PerformanceBoardRevision(Base):
    __tablename__ = "performance_board_revisions"
    __table_args__ = (
        UniqueConstraint("board_id", "revision_number", name="uq_board_revision_number"),
        UniqueConstraint("board_id", "id", name="uq_board_revision_scope"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    board_id: Mapped[int] = mapped_column(ForeignKey("performance_boards.id"), index=True)
    revision_number: Mapped[int] = mapped_column(Integer)
    raw_text: Mapped[str] = mapped_column(Text)
    status: Mapped[BoardRevisionStatus] = mapped_column(
        Enum(BoardRevisionStatus), default=BoardRevisionStatus.REVIEW_REQUIRED
    )
    parser_type: Mapped[BoardParserType] = mapped_column(
        Enum(BoardParserType), default=BoardParserType.DETERMINISTIC
    )
    provider_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    raw_ai_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rollback_source_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("performance_board_revisions.id"), nullable=True
    )
    board: Mapped[PerformanceBoard] = relationship(
        back_populates="revisions", foreign_keys=[board_id]
    )
    draft_items: Mapped[list["BoardDraftItem"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan", order_by="BoardDraftItem.id"
    )


class PerformancePlayer(Base):
    __tablename__ = "performance_players"
    __table_args__ = (
        UniqueConstraint(
            "performance_id", "player_character_name", name="uq_performance_player_character"
        ),
        ForeignKeyConstraint(
            ["performance_id", "source_board_id"],
            ["performance_boards.performance_id", "performance_boards.id"],
            name="fk_performance_players_board_scope",
        ),
        ForeignKeyConstraint(
            ["source_board_id", "source_revision_id"],
            ["performance_board_revisions.board_id", "performance_board_revisions.id"],
            name="fk_performance_players_revision_scope",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    performance_id: Mapped[int] = mapped_column(ForeignKey("performances.id"), index=True)
    player_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("player_profiles.id"), nullable=True
    )
    player_name_snapshot: Mapped[str] = mapped_column(String(120))
    player_character_name: Mapped[str] = mapped_column(String(120))
    paired_role_name: Mapped[str] = mapped_column(String(120))
    relation_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    theater_visit_ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    character_visit_ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_board_id: Mapped[int] = mapped_column(Integer)
    source_revision_id: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")


class BoardDraftItem(Base):
    __tablename__ = "board_draft_items"
    __table_args__ = (
        UniqueConstraint("revision_id", "stable_key", name="uq_board_draft_revision_stable_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    revision_id: Mapped[int] = mapped_column(
        ForeignKey("performance_board_revisions.id"), index=True
    )
    item_kind: Mapped[BoardItemKind] = mapped_column(Enum(BoardItemKind))
    change_type: Mapped[BoardChangeType] = mapped_column(Enum(BoardChangeType))
    stable_key: Mapped[str] = mapped_column(String(300), index=True)
    raw_line: Mapped[str | None] = mapped_column(Text, nullable=True)
    player_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    player_character_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    paired_role_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    relation_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    theater_visit_ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    character_visit_ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_name_raw: Mapped[str | None] = mapped_column(String(120), nullable=True)
    role_name_raw: Mapped[str | None] = mapped_column(String(120), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_player_id: Mapped[int | None] = mapped_column(
        ForeignKey("player_profiles.id"), nullable=True
    )
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("actors.id"), nullable=True)
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"), nullable=True)
    candidates: Mapped[list | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation_status: Mapped[BoardValidationStatus] = mapped_column(
        Enum(BoardValidationStatus), default=BoardValidationStatus.VALID
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    performance_player_id: Mapped[int | None] = mapped_column(
        ForeignKey("performance_players.id"), nullable=True
    )
    designation_id: Mapped[int | None] = mapped_column(ForeignKey("designations.id"), nullable=True)
    wish_id: Mapped[int | None] = mapped_column(ForeignKey("wishes.id"), nullable=True)
    removal_lifecycle_confirmed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )
    revision: Mapped[PerformanceBoardRevision] = relationship(back_populates="draft_items")


class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    __table_args__ = (UniqueConstraint("actor_id", "leave_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("actors.id"), index=True)
    leave_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[LeaveStatus] = mapped_column(Enum(LeaveStatus), default=LeaveStatus.PENDING)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[Actor] = relationship()


class LeaveApplication(Base):
    __tablename__ = "leave_applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("actors.id"), index=True)
    theater_id: Mapped[int] = mapped_column(ForeignKey("theaters.id"), index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now(), index=True
    )
    actor: Mapped[Actor] = relationship()
    theater: Mapped[Theater] = relationship()
    days: Mapped[list[LeaveApplicationDay]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="LeaveApplicationDay.leave_date",
    )


class LeaveApplicationDay(Base):
    __tablename__ = "leave_application_days"
    __table_args__ = (
        UniqueConstraint("application_id", "leave_date", name="uq_leave_application_day"),
        Index("ix_leave_days_status_date", "status", "leave_date", "withdrawn_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("leave_applications.id"), index=True)
    leave_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[LeaveStatus] = mapped_column(
        Enum(LeaveStatus), default=LeaveStatus.PENDING, server_default=LeaveStatus.PENDING.name
    )
    has_schedule_conflict: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    conflict_performance_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    application: Mapped[LeaveApplication] = relationship(back_populates="days")


class ActorNotificationTask(Base):
    __tablename__ = "actor_notification_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    theater_id: Mapped[int] = mapped_column(ForeignKey("theaters.id"), index=True)
    performance_id: Mapped[int] = mapped_column(ForeignKey("performances.id"), index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("actors.id"), index=True)
    schedule_version: Mapped[int] = mapped_column(Integer)
    notification_type: Mapped[ActorNotificationType] = mapped_column(Enum(ActorNotificationType))
    reveal_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[ActorNotificationTaskStatus] = mapped_column(
        Enum(ActorNotificationTaskStatus),
        default=ActorNotificationTaskStatus.PENDING,
        server_default=ActorNotificationTaskStatus.PENDING.name,
        index=True,
    )
    assignment_fingerprint: Mapped[str] = mapped_column(String(120), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True)
    supersedes_id: Mapped[int | None] = mapped_column(
        ForeignKey("actor_notification_tasks.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now()
    )
    revealed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ActorNotification(Base):
    __tablename__ = "actor_notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("actor_notification_tasks.id"), nullable=True
    )
    theater_id: Mapped[int] = mapped_column(ForeignKey("theaters.id"), index=True)
    performance_id: Mapped[int] = mapped_column(ForeignKey("performances.id"), index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("actors.id"), index=True)
    notification_type: Mapped[ActorNotificationType] = mapped_column(
        Enum(ActorNotificationType), index=True
    )
    schedule_version: Mapped[int] = mapped_column(Integer)
    theater_name_snapshot: Mapped[str] = mapped_column(String(120))
    performance_date_snapshot: Mapped[date] = mapped_column(Date, index=True)
    slot_name_snapshot: Mapped[str] = mapped_column(String(80))
    start_time_snapshot: Mapped[time] = mapped_column(Time)
    role_name_snapshot: Mapped[str] = mapped_column(String(120))
    player_name_snapshot: Mapped[str | None] = mapped_column(String(120), nullable=True)
    designation_type_snapshot: Mapped[str | None] = mapped_column(String(40), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(180), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now(), index=True
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SmsDelivery(Base):
    __tablename__ = "sms_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    notification_id: Mapped[int] = mapped_column(ForeignKey("actor_notifications.id"), index=True)
    theater_id: Mapped[int] = mapped_column(ForeignKey("theaters.id"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("actors.id"), index=True)
    masked_phone: Mapped[str] = mapped_column(String(30))
    status: Mapped[SmsDeliveryStatus] = mapped_column(
        Enum(SmsDeliveryStatus),
        default=SmsDeliveryStatus.PENDING,
        server_default=SmsDeliveryStatus.PENDING.name,
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(180), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


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
    weekly_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("weekly_batches.id"), nullable=True
    )
    performance_id: Mapped[int | None] = mapped_column(
        ForeignKey("performances.id", name="fk_designations_performance"), nullable=True
    )
    beneficiary_performance_player_id: Mapped[int | None] = mapped_column(
        ForeignKey("performance_players.id", name="fk_designations_beneficiary_performance_player"),
        nullable=True,
    )
    owner_player_id: Mapped[int | None] = mapped_column(
        ForeignKey("player_profiles.id", name="fk_designations_owner_player"), nullable=True
    )
    entitlement_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("entitlement_items.id", name="fk_designations_entitlement_item"), nullable=True
    )
    usage_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    verification_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    verified_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", name="fk_designations_verified_by"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    lifecycle_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    replaced_designation_id: Mapped[int | None] = mapped_column(
        ForeignKey("designations.id", name="fk_designations_replaced_designation"), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    current_version_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "designation_versions.id",
            name="fk_designations_current_version",
            use_alter=True,
        ),
        nullable=True,
    )
    role: Mapped[Role] = relationship()
    actor: Mapped[Actor] = relationship()
    target_performance: Mapped[Performance | None] = relationship(
        foreign_keys=[target_performance_id]
    )
    weekly_batch: Mapped[WeeklyBatch | None] = relationship()


class DesignationLifecycleEvent(Base):
    __tablename__ = "designation_lifecycle_events"
    __table_args__ = (
        UniqueConstraint(
            "designation_id", "action", "idempotency_key", name="uq_designation_action_idempotency"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    designation_id: Mapped[int] = mapped_column(ForeignKey("designations.id"), index=True)
    operator_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(40))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    request_hash: Mapped[str] = mapped_column(String(64))
    result_snapshot: Mapped[dict] = mapped_column(JSON)
    from_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    entitlement_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("entitlement_items.id"), nullable=True
    )
    conflict_designation_id: Mapped[int | None] = mapped_column(
        ForeignKey("designations.id"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now()
    )


class Wish(Base):
    __tablename__ = "wishes"
    __table_args__ = (UniqueConstraint("active_scope_key", name="uq_wish_active_scope_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    player_name: Mapped[str] = mapped_column(String(120))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("actors.id"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    weekly_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("weekly_batches.id"), nullable=True
    )
    performance_id: Mapped[int | None] = mapped_column(
        ForeignKey("performances.id", name="fk_wishes_performance"), nullable=True
    )
    performance_player_id: Mapped[int | None] = mapped_column(
        ForeignKey("performance_players.id", name="fk_wishes_performance_player"), nullable=True
    )
    status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    active_scope_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("wish_versions.id", name="fk_wishes_current_version", use_alter=True),
        nullable=True,
    )
    role: Mapped[Role] = relationship()
    actor: Mapped[Actor] = relationship()
    weekly_batch: Mapped[WeeklyBatch | None] = relationship()


class WishLifecycleEvent(Base):
    __tablename__ = "wish_lifecycle_events"
    __table_args__ = (
        UniqueConstraint("action", "idempotency_key", name="uq_wish_action_idempotency"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    wish_id: Mapped[int] = mapped_column(ForeignKey("wishes.id"), index=True)
    operator_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(40))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    request_hash: Mapped[str] = mapped_column(String(64))
    result_snapshot: Mapped[dict] = mapped_column(JSON)
    from_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now()
    )


class DesignationVersion(Base):
    __tablename__ = "designation_versions"
    __table_args__ = (
        UniqueConstraint("designation_id", "version_number", name="uq_designation_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    designation_id: Mapped[int] = mapped_column(ForeignKey("designations.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    player_name: Mapped[str] = mapped_column(String(120))
    actor_id: Mapped[int] = mapped_column(ForeignKey("actors.id"))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    usage_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    owner_player_id: Mapped[int | None] = mapped_column(
        ForeignKey("player_profiles.id"), nullable=True
    )
    entitlement_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("entitlement_items.id"), nullable=True
    )
    source_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("performance_board_revisions.id"), nullable=True
    )
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    correction_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class WishVersion(Base):
    __tablename__ = "wish_versions"
    __table_args__ = (UniqueConstraint("wish_id", "version_number", name="uq_wish_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    wish_id: Mapped[int] = mapped_column(ForeignKey("wishes.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    player_name: Mapped[str] = mapped_column(String(120))
    actor_id: Mapped[int] = mapped_column(ForeignKey("actors.id"))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    source_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("performance_board_revisions.id"), nullable=True
    )
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    correction_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FulfillmentFailure(Base):
    __tablename__ = "fulfillment_failures"

    id: Mapped[int] = mapped_column(primary_key=True)
    operation: Mapped[str] = mapped_column(String(60), index=True)
    business_kind: Mapped[str] = mapped_column(String(40), index=True)
    business_id: Mapped[int] = mapped_column(Integer, index=True)
    performance_id: Mapped[int | None] = mapped_column(
        ForeignKey("performances.id"), nullable=True, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True)
    error_code: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(40), default="pending", server_default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    operator_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=utc_now
    )


class ScheduleAssignment(Base):
    __tablename__ = "schedule_assignments"
    __table_args__ = (
        UniqueConstraint(
            "weekly_batch_id",
            "performance_id",
            "role_id",
            name="uq_schedule_assignment_batch_slot",
        ),
        Index(
            "ix_schedule_assignments_actor_performance",
            "actor_id",
            "performance_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    weekly_batch_id: Mapped[int] = mapped_column(ForeignKey("weekly_batches.id"), index=True)
    performance_id: Mapped[int] = mapped_column(ForeignKey("performances.id"), index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("actors.id"), index=True)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    locked: Mapped[bool] = mapped_column(default=False)
    requires_approval: Mapped[bool] = mapped_column(default=False)
    approved: Mapped[bool] = mapped_column(default=False)
    conflict_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    weekly_batch: Mapped[WeeklyBatch] = relationship(back_populates="assignments")
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    theater: Mapped[Theater] = relationship()
    assignments: Mapped[list[ScheduleAssignment]] = relationship(
        back_populates="weekly_batch", cascade="all, delete-orphan"
    )


class WeeklyPublishOperation(Base):
    __tablename__ = "weekly_publish_operations"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_weekly_publish_idempotency_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    theater_id: Mapped[int] = mapped_column(ForeignKey("theaters.id"), index=True)
    week_start: Mapped[date] = mapped_column(Date, index=True)
    weekly_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("weekly_batches.id"), nullable=True, index=True
    )
    operator_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    confirmation_token: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    unmet_scope_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unmet_scope: Mapped[list | None] = mapped_column(JSON, nullable=True)
    response_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PerformanceCastPublication(Base):
    __tablename__ = "performance_cast_publications"
    __table_args__ = (UniqueConstraint("performance_id", name="uq_performance_cast_publication"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    performance_id: Mapped[int] = mapped_column(ForeignKey("performances.id"), index=True)
    theater_id: Mapped[int] = mapped_column(ForeignKey("theaters.id"), index=True)
    weekly_batch_id: Mapped[int] = mapped_column(ForeignKey("weekly_batches.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    source_batch_version: Mapped[int] = mapped_column(Integer)
    assignment_hash: Mapped[str] = mapped_column(String(64))
    published_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    operator_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    assignments: Mapped[list[PublishedCastAssignment]] = relationship(
        back_populates="publication", cascade="all, delete-orphan"
    )


class PublishedCastAssignment(Base):
    __tablename__ = "published_cast_assignments"
    __table_args__ = (UniqueConstraint("publication_id", "role_id", name="uq_published_cast_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    publication_id: Mapped[int] = mapped_column(
        ForeignKey("performance_cast_publications.id"), index=True
    )
    performance_id: Mapped[int] = mapped_column(ForeignKey("performances.id"), index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("actors.id"), index=True)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    publication: Mapped[PerformanceCastPublication] = relationship(back_populates="assignments")


class DailyPublishOperation(Base):
    __tablename__ = "daily_publish_operations"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_daily_publish_idempotency_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(120))
    theater_id: Mapped[int] = mapped_column(ForeignKey("theaters.id"), index=True)
    performance_date: Mapped[date] = mapped_column(Date, index=True)
    weekly_batch_id: Mapped[int] = mapped_column(ForeignKey("weekly_batches.id"), index=True)
    operator_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    response_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class PersistentImportDraft(Base):
    __tablename__ = "import_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    weekly_batch_id: Mapped[int] = mapped_column(ForeignKey("weekly_batches.id"), index=True)
    raw_text: Mapped[str] = mapped_column(Text)
    status: Mapped[ImportDraftStatus] = mapped_column(
        Enum(ImportDraftStatus), default=ImportDraftStatus.DRAFT
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

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
    target_performance_id: Mapped[int | None] = mapped_column(
        ForeignKey("performances.id"), nullable=True
    )
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
