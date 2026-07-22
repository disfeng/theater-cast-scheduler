import pytest

from app.models.entities import EntitlementItem, EntitlementItemType
from app.models.enums import EntitlementGrantMode
from app.services.entitlement_binding import (
    EntitlementBindingError,
    validate_designation_binding,
    validate_grant_mode,
)


@pytest.mark.parametrize(
    ("binds_actor", "mode", "allowed"),
    [
        (False, EntitlementGrantMode.BY_PLAYER, True),
        (False, EntitlementGrantMode.BY_ACTOR, False),
        (True, EntitlementGrantMode.BY_PLAYER, False),
        (True, EntitlementGrantMode.BY_ACTOR, True),
    ],
)
def test_grant_mode_follows_actor_binding(binds_actor, mode, allowed):
    item_type = EntitlementItemType(binds_actor=binds_actor)
    if allowed:
        validate_grant_mode(item_type, mode)
    else:
        with pytest.raises(EntitlementBindingError, match="entitlement_grant_mode_mismatch"):
            validate_grant_mode(item_type, mode)


@pytest.mark.parametrize(
    ("binds_beneficiary", "binds_actor", "beneficiary", "actor", "error"),
    [
        (False, False, 20, 200, None),
        (True, False, 20, 200, "entitlement_beneficiary_mismatch"),
        (False, True, 20, 200, "entitlement_bound_actor_mismatch"),
        (True, True, 10, 100, None),
    ],
)
def test_designation_binding_uses_inventory_snapshots(
    binds_beneficiary, binds_actor, beneficiary, actor, error
):
    item = EntitlementItem(
        owner_id=10,
        bound_actor_id=100,
        binds_beneficiary_snapshot=binds_beneficiary,
        binds_actor_snapshot=binds_actor,
    )
    if error:
        with pytest.raises(EntitlementBindingError, match=error):
            validate_designation_binding(item, beneficiary, actor)
    else:
        validate_designation_binding(item, beneficiary, actor)
