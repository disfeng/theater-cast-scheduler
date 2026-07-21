from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.entities import (
    EntitlementGrantBatch,
    EntitlementGrantDraftItem,
    EntitlementItem,
    EntitlementItemType,
    EntitlementLedgerEntry,
    PlayerAlias,
    PlayerProfile,
)
from app.models.enums import (
    EntitlementEventType,
    EntitlementItemStatus,
    GrantBatchStatus,
    PlayerStatus,
)
from app.services.entitlements import (
    EntitlementConflict,
    confirm_grant_batch,
    consume_item,
    create_or_match_player,
    extend_item,
    normalize_player_name,
    release_item,
    reverse_consumption,
    reserve_item,
)


def _player(db_session, name="Alice"):
    player = PlayerProfile(display_name=name, normalized_name=normalize_player_name(name))
    db_session.add(player)
    db_session.commit()
    return player


def _item_type(db_session, months=3):
    item_type = EntitlementItemType(
        code=f"type-{months}", display_name="Test", priority=1, default_validity_months=months
    )
    db_session.add(item_type)
    db_session.commit()
    return item_type


def _available_item(db_session, *, expires_at=None):
    player = _player(db_session)
    item_type = _item_type(db_session)
    item = EntitlementItem(
        serial_number="DT-202607-0001",
        owner_id=player.id,
        item_type_id=item_type.id,
        source_month=date(2026, 7, 1),
        source_label="manual",
        granted_at=datetime(2026, 7, 1),
        expires_at=expires_at or datetime.utcnow() + timedelta(days=30),
        status=EntitlementItemStatus.AVAILABLE,
    )
    db_session.add(item)
    db_session.commit()
    return item


def test_normalized_name_ignores_whitespace_and_english_case():
    assert normalize_player_name("  Alice \t SMITH\n") == normalize_player_name("alice smith")


def test_reverse_consumption_restores_original_item_once(db_session):
    item = _available_item(db_session, expires_at=datetime.utcnow() + timedelta(days=30))
    reserve_item(db_session, item.id, designation_id=9, performance_id=7, operator_user_id=1)
    consume_item(db_session, item.id, operator_user_id=1)
    consumed = db_session.scalar(
        select(EntitlementLedgerEntry).where(
            EntitlementLedgerEntry.item_id == item.id,
            EntitlementLedgerEntry.event_type == EntitlementEventType.CONSUMED,
        )
    )

    restored = reverse_consumption(
        db_session,
        consumed.id,
        designation_id=9,
        reason="排班换演员",
        operator_user_id=1,
        idempotency_key="reverse-9",
    )
    replay = reverse_consumption(
        db_session,
        consumed.id,
        designation_id=9,
        reason="排班换演员",
        operator_user_id=1,
        idempotency_key="reverse-9",
    )

    assert restored.status == EntitlementItemStatus.AVAILABLE
    assert replay.id == restored.id
    reversal = db_session.scalar(
        select(EntitlementLedgerEntry).where(
            EntitlementLedgerEntry.reverses_entry_id == consumed.id
        )
    )
    assert reversal.event_type == EntitlementEventType.REVERSED


def test_ambiguous_alias_returns_candidates_without_creating_player(db_session):
    first = _player(db_session, "Alice One")
    second = _player(db_session, "Alice Two")
    db_session.add_all(
        [
            PlayerAlias(player_id=first.id, alias="Alice North", normalized_alias="alice north"),
            PlayerAlias(player_id=second.id, alias="Alice South", normalized_alias="alice south"),
        ]
    )
    db_session.commit()

    result = create_or_match_player(db_session, " alice ")

    assert result.player is None
    assert {candidate.id for candidate in result.candidates} == {first.id, second.id}
    assert (
        db_session.scalar(select(PlayerProfile).where(PlayerProfile.normalized_name == "alice"))
        is None
    )


def test_corrupt_cross_namespace_exact_match_returns_all_candidates(db_session):
    primary = _player(db_session, "Alice")
    alias_owner = _player(db_session, "Bob")
    db_session.add(PlayerAlias(player_id=alias_owner.id, alias="Alice", normalized_alias="alice"))
    db_session.commit()
    result = create_or_match_player(db_session, "alice")
    assert result.player is None
    assert {candidate.id for candidate in result.candidates} == {primary.id, alias_owner.id}


def test_create_flush_name_collision_rolls_back_and_resolves_winner(db_session, monkeypatch):
    original_flush = db_session.flush
    original_rollback = db_session.rollback
    original_commit = db_session.commit
    collided = False

    def flush_with_collision(*args, **kwargs):
        nonlocal collided
        if not collided:
            collided = True
            raise IntegrityError(
                "insert", {}, Exception("UNIQUE constraint failed: player_aliases.normalized_alias")
            )
        return original_flush(*args, **kwargs)

    def rollback_then_publish_winner():
        original_rollback()
        winner = PlayerProfile(display_name="Alice", normalized_name="alice")
        db_session.add(winner)
        original_flush()
        db_session.add(
            PlayerAlias(
                player_id=winner.id, alias="Alice", normalized_alias="alice", is_primary=True
            )
        )
        original_commit()

    monkeypatch.setattr(db_session, "flush", flush_with_collision)
    monkeypatch.setattr(db_session, "rollback", rollback_then_publish_winner)
    result = create_or_match_player(db_session, "Alice")
    assert result.player is not None
    assert result.player.normalized_name == "alice"
    assert result.created is False


