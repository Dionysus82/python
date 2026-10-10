"""Authenticated principal. Permissions come from configuration, not from documents."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import load_json
from app.models.tables import User, UserPortfolio


@dataclass(frozen=True)
class Principal:
    user_id: str
    username: str
    display_name: str
    role: str
    role_label: str
    line: str
    permissions: frozenset[str]
    portfolio_ids: frozenset[str]
    read_only: bool

    def can(self, permission: str) -> bool:
        return permission in self.permissions


def role_map() -> dict:
    return load_json("rbac.json")["roles"]  # type: ignore[index]


def load_principal(session: Session, username: str) -> Principal | None:
    user = session.scalar(select(User).where(User.username == username, User.active.is_(True)))
    if user is None:
        return None
    roles = role_map()
    role = roles[user.role]
    portfolios = session.scalars(
        select(UserPortfolio.portfolio_id).where(UserPortfolio.user_id == user.user_id)
    ).all()
    return Principal(
        user_id=user.user_id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        role_label=role["label"],
        line=role["line"],
        permissions=frozenset(role["permissions"]),
        portfolio_ids=frozenset(portfolios),
        read_only=bool(role["read_only"]),
    )
