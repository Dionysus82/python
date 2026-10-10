"""HMAC session tokens. This is a hackathon control, not production session management."""

from __future__ import annotations

import hashlib
import hmac
import time

from app.config import get_settings


def issue_token(username: str, secret: str | None = None, ttl_hours: int | None = None) -> str:
    settings = get_settings()
    secret = secret if secret is not None else settings.secret_key
    ttl = ttl_hours if ttl_hours is not None else settings.token_ttl_hours
    expires = int(time.time()) + ttl * 3600
    body = f"{username}|{expires}"
    signature = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{body}|{signature}"


def read_token(token: str, secret: str | None = None) -> str | None:
    settings = get_settings()
    secret = secret if secret is not None else settings.secret_key
    parts = token.split("|")
    if len(parts) != 3:
        return None
    username, expires, signature = parts
    body = f"{username}|{expires}"
    expected = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return None
    try:
        if int(expires) < int(time.time()):
            return None
    except ValueError:
        return None
    return username