def test_match_follows_legacy_merged_claim_to_active_target(db_session):
    target = PlayerProfile(
        display_name="Target", normalized_name="target", status=PlayerStatus.ACTIVE
    )
    source = PlayerProfile(display_name="Old", normalized_name="old", status=PlayerStatus.MERGED)
    db_session.add_all([target, source])
    db_session.flush()
    source.merged_into_id = target.id
    db_session.add(
        PlayerAlias(player_id=source.id, alias="Old", normalized_alias="old", is_primary=True)
    )
    db_session.commit()
    result = create_or_match_player(db_session, "old")
    assert result.player.id == target.id
    assert result.candidates == []


def test_draft_batch_does_not_change_inventory(db_session):
    player = _player(db_session)
    item_type = _item_type(db_session)
    batch = EntitlementGrantBatch(source_month=date(2026, 7, 1), source_label="July ranking")
    db_session.add(batch)
    db_session.flush()
    db_session.add_all(
        [
            EntitlementGrantDraftItem(
                batch_id=batch.id, player_id=player.id, item_type_id=item_type.id
            ),
            EntitlementGrantDraftItem(
                batch_id=batch.id, player_id=player.id, item_type_id=item_type.id
            ),
        ]
    )
    db_session.commit()

    assert batch.status == GrantBatchStatus.DRAFT
    assert db_session.scalar(select(EntitlementItem)) is None


def test_confirmation_creates_independent_items_and_grant_ledger_with_calendar_expiry(
    db_session, monkeypatch
):
    granted_at = datetime(2026, 11, 30, 12, 30)
    monkeypatch.setattr("app.services.entitlements.utcnow", lambda: granted_at)
    player = _player(db_session)
    item_type = _item_type(db_session, months=3)
    batch = EntitlementGrantBatch(source_month=date(2026, 11, 1), source_label="November ranking")
    db_session.add(batch)
    db_session.flush()
    db_session.add_all(
        [
            EntitlementGrantDraftItem(
                batch_id=batch.id, player_id=player.id, item_type_id=item_type.id
            ),
            EntitlementGrantDraftItem(
                batch_id=batch.id, player_id=player.id, item_type_id=item_type.id
            ),
        ]
    )
    db_session.commit()

    confirmed = confirm_grant_batch(db_session, batch.id, operator_user_id=7)
    items = list(db_session.scalars(select(EntitlementItem).order_by(EntitlementItem.id)))
    ledger = list(
        db_session.scalars(select(EntitlementLedgerEntry).order_by(EntitlementLedgerEntry.id))
    )

    assert confirmed.status == GrantBatchStatus.GRANTED
    assert [item.serial_number for item in items] == ["DT-202611-0001", "DT-202611-0002"]
    assert [item.expires_at for item in items] == [datetime(2027, 2, 28, 12, 30)] * 2
    assert [entry.event_type for entry in ledger] == [EntitlementEventType.GRANTED] * 2
    assert all('"operator_user_id": 7' in entry.note for entry in ledger)


def test_confirmation_preserves_per_item_source_and_expiry_overrides(db_session, monkeypatch):
    monkeypatch.setattr("app.services.entitlements.utcnow", lambda: datetime(2026, 7, 17, 9))
    player = _player(db_session)
    item_type = _item_type(db_session)
    batch = EntitlementGrantBatch(source_month=date(2026, 7, 1), source_label="batch source")
    db_session.add(batch)
    db_session.flush()
    db_session.add(
        EntitlementGrantDraftItem(
            batch_id=batch.id,
            player_id=player.id,
            item_type_id=item_type.id,
            source_month=date(2026, 6, 1),
            source_label="manual correction",
            expires_at=datetime(2027, 1, 2, 3, 4, 5),
        )
    )
    db_session.commit()

    confirm_grant_batch(db_session, batch.id, operator_user_id=1)
    item = db_session.scalar(select(EntitlementItem))

    assert item.source_month == date(2026, 6, 1)
    assert item.source_label == "manual correction"
    assert item.expires_at == datetime(2027, 1, 2, 3, 4, 5)


def test_reserve_succeeds_once_and_second_reservation_fails(db_session):
    item = _available_item(db_session)

    reserve_item(db_session, item.id, designation_id=10, performance_id=20, operator_user_id=1)
    with pytest.raises(EntitlementConflict, match="entitlement_already_reserved"):
        reserve_item(db_session, item.id, designation_id=11, performance_id=21, operator_user_id=1)


