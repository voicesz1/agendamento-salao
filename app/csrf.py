import hmac
import secrets

from fastapi import Form, Header, HTTPException, Request


def csrf_value(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def validate_csrf(request: Request, csrf: str = Form(...)) -> None:
    expected = request.session.get("csrf_token", "")
    if not expected or not hmac.compare_digest(expected.encode(), csrf.encode()):
        raise HTTPException(status_code=403, detail="Requisição inválida. Atualize a página e tente novamente.")


def validate_csrf_header(request: Request, x_csrf_token: str = Header("")) -> None:
    validate_csrf(request, x_csrf_token)
