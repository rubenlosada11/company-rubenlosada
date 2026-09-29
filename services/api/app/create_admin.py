"""Crea el primer administrador: `uv run create-admin <email>`.

`POST /users` es público y siempre crea usuarios con rol `user`, así que el primer `admin` se crea desde la máquina
donde está la base de datos. Si el email ya existe, lo convierte en `admin` y lo activa sin tocar su contraseña.
La contraseña se pide por teclado (sin eco); nunca se pasa como argumento para que no quede en el historial.
"""

import argparse
import getpass
import sys

from pydantic import ValidationError

from app.auth_models import Role, UserCreate, check_email
from app.database import get_auth_db_path
from app.services.users import create_user, get_user_by_email, update_user


def create_or_promote_admin(email: str, read_password=getpass.getpass) -> tuple[str, str]:
    """Devuelve `("creado" | "promovido", id)`. `read_password` se inyecta en los tests."""
    email = check_email(email)
    existing = get_user_by_email(email)
    if existing is not None:
        update_user(existing.id, {"role": Role.ADMIN, "is_active": True})
        return "promovido", existing.id

    password = read_password("Contraseña: ")
    if password != read_password("Repite la contraseña: "):
        raise ValueError("Las contraseñas no coinciden.")
    user, _ = create_user(UserCreate(email=email, password=password), role=Role.ADMIN)
    return "creado", user.id


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="create-admin", description="Crea o promueve un usuario administrador.")
    parser.add_argument("email")
    args = parser.parse_args()

    try:
        action, user_id = create_or_promote_admin(args.email)
    except ValidationError as error:
        sys.exit("; ".join(item["msg"].removeprefix("Value error, ") for item in error.errors()))
    except ValueError as error:
        sys.exit(str(error))

    print(f"Base de datos: {get_auth_db_path()}")
    print(f"Administrador {action}: {args.email.strip().lower()} (id {user_id})")


if __name__ == "__main__":
    main()
