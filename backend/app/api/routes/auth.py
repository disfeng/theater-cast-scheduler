from fastapi import APIRouter, HTTPException

from app.schemas.auth import LoginRequest, TokenResponse
from app.services.auth import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    if payload.email == "admin@example.com" and payload.password == "admin":
        return TokenResponse(access_token=create_access_token(payload.email, "admin"))
    if payload.email == "actor@example.com" and payload.password == "actor":
        return TokenResponse(access_token=create_access_token(payload.email, "actor"))
    raise HTTPException(status_code=401, detail="Invalid credentials")
