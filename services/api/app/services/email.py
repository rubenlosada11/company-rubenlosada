"""Envío de emails (AUTH-03): interfaz `EmailSender` y su implementación con Resend.

Configuración por variables de entorno (ver `.env.example`), leída en cada uso como el resto de la API:

- `RESEND_API_KEY` (opcional): clave de la API de Resend. Sin ella la API arranca, pero no envía emails (se registra
  un aviso). Solo vive en el `.env` del servidor: nunca en el código, en git ni en el frontend.
- `MAIL_FROM` (obligatoria si hay clave): remitente, `Nombre <direccion@dominio>`. El dominio debe estar verificado en
  Resend (sin dominio, Resend solo admite `onboarding@resend.dev` y entrega únicamente al titular de la cuenta).

Los routers no hablan con Resend: piden un `EmailSender` con la dependencia `get_email_sender` (los tests la sustituyen
por un emisor falso) y envían con `deliver`, que nunca lanza y registra los fallos sin datos sensibles.

Se usa la API REST de Resend con `urllib` (biblioteca estándar): es un solo `POST` y no merece una dependencia.
"""

import json
import logging
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from app.security import ConfigError

RESEND_API_URL = "https://api.resend.com/emails"
REQUEST_TIMEOUT_SECONDS = 10
USER_AGENT = "trackflow-api/0.1.0"

logger = logging.getLogger("trackflow.email")

# Remitente: `direccion@dominio.tld` o `Nombre <direccion@dominio.tld>`. El nombre no admite `<`, `>`, `@`, `=` ni
# comillas: así se detectan errores de copia como `MAIL_FROM=MAIL_FROM="…"`, que Resend aceptaría (con un nombre
# absurdo).
_ADDRESS = r'[^\s<>@"]+@[^\s<>@".]+(?:\.[^\s<>@".]+)+'
MAIL_FROM_PATTERN = re.compile(rf'{_ADDRESS}|[^<>@="\r\n]+ <{_ADDRESS}>')


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    html: str
    text: str
    # Resend no repite un envío con la misma clave en 24 h (protege de reintentos). Máximo 256 caracteres.
    idempotency_key: str | None = None


class EmailError(Exception):
    """El proveedor rechazó el envío o no respondió.

    Solo guarda el código HTTP (0 = sin respuesta) y el tipo de error de Resend (`validation_error`,
    `rate_limit_exceeded`…), nunca su mensaje: puede incluir direcciones de email.
    """

    def __init__(self, status: int, kind: str):
        super().__init__(f"{kind} ({status})")
        self.status = status
        self.kind = kind


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> str | None:
        """Envía el email y devuelve el id del proveedor (o `None` si no se envía). Lanza `EmailError` si falla."""
        ...


def get_resend_api_key() -> str | None:
    return os.environ.get("RESEND_API_KEY", "").strip() or None


def get_mail_from() -> str | None:
    return os.environ.get("MAIL_FROM", "").strip() or None


def check_email_config() -> None:
    """Falla al arrancar si hay clave de Resend pero no un remitente válido (si no, cada envío fallaría)."""
    if get_resend_api_key() is None:
        return
    mail_from = get_mail_from()
    if mail_from is None:
        raise ConfigError(
            'MAIL_FROM es obligatoria si defines RESEND_API_KEY, p. ej. MAIL_FROM="TrackFlow <no-reply@tu-dominio>" '
            "con un dominio verificado en Resend."
        )
    if not MAIL_FROM_PATTERN.fullmatch(mail_from):
        raise ConfigError(
            'MAIL_FROM debe ser "direccion@dominio" o "Nombre <direccion@dominio>", p. ej. '
            'MAIL_FROM="TrackFlow <no-reply@tu-dominio>" (revisa que la línea no repita "MAIL_FROM=").'
        )


class ResendSender:
    """Envía con `POST https://api.resend.com/emails` (Bearer + JSON)."""

    def __init__(self, api_key: str, mail_from: str, *, url: str = RESEND_API_URL):
        self._api_key = api_key
        self._mail_from = mail_from
        self._url = url

    def __repr__(self) -> str:
        # Nunca mostrar la clave, ni siquiera en una traza de error.
        return f"ResendSender(mail_from={self._mail_from!r})"

    def send(self, message: EmailMessage) -> str | None:
        body = {
            "from": self._mail_from,
            "to": [message.to],
            "subject": message.subject,
            "html": message.html,
            "text": message.text,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            # Sin User-Agent propio, algunos proxies rechazan el de urllib por defecto.
            "User-Agent": USER_AGENT,
        }
        if message.idempotency_key:
            headers["Idempotency-Key"] = message.idempotency_key
        request = urllib.request.Request(
            self._url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            raise EmailError(error.code, _error_kind(error)) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise EmailError(0, "connection_error") from None
        except ValueError:
            raise EmailError(200, "invalid_response") from None
        return payload.get("id") if isinstance(payload, dict) else None


def _error_kind(error: urllib.error.HTTPError) -> str:
    """Tipo de error de Resend (`{"name": "validation_error", "message": …}`), sin leer ni conservar el mensaje."""
    try:
        name = json.loads(error.read() or b"{}").get("name")
    except (ValueError, AttributeError, OSError):
        name = None
    return name if isinstance(name, str) and name.isidentifier() else "http_error"


class DisabledSender:
    """Sin `RESEND_API_KEY`: no envía nada. La API sigue funcionando y lo avisa en el log (sin el contenido)."""

    def send(self, message: EmailMessage) -> str | None:
        logger.warning("Email no enviado: falta RESEND_API_KEY en la configuración de la API.")
        return None


def get_email_sender() -> EmailSender:
    """Dependencia de FastAPI: `sender: EmailSender = Depends(get_email_sender)`."""
    api_key = get_resend_api_key()
    if api_key is None:
        return DisabledSender()
    check_email_config()
    return ResendSender(api_key, get_mail_from() or "")


def deliver(sender: EmailSender, message: EmailMessage, *, purpose: str, user_id: str) -> bool:
    """Envía y devuelve si salió bien. Pensada para `BackgroundTasks`: nunca lanza.

    El log identifica el envío solo por su propósito y el id del usuario: nunca el destinatario, el asunto, el cuerpo
    (contiene el enlace de recuperación) ni la clave.
    """
    try:
        provider_id = sender.send(message)
    except EmailError as error:
        logger.warning(
            "Email %s para el usuario %s no enviado: %s (HTTP %s).", purpose, user_id, error.kind, error.status
        )
        return False
    except Exception as error:  # noqa: BLE001 - un fallo inesperado no debe tumbar la tarea
        # Solo el tipo: el mensaje o la traza de un error inesperado podrían arrastrar el contenido del email.
        logger.warning(
            "Email %s para el usuario %s no enviado: error inesperado (%s).", purpose, user_id, type(error).__name__
        )
        return False
    if provider_id:
        logger.info("Email %s para el usuario %s enviado (id %s).", purpose, user_id, provider_id)
    return provider_id is not None
