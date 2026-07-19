from pydantic import BaseModel, Field


class PasswordChangeInput(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)


class ActorPasswordResetInput(BaseModel):
    entry_theater_id: int


class ActorProfileTheater(BaseModel):
    id: int
    name: str
    is_entry_theater: bool


class ActorProfileRead(BaseModel):
    id: int
    display_name: str
    phone_number: str
    must_change_password: bool
    theaters: list[ActorProfileTheater]
