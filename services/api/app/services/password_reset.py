"""Enlaces de recuperación de contraseña (`PasswordResetToken`) en TinyDB, tabla `password_reset_tokens`.

- El token en claro solo existe al emitirlo (va en el email); se guarda su SHA-256.
- Caduca a los `RESET_TOKEN_EXPIRE_MINUTES` (30 por defecto) y es de un solo uso.
- Usarlo es atómico: comprobarlo, marcarlo como usado y cambiar la contraseña ocurren bajo el candado de la base de
  usuarios, así que dos peticiones simultáneas con el mismo token no pueden pasar las dos. El candado es de proceso:
  la API debe correr con un solo worker (ya es requisito de TinyDB).

Aquí no se envía ningún email ni se decide qué responder al cliente: eso es de los routers (AUTH-03, fases 5–6).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from tinydb import Query, TinyDB

from app.auth_models import PasswordResetToken, User
from app.database import auth_db
from app.security import generate_reset_token, get_reset_token_expire_minutes, hash_reset_token
from app.services.users import USERS_TABLE

RESET_TOKENS_TABLE = "password_reset_tokens"

# Un usuario no puede pedir otro enlace hasta pasado este tiempo: evita usar la API para inundar su bandeja.
REQUEST_COOLDOWN = timedelta(seconds=60)
# Los enlaces caducados o usados se borran al emitir otros, cuando ya llevan este tiempo sin servir.
PURGE_AFTER = timedelta(hours=24)


class ResetTokenStatus(StrEnum):
    VALID = "valid"
    EXPIRED = "expired"
    USED = "used"
    NOT_FOUND = "not_found"


class InvalidResetToken(Exception):
    """El token no existe, ya se usó, ha caducado o su usuario ya no existe o está desactivado."""


@dataclass(frozen=True)
class IssuedResetToken:
    """Enlace recién emitido. `token` (en claro) solo debe ir al email; `id` sirve como clave de idempotencia."""

    id: str
    token: str
    expires_at: datetime


def _now() -> datetime:
    return datetime.now(UTC)


def _status(record: PasswordResetToken | None, now: datetime) -> ResetTokenStatus:
    if record is None:
        return ResetTokenStatus.NOT_FOUND
    if record.used_at is not None:
        return ResetTokenStatus.USED
    if now >= record.expires_at:
        return ResetTokenStatus.EXPIRED
    return ResetTokenStatus.VALID


def _find(db: TinyDB, token: str) -> PasswordResetToken | None:
    doc = db.table(RESET_TOKENS_TABLE).get(Query().token_hash == hash_reset_token(token))
    return PasswordResetToken.model_validate(doc) if doc else None


def _user_records(db: TinyDB, user_id: str) -> list[PasswordResetToken]:
    docs = db.table(RESET_TOKENS_TABLE).search(Query().user_id == user_id)
    return [PasswordResetToken.model_validate(doc) for doc in docs]


def _iso(moment: datetime) -> str:
    """Mismo formato que `model_dump(mode="json")` (UTC con `Z`), para que todas las fechas de la tabla coincidan."""
    return moment.isoformat().replace("+00:00", "Z")


def _purge_stale(db: TinyDB, now: datetime) -> None:
    """Borra los enlaces caducados o usados hace más de `PURGE_AFTER`, de cualquier usuario (también borrado)."""
    cutoff = now - PURGE_AFTER
    tokens = db.table(RESET_TOKENS_TABLE)
    stale = []
    for doc in tokens.all():
        record = PasswordResetToken.model_validate(doc)
        if record.expires_at <= cutoff or (record.used_at is not None and record.used_at <= cutoff):
            stale.append(doc.doc_id)
    if stale:
        tokens.remove(doc_ids=stale)


def issue_reset_token(user_id: str, *, now: datetime | None = None) -> IssuedResetToken | None:
    """Crea un enlace nuevo para `user_id` e invalida los anteriores.

    Devuelve `None` si el usuario ya pidió uno hace menos de `REQUEST_COOLDOWN` (el anterior sigue valiendo). No
    comprueba que el usuario exista: eso lo hace quien llama, sin revelarlo.
    """
    now = now or _now()
    token = generate_reset_token()
    record = PasswordResetToken(
        id=str(uuid.uuid4()),
        user_id=user_id,
        token_hash=hash_reset_token(token),
        created_at=now,
        expires_at=now + timedelta(minutes=get_reset_token_expire_minutes()),
    )
    with auth_db() as db:
        _purge_stale(db, now)
        previous = _user_records(db, user_id)
        if any(now - item.created_at < REQUEST_COOLDOWN for item in previous):
            return None
        tokens = db.table(RESET_TOKENS_TABLE)
        # Solo vale el último enlace pedido: los anteriores dejan de existir.
        tokens.remove(Query().user_id == user_id)
        tokens.insert(record.model_dump(mode="json"))
    return IssuedResetToken(id=record.id, token=token, expires_at=record.expires_at)


def reset_token_status(token: str, *, now: datetime | None = None) -> ResetTokenStatus:
    """Estado de un token (válido, caducado, usado o inexistente). Uso interno y en tests: no se expone al cliente."""
    with auth_db() as db:
        return _status(_find(db, token), now or _now())


def consume_reset_token(token: str, hashed_password: str, *, now: datetime | None = None) -> User:
    """Usa el token: guarda la nueva contraseña (ya hasheada) y lo marca como usado, todo en una sola operación.

    `hashed_password` se calcula antes de llamar (bcrypt tarda ~0,25 s y no debe retener el candado). Lanza
    `InvalidResetToken` sin cambiar nada si el token no es válido o su usuario ya no existe o está desactivado.
    """
    now = now or _now()
    with auth_db() as db:
        record = _find(db, token)
        if _status(record, now) is not ResetTokenStatus.VALID:
            raise InvalidResetToken
        users = db.table(USERS_TABLE)
        user_doc = users.get(Query().id == record.user_id)
        if user_doc is None or not user_doc.get("is_active", False):
            raise InvalidResetToken

        changes = {"hashed_password": hashed_password, "password_changed_at": _iso(now)}
        users.update(changes, Query().id == record.user_id)
        tokens = db.table(RESET_TOKENS_TABLE)
        tokens.update({"used_at": _iso(now)}, Query().id == record.id)
        # Cualquier otro enlace pendiente del usuario deja de servir.
        tokens.remove((Query().user_id == record.user_id) & (Query().id != record.id))
        return User.model_validate({**user_doc, **changes})


def revoke_reset_tokens(user_id: str) -> int:
    """Borra los enlaces pendientes de un usuario (p. ej. tras cambiar la contraseña estando autenticado)."""
    with auth_db() as db:
        pending = (Query().user_id == user_id) & (Query().used_at == None)  # noqa: E711 (consulta de TinyDB)
        return len(db.table(RESET_TOKENS_TABLE).remove(pending))
