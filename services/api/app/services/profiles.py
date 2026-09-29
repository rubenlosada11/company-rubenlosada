"""Perfiles (`Profile`) en TinyDB: uno por usuario, enlazado por `user_id`.

Las funciones con `db` como primer parámetro trabajan dentro de una base ya abierta (y bajo su candado), para que
`app/services/users.py` pueda crear o borrar usuario y perfil en la misma operación.
"""

import uuid
from typing import Any

from tinydb import Query, TinyDB

from app.auth_models import Profile
from app.database import auth_db

PROFILES_TABLE = "profiles"


def _find(db: TinyDB, user_id: str) -> dict | None:
    return db.table(PROFILES_TABLE).get(Query().user_id == user_id)


def insert_profile(db: TinyDB, user_id: str, data: dict[str, Any] | None = None) -> Profile:
    profile = Profile(id=str(uuid.uuid4()), user_id=user_id, **(data or {}))
    db.table(PROFILES_TABLE).insert(profile.model_dump())
    return profile


def remove_profile(db: TinyDB, user_id: str) -> bool:
    return bool(db.table(PROFILES_TABLE).remove(Query().user_id == user_id))


def get_profile_by_user_id(user_id: str) -> Profile | None:
    with auth_db() as db:
        doc = _find(db, user_id)
    return Profile.model_validate(doc) if doc else None


def get_or_create_profile(user_id: str) -> Profile:
    """Perfil del usuario; si faltara (p. ej. datos creados a mano), se crea vacío para mantener la relación 1:1."""
    with auth_db() as db:
        doc = _find(db, user_id)
        return Profile.model_validate(doc) if doc else insert_profile(db, user_id)


def update_profile(user_id: str, changes: dict[str, Any]) -> Profile:
    """Aplica `changes` (solo `name`, `phone`, `address`) al perfil del usuario, creándolo si no existe."""
    with auth_db() as db:
        if _find(db, user_id) is None:
            return insert_profile(db, user_id, changes)
        db.table(PROFILES_TABLE).update(changes, Query().user_id == user_id)
        return Profile.model_validate(_find(db, user_id))


def delete_profile(user_id: str) -> bool:
    with auth_db() as db:
        return remove_profile(db, user_id)
