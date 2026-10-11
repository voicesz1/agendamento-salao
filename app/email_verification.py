from html import escape
from urllib.parse import urlencode

import httpx

from app.config import EMAIL_WEBHOOK_SECRET, EMAIL_WEBHOOK_URL, PUBLIC_BASE_URL


class EmailConfigurationError(RuntimeError):
    pass


class EmailDeliveryError(RuntimeError):
    pass


def send_confirmation_email(email: str, name: str, token: str) -> None:
    if not EMAIL_WEBHOOK_URL or len(EMAIL_WEBHOOK_SECRET) < 32 or not PUBLIC_BASE_URL:
        raise EmailConfigurationError("O envio de e-mail ainda não está configurado.")

    confirmation_url = f"{PUBLIC_BASE_URL}/cliente/verificar?{urlencode({'token': token})}"
    safe_name = escape(name)
    safe_url = escape(confirmation_url, quote=True)
    text_body = (
        f"Olá, {name}!\n\nAcesse este link para confirmar seu e-mail: "
        f"{confirmation_url}\n\nO link expira em 24 horas. Se você não criou esta conta, ignore esta mensagem."
    )
    html_body = (
        f"<p>Olá, {safe_name}!</p>"
        "<p>Para ativar sua conta, confirme seu endereço de e-mail:</p>"
        f'<p><a href="{safe_url}">Confirmar meu e-mail</a></p>'
        "<p>Este link expira em 24 horas. Se você não criou esta conta, ignore esta mensagem.</p>"
    )
    response = httpx.post(
        EMAIL_WEBHOOK_URL,
        json={
            "secret": EMAIL_WEBHOOK_SECRET,
            "to": email,
            "subject": "Confirme seu e-mail",
            "text": text_body,
            "html": html_body,
        },
        timeout=15,
        follow_redirects=True,
    )
    response.raise_for_status()
    try:
        result = response.json()
    except ValueError as exc:
        raise EmailDeliveryError("O serviço de e-mail retornou uma resposta inválida.") from exc
    if result.get("ok") is not True:
        raise EmailDeliveryError("O serviço de e-mail não aceitou a mensagem.")
