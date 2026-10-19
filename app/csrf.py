import hmac
import secrets

from fastapi import Form, HTTPException, Request


def csrf_value(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def validate_csrf(request: Request, csrf: str = Form(...)) -> None:
    expected = request.session.get("csrf_token", "")
    if not expected or not hmac.compare_digest(expected, csrf):
        raise HTTPException(status_code=403, detail="Requisição inválida. Atualize a página e tente novamente.")
