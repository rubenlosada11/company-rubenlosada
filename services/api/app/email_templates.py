"""Plantillas de los emails de la API (AUTH-03), en español, con versión HTML y de texto plano.

HTML de email: tablas y estilos en línea (muchos clientes ignoran `<style>` y el CSS moderno), ancho máximo de 600 px
que se adapta al móvil, sin imágenes externas (los clientes las bloquean por defecto) y con el enlace también
escrito, por si el botón no funciona. Los valores se escapan con `html.escape`.
"""

from html import escape

from app.services.email import EmailMessage

# Paleta del backoffice (Tailwind): blue-700, blue-800, slate-900, slate-600, slate-200, slate-100.
_BLUE = "#1d4ed8"
_BLUE_DARK = "#1e40af"
_TEXT = "#0f172a"
_MUTED = "#475569"
_BORDER = "#e2e8f0"
_BACKGROUND = "#f1f5f9"
_FONT = "Arial, Helvetica, sans-serif"

PASSWORD_RESET_SUBJECT = "Restablece tu contraseña de TrackFlow"


def password_reset_email(to: str, reset_url: str, expire_minutes: int, *, idempotency_key: str | None = None
                         ) -> EmailMessage:
    """Email con el enlace de recuperación. `reset_url` lleva el token: no debe registrarse en ningún log."""
    url = escape(reset_url, quote=True)
    minutes = int(expire_minutes)
    html = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>{PASSWORD_RESET_SUBJECT}</title>
</head>
<body style="margin:0;padding:0;background:{_BACKGROUND};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">Usa este enlace en los próximos {minutes} \
minutos para elegir una contraseña nueva.</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_BACKGROUND};">
<tr><td align="center" style="padding:32px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;\
border:1px solid {_BORDER};border-radius:16px;">
<tr><td style="padding:32px 32px 8px 32px;font-family:{_FONT};">
<p style="margin:0;font-size:22px;font-weight:bold;color:{_BLUE_DARK};letter-spacing:-0.5px;">TrackFlow</p>
<p style="margin:4px 0 0 0;font-size:12px;font-weight:bold;letter-spacing:2px;text-transform:uppercase;\
color:{_MUTED};">Backoffice</p>
</td></tr>
<tr><td style="padding:16px 32px 0 32px;font-family:{_FONT};color:{_TEXT};">
<h1 style="margin:0 0 16px 0;font-size:24px;line-height:1.3;color:{_TEXT};">Restablece tu contraseña</h1>
<p style="margin:0 0 16px 0;font-size:16px;line-height:1.6;color:{_TEXT};">Hemos recibido una solicitud para \
restablecer la contraseña de tu cuenta del backoffice de TrackFlow. Pulsa el botón para elegir una nueva.</p>
</td></tr>
<tr><td align="left" style="padding:8px 32px 24px 32px;">
<table role="presentation" cellpadding="0" cellspacing="0"><tr>
<td style="border-radius:999px;background:{_BLUE};">
<a href="{url}" target="_blank" rel="noopener" style="display:inline-block;padding:14px 28px;font-family:{_FONT};\
font-size:16px;font-weight:bold;color:#ffffff;text-decoration:none;border-radius:999px;">Restablecer contraseña</a>
</td></tr></table>
</td></tr>
<tr><td style="padding:0 32px 8px 32px;font-family:{_FONT};">
<p style="margin:0 0 16px 0;font-size:14px;line-height:1.6;color:{_MUTED};">El enlace caduca en \
<strong style="color:{_TEXT};">{minutes} minutos</strong> y solo se puede usar una vez.</p>
<p style="margin:0 0 8px 0;font-size:14px;line-height:1.6;color:{_MUTED};">Si el botón no funciona, copia este \
enlace en tu navegador:</p>
<p style="margin:0 0 24px 0;font-size:13px;line-height:1.5;word-break:break-all;"><a href="{url}" target="_blank" \
rel="noopener" style="color:{_BLUE};">{url}</a></p>
</td></tr>
<tr><td style="padding:16px 32px 32px 32px;border-top:1px solid {_BORDER};font-family:{_FONT};">
<p style="margin:0;font-size:13px;line-height:1.6;color:{_MUTED};">Si no has pedido este cambio, ignora este correo: \
tu contraseña actual seguirá funcionando y nadie podrá cambiarla sin este enlace.</p>
</td></tr>
</table>
<p style="margin:16px 0 0 0;font-family:{_FONT};font-size:12px;color:{_MUTED};">TrackFlow Tech · Email automático, \
no respondas a este mensaje.</p>
</td></tr>
</table>
</body>
</html>
"""
    text = (
        "Restablece tu contraseña de TrackFlow\n\n"
        "Hemos recibido una solicitud para restablecer la contraseña de tu cuenta del backoffice de TrackFlow.\n\n"
        f"Abre este enlace para elegir una nueva:\n{reset_url}\n\n"
        f"El enlace caduca en {minutes} minutos y solo se puede usar una vez.\n\n"
        "Si no has pedido este cambio, ignora este correo: tu contraseña actual seguirá funcionando.\n\n"
        "TrackFlow Tech · Email automático, no respondas a este mensaje.\n"
    )
    return EmailMessage(to=to, subject=PASSWORD_RESET_SUBJECT, html=html, text=text, idempotency_key=idempotency_key)
