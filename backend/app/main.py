from fastapi import FastAPI

from app.api.routes import actor, admin, admin_imports, auth, scheduling
from app.core.config import settings


app = FastAPI(title=settings.app_name)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(admin_imports.router)
app.include_router(actor.router)
app.include_router(scheduling.router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
