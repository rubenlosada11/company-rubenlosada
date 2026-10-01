"""Usuarios (`User`) en TinyDB: alta con su perfil, consulta, modificación y baja.

La lógica de permisos (quién puede hacer qué) vive en los routers; aquí solo están las operaciones de datos.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from tinydb import Query, TinyDB

from app.auth_models import Profile, Role, User, UserCreate
from app.database import auth_db
from app.security import hash_password
from app.services.profiles import insert_profile, remove_profile

USERS_TABLE = "users"


class EmailAlreadyRegistered(Exception):
    """Ya hay un usuario con ese email."""


def _find_by_id(db: TinyDB, user_id: str) -> dict | None:
    return db.table(USERS_TABLE).get(Query().id == user_id)


def _find_by_email(db: TinyDB, email: str) -> dict | None:
    return db.table(USERS_TABLE).get(Query().email == email)


def create_user(data: UserCreate, role: Role = Role.USER) -> tuple[User, Profile]:
    """Crea el usuario (con la contraseña hasheada) y su perfil en la misma operación."""
    # bcrypt tarda ~0,25 s a propósito: se calcula fuera del candado para no bloquear la base.
    hashed_password = hash_password(data.password)
    with auth_db() as db:
        if _find_by_email(db, data.email) is not None:
            raise EmailAlreadyRegistered(data.email)
        user = User(
            id=str(uuid.uuid4()),
            email=data.email,
            hashed_password=hashed_password,
            is_active=True,
            role=role,
            created_at=datetime.now(UTC),
        )
        # `password_changed_at` solo se guarda a partir del primer cambio de contraseña.
        db.table(USERS_TABLE).insert(user.model_dump(mode="json", exclude={"password_changed_at"}))
        profile = insert_profile(db, user.id, data.model_dump(include={"name", "phone", "address"}))
    return user, profile


def get_user(user_id: str) -> User | None:
    with auth_db() as db:
        doc = _find_by_id(db, user_id)
    return User.model_validate(doc) if doc else None


def get_user_by_email(email: str) -> User | None:
    with auth_db() as db:
        doc = _find_by_email(db, email)
    return User.model_validate(doc) if doc else None


def list_users() -> list[User]:
    with auth_db() as db:
        docs = db.table(USERS_TABLE).all()
    return sorted((User.model_validate(doc) for doc in docs), key=lambda user: user.created_at)


def update_user(user_id: str, changes: dict[str, Any]) -> User | None:
    """Aplica `changes` (email, role, is_active). La contraseña tiene su propia función: `change_password`."""
    changes = dict(changes)
    if "role" in changes:
        changes["role"] = Role(changes["role"]).value

    with auth_db() as db:
        if _find_by_id(db, user_id) is None:
            return None
        if "email" in changes:
            owner = _find_by_email(db, changes["email"])
            if owner is not None and owner["id"] != user_id:
                raise EmailAlreadyRegistered(changes["email"])
        db.table(USERS_TABLE).update(changes, Query().id == user_id)
        return User.model_validate(_find_by_id(db, user_id))


def change_password(user_id: str, hashed_password: str) -> User | None:
    """Guarda la contraseña (ya hasheada) y la fecha del cambio, que invalida los JWT emitidos antes (AUTH-03)."""
    # Mismo formato que `model_dump(mode="json")`: UTC con `Z`.
    changed_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    with auth_db() as db:
        if _find_by_id(db, user_id) is None:
            return None
        changes = {"hashed_password": hashed_password, "password_changed_at": changed_at}
        db.table(USERS_TABLE).update(changes, Query().id == user_id)
        return User.model_validate(_find_by_id(db, user_id))


def delete_user(user_id: str) -> bool:
    """Borra el usuario y su perfil. Devuelve `False` si no existía."""
    with auth_db() as db:
        if not db.table(USERS_TABLE).remove(Query().id == user_id):
            return False
        remove_profile(db, user_id)
    return True
