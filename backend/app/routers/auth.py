"""Admin portal authentication.

Prototype-grade: PBKDF2 password hashing and a signed JWT. A production
deployment would federate against the department's identity provider.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import User
from ..schemas import LoginIn, TokenOut

router = APIRouter(prefix="/api/auth", tags=["auth"])

PBKDF2_ROUNDS = 120_000


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex),
                                 PBKDF2_ROUNDS)
    return hmac.compare_digest(digest.hex(), digest_hex)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_token(user: User) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps({
        "sub": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "exp": int(time.time()) + settings.jwt_ttl_hours * 3600,
    }, separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}".encode()
    signature = hmac.new(settings.jwt_secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64(signature)}"


def decode_token(token: str) -> dict:
    try:
        header, payload, signature = token.split(".")
    except ValueError:
        raise HTTPException(401, "Malformed token")

    expected = hmac.new(
        settings.jwt_secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(_unb64(signature), expected):
        raise HTTPException(401, "Invalid token signature")

    claims = json.loads(_unb64(payload))
    if claims.get("exp", 0) < time.time():
        raise HTTPException(401, "Token expired")
    return claims


def current_user(authorization: str = Header(default="")) -> dict:
    """Dependency for protected routes."""
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token")
    return decode_token(authorization.split(" ", 1)[1])


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(403, "Administrator role required")
    return user


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower().strip()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    return TokenOut(
        access_token=create_token(user),
        name=user.name,
        role=user.role,
        email=user.email,
    )


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return user
