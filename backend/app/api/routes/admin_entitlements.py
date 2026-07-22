from fastapi import APIRouter

from app.api.routes import (
    admin_entitlement_catalog,
    admin_entitlement_grants,
    admin_entitlement_inventory,
    admin_entitlement_players,
    admin_entitlement_reconciliation,
)

router = APIRouter()
router.include_router(admin_entitlement_reconciliation.router)
router.include_router(admin_entitlement_players.router)
router.include_router(admin_entitlement_catalog.router)
router.include_router(admin_entitlement_grants.router)
router.include_router(admin_entitlement_inventory.router)
