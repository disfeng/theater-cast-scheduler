from pydantic import BaseModel, model_validator


class LoginRequest(BaseModel):
    identifier: str | None = None
    email: str | None = None
    password: str

    @model_validator(mode="after")
    def require_identifier(self):
        if not (self.identifier or self.email):
            raise ValueError("identifier_required")
        return self

    @property
    def login_identifier(self) -> str:
        return str(self.identifier or self.email)


class TokenResponse(BaseModel):
    access_token: str
    role: str
    token_type: str = "bearer"
    must_change_password: bool = False