@pytest.mark.parametrize(
    ("expires_at", "expected"),
    [
        (datetime.utcnow() + timedelta(days=1), EntitlementItemStatus.AVAILABLE),
        (datetime.utcnow() - timedelta(days=1), EntitlementItemStatus.EXPIRED),
    ],
)
def test_release_returns_item_to_availability_based_on_expiry(db_session, expires_at, expected):
    item = _available_item(db_session, expires_at=expires_at)
    if expires_at <= datetime.utcnow():
        item.status = EntitlementItemStatus.RESERVED
        item.current_designation_id = 10
        db_session.commit()
    else:
        reserve_item(db_session, item.id, 10, 20, 1)

    released = release_item(db_session, item.id, "schedule changed", 1)

    assert released.status == expected
    assert released.current_designation_id is None


def test_consume_only_accepts_reserved_items(db_session):
    item = _available_item(db_session)
    with pytest.raises(EntitlementConflict, match="entitlement_not_reserved"):
        consume_item(db_session, item.id, 1)
    reserve_item(db_session, item.id, 10, 20, 1)
    assert consume_item(db_session, item.id, 1).status == EntitlementItemStatus.CONSUMED


def test_extension_records_old_new_expiry_and_reason(db_session):
    item = _available_item(db_session)
    old_expiry = item.expires_at
    new_expiry = old_expiry + timedelta(days=30)

    extend_item(db_session, item.id, new_expiry, "service recovery", 9)
    entry = db_session.scalars(
        select(EntitlementLedgerEntry).where(EntitlementLedgerEntry.item_id == item.id)
    ).all()[-1]

    assert item.expires_at == new_expiry
    assert f'"old_expires_at": "{old_expiry.isoformat()}"' in entry.note
    assert f'"new_expires_at": "{new_expiry.isoformat()}"' in entry.note
    assert '"reason": "service recovery"' in entry.note


def test_confirmation_rejects_provisional_player(db_session):
    player = PlayerProfile(display_name="Pending", normalized_name="pending", status="PROVISIONAL")
    item_type = _item_type(db_session)
    batch = EntitlementGrantBatch(source_month=date(2026, 7, 1), source_label="July")
    db_session.add_all([player, batch])
    db_session.flush()
    db_session.add(
        EntitlementGrantDraftItem(batch_id=batch.id, player_id=player.id, item_type_id=item_type.id)
    )
    db_session.commit()
    with pytest.raises(EntitlementConflict, match="player_not_confirmed"):
        confirm_grant_batch(db_session, batch.id, 1)


def test_serial_unique_conflict_is_stable_and_rolls_back(db_session, monkeypatch):
    player = _player(db_session)
    item_type = _item_type(db_session)
    batch = EntitlementGrantBatch(source_month=date(2026, 7, 1), source_label="July")
    db_session.add(batch)
    db_session.flush()
    db_session.add(
        EntitlementGrantDraftItem(batch_id=batch.id, player_id=player.id, item_type_id=item_type.id)
    )
    db_session.commit()
    monkeypatch.setattr(
        db_session,
        "commit",
        lambda: (_ for _ in ()).throw(
            IntegrityError(
                "insert", {}, Exception("UNIQUE constraint failed: entitlement_items.serial_number")
            )
        ),
    )
    with pytest.raises(EntitlementConflict, match="entitlement_serial_conflict"):
        confirm_grant_batch(db_session, batch.id, 1)
    assert batch.status == GrantBatchStatus.DRAFT


def test_serial_unique_conflict_retries_and_recovers(db_session, monkeypatch):
    player = _player(db_session)
    item_type = _item_type(db_session)
    batch = EntitlementGrantBatch(source_month=date(2026, 7, 1), source_label="July")
    db_session.add(batch)
    db_session.flush()
    db_session.add(
        EntitlementGrantDraftItem(batch_id=batch.id, player_id=player.id, item_type_id=item_type.id)
    )
    db_session.commit()
    original_commit = db_session.commit
    attempts = 0

    def conflict_once():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise IntegrityError("insert", {}, Exception("Duplicate entry for key 'serial_number'"))
        original_commit()

    monkeypatch.setattr(db_session, "commit", conflict_once)
    confirmed = confirm_grant_batch(db_session, batch.id, 1)
    assert confirmed.status == GrantBatchStatus.GRANTED
    assert attempts == 2


def test_non_serial_integrity_error_is_not_misreported_or_retried(db_session, monkeypatch):
    player = _player(db_session)
    item_type = _item_type(db_session)
    batch = EntitlementGrantBatch(source_month=date(2026, 7, 1), source_label="July")
    db_session.add(batch)
    db_session.flush()
    db_session.add(
        EntitlementGrantDraftItem(batch_id=batch.id, player_id=player.id, item_type_id=item_type.id)
    )
    db_session.commit()
    attempts = 0

    def invalid_operator_fk():
        nonlocal attempts
        attempts += 1
        raise IntegrityError("insert", {}, Exception("FOREIGN KEY constraint failed"))

    monkeypatch.setattr(db_session, "commit", invalid_operator_fk)
    with pytest.raises(EntitlementConflict, match="entitlement_integrity_error"):
        confirm_grant_batch(db_session, batch.id, 999)
    assert attempts == 1
