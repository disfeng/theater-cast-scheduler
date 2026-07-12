from fastapi import APIRouter, Depends

from app.api.deps import require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/dashboard")
def dashboard(_: dict[str, str] = Depends(require_admin)) -> dict[str, int]:
    return {
        "pending_leave_requests": 0,
        "pending_designations": 0,
        "approval_required_assignments": 0,
        "unpublished_performances": 0,
    }
