"""User management module with hashed credentials and role enforcement."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import yaml
from passlib.context import CryptContext
from pydantic import BaseModel, Field, field_validator


_DEFAULT_ROLES = {"admin", "operator", "viewer"}
_DEFAULT_ADMIN_PASSWORD = "admin123"


class User(BaseModel):
    """Represents a user with a hashed password and role assignments."""

    username: str
    password_hash: str
    roles: list[str] = Field(default_factory=lambda: ["viewer"])

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Username cannot be empty")
        return value

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("At least one role must be assigned")
        unknown = sorted(set(value) - _DEFAULT_ROLES)
        if unknown:
            raise ValueError(f"Unknown roles: {', '.join(unknown)}")
        return value


class UserStore:
    """Thread-safe YAML-backed storage for users with password hashing."""

    def __init__(self, path: Path | str = Path("config/users.yaml")) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        # Use PBKDF2-SHA256 for hashing to avoid strict bcrypt backend/version
        # coupling that can cause runtime failures when optional dependencies
        # are missing or incompatible.
        self._pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
        self._users: dict[str, User] | None = None
        self._ensure_default_admin()

    # Public API ---------------------------------------------------------
    def list_users(self) -> list[User]:
        with self._lock:
            return list(self._load_users().values())

    def get_user(self, username: str) -> Optional[User]:
        with self._lock:
            return self._load_users().get(username)

    def add_user(self, username: str, password: str, roles: Iterable[str]) -> User:
        with self._lock:
            users = self._load_users()
            if username in users:
                raise ValueError(f"User '{username}' already exists")

            user = User(
                username=username,
                password_hash=self._pwd_context.hash(password),
                roles=sorted(set(roles)),
            )
            users[username] = user
            self._persist(users)
            return user

    def update_user(
        self, username: str, password: Optional[str] = None, roles: Optional[Iterable[str]] = None
    ) -> User:
        with self._lock:
            users = self._load_users()
            if username not in users:
                raise ValueError(f"User '{username}' not found")

            user = users[username]
            if password:
                user.password_hash = self._pwd_context.hash(password)
            if roles is not None:
                user.roles = User.validate_roles(list(roles))
            users[username] = user
            self._persist(users)
            return user

    def delete_user(self, username: str) -> None:
        with self._lock:
            users = self._load_users()
            if username not in users:
                raise ValueError(f"User '{username}' not found")
            del users[username]
            self._persist(users)

    def authenticate(self, username: str, password: str) -> User:
        """Validate credentials and return the associated user."""

        with self._lock:
            users = self._load_users()
            user = users.get(username)
            if not user:
                raise ValueError("Invalid credentials")
            if not self._pwd_context.verify(password, user.password_hash):
                raise ValueError("Invalid credentials")
            return user

    # Internal helpers ----------------------------------------------------
    def _load_users(self) -> dict[str, User]:
        if self._users is None:
            self._users = self._read_users_file()
        return self._users

    def _read_users_file(self) -> dict[str, User]:
        if not self.path.exists():
            return {}
        with self.path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            raise ValueError("User file must contain a mapping of username to attributes")
        users: dict[str, User] = {}
        for username, payload in data.items():
            if not isinstance(payload, dict):
                raise ValueError(f"Invalid user payload for {username}")
            users[username] = User(username=username, **payload)
        return users

    def _persist(self, users: dict[str, User]) -> None:
        payload = {name: u.model_dump(exclude={"username"}) for name, u in users.items()}
        fd, tmp_path = tempfile.mkstemp(dir=self.path.parent, prefix=".users.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                yaml.safe_dump(payload, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, self.path)
            self._users = users
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def _ensure_default_admin(self) -> None:
        with self._lock:
            if self.path.exists():
                return
            self._persist(
                {
                    "admin": User(
                        username="admin",
                        password_hash=self._pwd_context.hash(_DEFAULT_ADMIN_PASSWORD),
                        roles=["admin"],
                    )
                }
            )


_user_store: UserStore | None = None


def get_user_store() -> UserStore:
    global _user_store
    if _user_store is None:
        _user_store = UserStore()
    return _user_store


@dataclass
class AuthenticatedUser:
    username: str
    roles: list[str]


# CLI utilities -----------------------------------------------------------


def _print_user(user: User) -> None:
    print(json.dumps({"username": user.username, "roles": sorted(user.roles)}, indent=2))


def _cli_list(store: UserStore, args: argparse.Namespace) -> None:  # noqa: ARG001
    for user in store.list_users():
        _print_user(user)


def _cli_create(store: UserStore, args: argparse.Namespace) -> None:
    user = store.add_user(args.username, args.password, args.roles)
    _print_user(user)


def _cli_update(store: UserStore, args: argparse.Namespace) -> None:
    user = store.update_user(args.username, password=args.password, roles=args.roles)
    _print_user(user)


def _cli_delete(store: UserStore, args: argparse.Namespace) -> None:
    store.delete_user(args.username)
    print(f"Deleted user {args.username}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Manage ONVIF reference NVR users")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parser_list = subparsers.add_parser("list", help="List users")
    parser_list.set_defaults(func=_cli_list)

    parser_create = subparsers.add_parser("create", help="Create a new user")
    parser_create.add_argument("username", help="Username")
    parser_create.add_argument("password", help="Plaintext password")
    parser_create.add_argument(
        "--roles",
        nargs="+",
        default=["viewer"],
        help="Roles to assign (default: viewer)",
    )
    parser_create.set_defaults(func=_cli_create)

    parser_update = subparsers.add_parser("update", help="Update an existing user")
    parser_update.add_argument("username", help="Username")
    parser_update.add_argument("--password", help="New password")
    parser_update.add_argument("--roles", nargs="+", help="Replace assigned roles")
    parser_update.set_defaults(func=_cli_update)

    parser_delete = subparsers.add_parser("delete", help="Delete a user")
    parser_delete.add_argument("username", help="Username")
    parser_delete.set_defaults(func=_cli_delete)

    args = parser.parse_args(argv)
    store = get_user_store()
    try:
        args.func(store, args)
    except ValueError as exc:  # pragma: no cover - CLI surface
        parser.error(str(exc))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())

