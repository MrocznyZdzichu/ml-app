import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Header, HTTPException, status

from app.core.config import settings

PBKDF2_ITERATIONS = 600_000
LEGACY_PBKDF2_ITERATIONS = 120_000


@dataclass(frozen=True)
class Principal:
    user_id: str
    email: str
    display_name: str
    roles: tuple[str, ...] = ("owner",)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    parts = password_hash.split("$")
    if len(parts) == 3:
        algorithm, salt, expected_digest = parts
        iterations = LEGACY_PBKDF2_ITERATIONS
    elif len(parts) == 4:
        algorithm, raw_iterations, salt, expected_digest = parts
        try:
            iterations = int(raw_iterations)
        except ValueError:
            return False
    else:
        return False
    if (
        algorithm != "pbkdf2_sha256"
        or iterations not in {LEGACY_PBKDF2_ITERATIONS, PBKDF2_ITERATIONS}
    ):
        return False
    actual_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return hmac.compare_digest(actual_digest, expected_digest)


def create_access_token(principal: Principal) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": principal.user_id,
        "email": principal.email,
        "display_name": principal.display_name,
        "roles": list(principal.roles),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_expire_minutes)).timestamp()),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded_payload = _base64url_encode(payload_bytes)
    signature = _sign(encoded_payload)
    return f"{encoded_payload}.{signature}"


def decode_access_token(token: str) -> Principal:
    try:
        encoded_payload, signature = token.split(".", 1)
    except ValueError as exc:
        raise _credentials_error() from exc

    if not hmac.compare_digest(signature, _sign(encoded_payload)):
        raise _credentials_error()

    try:
        payload = json.loads(_base64url_decode(encoded_payload))
    except (ValueError, json.JSONDecodeError) as exc:
        raise _credentials_error() from exc

    if not isinstance(payload, dict) or _is_expired(payload):
        raise _credentials_error()

    return Principal(
        user_id=str(payload.get("sub", "")),
        email=str(payload.get("email", "")),
        display_name=str(payload.get("display_name", "")),
        roles=tuple(str(role) for role in payload.get("roles", ["owner"])),
    )


def require_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> Principal:
    if not authorization:
        raise _credentials_error()

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _credentials_error()

    principal = decode_access_token(token)
    if not principal.user_id or not principal.email:
        raise _credentials_error()
    return principal


def _sign(encoded_payload: str) -> str:
    signature = hmac.new(
        settings.app_secret_key.encode("utf-8"),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _base64url_encode(signature)


def _base64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _base64url_decode(encoded: str) -> bytes:
    padded = encoded + "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _is_expired(payload: dict[str, Any]) -> bool:
    expires_at = payload.get("exp")
    if not isinstance(expires_at, int):
        return True
    return expires_at < int(datetime.now(timezone.utc).timestamp())


def _credentials_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )
