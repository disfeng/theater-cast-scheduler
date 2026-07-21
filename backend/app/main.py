from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    actor,
    admin,
    admin_entitlements,
    admin_designation_workspace,
    admin_imports,
    admin_performance_boards,
    admin_security,
    admin_weekly_scheduling,
    auth,
    scheduling,
)
from app.core.config import settings


app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:7003",
        "http://127.0.0.1:7003",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(admin_entitlements.router)
app.include_router(admin_designation_workspace.router)
app.include_router(admin_imports.router)
app.include_router(admin_performance_boards.router)
app.include_router(admin_weekly_scheduling.router)
app.include_router(admin_security.router)
app.include_router(actor.router)
app.include_router(scheduling.router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
