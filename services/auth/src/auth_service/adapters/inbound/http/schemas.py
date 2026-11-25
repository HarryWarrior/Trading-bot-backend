from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, EmailStr, Field

from auth_service.domain.tokens import AuthTokens
from auth_service.domain.user import User

MAX_PASSWORD_BYTES = 72  # bcrypt silently ignores anything beyond this


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


def _check_new_password(value: str) -> str:
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters")
    if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes in UTF-8")
    return value


Email = Annotated[EmailStr, BeforeValidator(_strip), Field(max_length=254)]
NewPassword = Annotated[str, AfterValidator(_check_new_password)]


class SignUpRequest(BaseModel):
    email: Email
    password: NewPassword
    name: str = Field(min_length=1, max_length=100)


class VerifyEmailRequest(BaseModel):
    email: Email
    code: str = Field(min_length=1, max_length=16)


class EmailRequest(BaseModel):
    email: Email


class SignInRequest(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=256)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=512)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    new_password: NewPassword


class UserOut(BaseModel):
    """Public view of a user. Deliberately has no ``password_hash``."""

    id: str
    email: str
    name: str
    role: str
    email_verified: bool
    created_at: datetime

    @classmethod
    def from_domain(cls, user: User) -> "UserOut":
        return cls(
            id=user.id,
            email=user.email,
            name=user.name,
            role=user.role.value,
            email_verified=user.email_verified,
            created_at=user.created_at,
        )


class UserEnvelope(BaseModel):
    user: UserOut


class TokensOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut

    @classmethod
    def from_domain(cls, tokens: AuthTokens) -> "TokensOut":
        return cls(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            expires_in=tokens.expires_in,
            user=UserOut.from_domain(tokens.user),
        )


class DeletedOut(BaseModel):
    deleted: int
