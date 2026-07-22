from app.main import app


WEEKLY_PATHS = {
    "/admin/weekly-schedules/workspace": {"get"},
    "/admin/weekly-schedules/validate": {"post"},
    "/admin/weekly-schedules/validate-context": {"post"},
    "/admin/weekly-schedules/recommend": {"post"},
    "/admin/weekly-schedules/draft": {"put"},
    "/admin/weekly-schedules/publish": {"post"},
    "/admin/weekly-schedules/publish-day": {"post"},
    "/admin/weekly-schedules/export": {"get"},
}

ACTOR_EXPORT_PATHS = {
    "/actor/me/calendar/export": {"get"},
}

ENTITLEMENT_PATHS = {
    "/admin/entitlement-grant-batches": {"get", "post"},
    "/admin/entitlement-grant-batches/{batch_id}": {"delete", "get", "patch"},
    "/admin/entitlement-grant-batches/{batch_id}/confirm": {"post"},
    "/admin/entitlement-item-types": {"get"},
    "/admin/entitlement-item-types/{type_id}": {"patch"},
    "/admin/entitlement-items/{item_id}": {"get"},
    "/admin/entitlement-items/{item_id}/adjust": {"post"},
    "/admin/entitlement-items/{item_id}/extend": {"post"},
    "/admin/entitlement-items/{item_id}/restore": {"post"},
    "/admin/entitlement-items/{item_id}/void": {"post"},
    "/admin/entitlements/reconciliation": {"get"},
    "/admin/entitlements/reconciliation/drill": {"get"},
    "/admin/player-profiles": {"get", "post"},
    "/admin/player-profiles/{player_id}": {"patch"},
    "/admin/player-profiles/{player_id}/aliases": {"post"},
    "/admin/player-profiles/{target_id}/merge": {"post"},
    "/admin/players/{player_id}/inventory": {"get"},
    "/admin/theaters/{theater_id}/entitlement-grant-batches": {"get", "post"},
    "/admin/theaters/{theater_id}/entitlement-grant-batches/{batch_id}/confirm": {"post"},
    "/admin/theaters/{theater_id}/entitlement-grant-player-matches": {"post"},
    "/admin/theaters/{theater_id}/entitlement-item-types": {"get", "post"},
    "/admin/theaters/{theater_id}/entitlement-item-types/default-designations": {"post"},
    "/admin/theaters/{theater_id}/entitlement-ledger": {"get"},
    "/admin/theaters/{theater_id}/players/{player_id}/inventory": {"get"},
    "/admin/theaters/{theater_id}/players/{player_id}/inventory/manual-consumption": {"post"},
    "/admin/theaters/{theater_id}/players/{player_id}/inventory/manual-consumption/preview": {
        "post"
    },
}


def test_phase_three_preserves_weekly_and_entitlement_http_contracts():
    paths = app.openapi()["paths"]

    for path, methods in {**WEEKLY_PATHS, **ENTITLEMENT_PATHS, **ACTOR_EXPORT_PATHS}.items():
        assert path in paths
        assert methods == {method for method in paths[path] if method != "parameters"}


def test_phase_three_service_modules_have_focused_boundaries():
    from app.services import (
        entitlement_catalog,
        entitlement_grants,
        entitlement_inventory,
        entitlement_lifecycle,
        entitlement_reconciliation,
        weekly_commands,
        weekly_conflicts,
        weekly_publication,
        weekly_workspace,
    )

    assert callable(weekly_workspace.get_workspace)
    assert callable(weekly_conflicts.validate_schedule)
    assert callable(weekly_commands.recommend_schedule)
    assert callable(weekly_publication.persist_schedule)
    assert callable(entitlement_catalog.validate_grant_binding)
    assert callable(entitlement_grants.confirm_grant_batch)
    assert callable(entitlement_inventory.inventory_for_player)
    assert callable(entitlement_lifecycle.reserve_item)
    assert callable(entitlement_reconciliation.reconciliation_drill)
