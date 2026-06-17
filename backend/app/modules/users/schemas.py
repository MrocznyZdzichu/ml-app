from pydantic import BaseModel, EmailStr


class UserRead(BaseModel):
    user_id: str
    email: EmailStr
    display_name: str
    roles: list[str]
