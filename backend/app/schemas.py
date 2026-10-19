from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    role: str
    active: bool

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    name: str = ""
    password: str = Field(min_length=8)
    role: str = "analyst"


class UserPatch(BaseModel):
    name: str | None = None
    role: str | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=8)


class StepRun(BaseModel):
    selected: list[str] | None = None
    ref_date: str | None = None  # YYYY-MM-DD


class SheetPick(BaseModel):
    sheet: str


class MappingIn(BaseModel):
    mapping: dict
