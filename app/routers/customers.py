import hmac
import re
import secrets
import time
from datetime import datetime, timedelta
from hashlib import sha256
from threading import Lock

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.config import BASE_DIR, TIMEZONE
from app.database import get_db
from app.email_verification import EmailConfigurationError, EmailDeliveryError, send_confirmation_email
from app.models import Appointment, Customer
from app.security import hash_password, verify_password
from app.settings_store import get_setting

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
router = APIRouter(prefix="/cliente")
LOGIN_FAILURES: dict[str, list[float]] = {}
LOGIN_LOCK = Lock()
EMAIL_SENDS: dict[str, list[float]] = {}
VERIFICATION_LIFETIME = timedelta(hours=24)


def safe_next_path(value: str | None) -> str:
    return "/agendar" if value == "/agendar" else ""


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


def page_context(request: Request, db: Session, **values) -> dict:
    return {
        "salon_name": get_setting(db, "salon_name", "Salão"),
        "salon_tagline": get_setting(db, "salon_tagline", ""),
        "csrf_token": csrf_value(request),
        **values,
    }


def current_customer(request: Request, db: Session) -> Customer | None:
    customer_id = request.session.get("customer_id")
    if not isinstance(customer_id, int):
        return None
    customer = db.get(Customer, customer_id)
    if customer is None:
        request.session.pop("customer_id", None)
    return customer


def issue_verification(customer: Customer, db: Session, next_path: str = "") -> str:
    token = secrets.token_urlsafe(32)
    customer.verification_token_hash = sha256(token.encode()).hexdigest()
    customer.verification_expires_at = datetime.now(TIMEZONE).replace(tzinfo=None) + VERIFICATION_LIFETIME
    db.commit()
    send_confirmation_email(customer.email, customer.name, token, next_path=safe_next_path(next_path))
    return token


def allow_email_send(request: Request) -> bool:
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with LOGIN_LOCK:
        recent = [stamp for stamp in EMAIL_SENDS.get(ip, []) if now - stamp < 3600]
        if len(recent) >= 5:
            EMAIL_SENDS[ip] = recent
            return False
        recent.append(now)
        EMAIL_SENDS[ip] = recent
        return True


@router.get("/cadastro", response_class=HTMLResponse)
def register_form(request: Request, next: str | None = None, db: Session = Depends(get_db)):
    next_path = safe_next_path(next)
    if current_customer(request, db):
        return RedirectResponse(next_path or "/cliente/minha-conta", status_code=303)
    return templates.TemplateResponse(
        request,
        "customer/auth.html",
        page_context(request, db, mode="register", error=None, next_path=next_path),
    )


@router.post("/cadastro", response_class=HTMLResponse)
def register(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    password: str = Form(...),
    next_path: str = Form(""),
    _csrf: None = Depends(validate_csrf),
    db: Session = Depends(get_db),
):
    next_path = safe_next_path(next_path)
    normalized_email = email.strip().lower()
    phone_digits = "".join(ch for ch in phone if ch.isdigit())
    error = None
    if not 2 <= len(name.strip()) <= 120:
        error = "Informe seu nome completo."
    elif len(normalized_email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized_email):
        error = "Informe um e-mail válido."
    elif not 10 <= len(phone_digits) <= 15:
        error = "Informe um WhatsApp válido com DDD e número."
    elif len(password) < 12:
        error = "A senha precisa ter pelo menos 12 caracteres."
    elif db.query(Customer).filter(Customer.email == normalized_email).first():
        error = "Já existe uma conta com este e-mail. Entre ou use outro e-mail."
    elif not allow_email_send(request):
        error = "Limite de envio atingido. Tente novamente daqui a uma hora."

    if error:
        return templates.TemplateResponse(
            request,
            "customer/auth.html",
            page_context(request, db, mode="register", error=error, name=name.strip(), email=normalized_email, phone=phone, next_path=next_path),
            status_code=400,
        )

    token = secrets.token_urlsafe(32)
    customer = Customer(
        name=name.strip(),
        email=normalized_email,
        phone=phone_digits,
        password_hash=hash_password(password),
        created_at=datetime.now(TIMEZONE).replace(tzinfo=None),
        verification_token_hash=sha256(token.encode()).hexdigest(),
        verification_expires_at=datetime.now(TIMEZONE).replace(tzinfo=None) + VERIFICATION_LIFETIME,
    )
    db.add(customer)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(
            request,
            "customer/auth.html",
            page_context(request, db, mode="register", error="Já existe uma conta com este e-mail.", name=name.strip(), email=normalized_email, phone=phone, next_path=next_path),
            status_code=400,
        )

    try:
        send_confirmation_email(customer.email, customer.name, token, next_path=next_path)
        notice = "Conta criada. Enviamos um link de confirmação para seu e-mail; ele expira em 24 horas."
        mail_error = None
    except (EmailConfigurationError, EmailDeliveryError, httpx.HTTPError):
        notice = None
        mail_error = "Sua conta foi criada, mas não foi possível enviar o e-mail agora. Você pode tentar reenviar abaixo."
    request.session.pop("customer_id", None)
    request.session.pop("admin", None)
    return templates.TemplateResponse(
        request,
        "customer/auth.html",
        page_context(
            request, db, mode="register", error=None, notice=notice, mail_error=mail_error,
            show_resend=True, email=normalized_email, next_path=next_path,
        ),
    )


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, next: str | None = None, db: Session = Depends(get_db)):
    next_path = safe_next_path(next)
    if current_customer(request, db):
        return RedirectResponse(next_path or "/cliente/minha-conta", status_code=303)
    if request.session.get("admin") is True:
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(
        request,
        "customer/auth.html",
        page_context(request, db, mode="login", error=None, next_path=next_path),
    )


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    username_or_email: str = Form(...),
    password: str = Form(...),
    next_path: str = Form(""),
    _csrf: None = Depends(validate_csrf),
    db: Session = Depends(get_db),
):
    next_path = safe_next_path(next_path)
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with LOGIN_LOCK:
        failures = [stamp for stamp in LOGIN_FAILURES.get(client_ip, []) if now - stamp < 900]
        if len(failures) >= 10:
            return HTMLResponse("Muitas tentativas. Aguarde 15 minutos antes de tentar novamente.", status_code=429)
        failures.append(now)
        LOGIN_FAILURES[client_ip] = failures

    identifier = username_or_email.strip().lower()
    customer = db.query(Customer).filter(Customer.email == identifier).first()
    valid_customer = bool(customer and verify_password(password, customer.password_hash))
    admin_password_hash = get_setting(db, "admin_password_hash")
    is_owner = identifier == "dona" and admin_password_hash and verify_password(password, admin_password_hash)
    if is_owner or (valid_customer and customer.email_verified_at):
        with LOGIN_LOCK:
            LOGIN_FAILURES.pop(client_ip, None)
        request.session.clear()
        if is_owner:
            request.session["admin"] = True
            return RedirectResponse("/admin", status_code=303)
        request.session["customer_id"] = customer.id
        csrf_value(request)
        return RedirectResponse(next_path or "/cliente/minha-conta", status_code=303)

    if valid_customer and not customer.email_verified_at:
        return templates.TemplateResponse(
            request,
            "customer/auth.html",
            page_context(
                request, db, mode="login",
                error="Confirme seu e-mail antes de entrar. Se não recebeu o link, solicite outro abaixo.",
                username_or_email=identifier, email=identifier, show_resend=True, next_path=next_path,
            ),
            status_code=401,
        )

    return templates.TemplateResponse(
        request,
        "customer/auth.html",
        page_context(request, db, mode="login", error="Usuário/e-mail ou senha incorretos.", username_or_email=username_or_email.strip(), next_path=next_path),
        status_code=401,
    )


@router.post("/reenviar-confirmacao", response_class=HTMLResponse)
def resend_confirmation(
    request: Request,
    email: str = Form(...),
    next_path: str = Form(""),
    _csrf: None = Depends(validate_csrf),
    db: Session = Depends(get_db),
):
    next_path = safe_next_path(next_path)
    if not allow_email_send(request):
        return HTMLResponse("Limite de envio atingido. Tente novamente daqui a uma hora.", status_code=429)

    normalized_email = email.strip().lower()
    customer = db.query(Customer).filter(Customer.email == normalized_email).first()
    mail_error = None
    if customer and not customer.email_verified_at:
        try:
            issue_verification(customer, db, next_path)
        except (EmailConfigurationError, EmailDeliveryError, httpx.HTTPError):
            mail_error = "Não foi possível enviar agora. Tente novamente mais tarde."

    notice = "Se existir uma conta pendente para esse e-mail, enviaremos um novo link de confirmação."
    return templates.TemplateResponse(
        request,
        "customer/auth.html",
        page_context(
            request, db, mode="login", error=mail_error, notice=notice,
            email=normalized_email, show_resend=True, next_path=next_path,
        ),
    )


@router.get("/verificar", response_class=HTMLResponse)
def verify_email(request: Request, token: str, next: str | None = None, db: Session = Depends(get_db)):
    next_path = safe_next_path(next)
    token_hash = sha256(token.encode()).hexdigest()
    customer = db.query(Customer).filter(Customer.verification_token_hash == token_hash).first()
    now = datetime.now(TIMEZONE).replace(tzinfo=None)
    if not customer or not customer.verification_expires_at or customer.verification_expires_at <= now:
        return templates.TemplateResponse(
            request,
            "customer/verify.html",
            page_context(
                request, db, valid=False, token="",
                email=customer.email if customer else "", next_path=next_path,
            ),
            status_code=400,
        )

    return templates.TemplateResponse(
        request,
        "customer/verify.html",
        page_context(request, db, valid=True, token=token, email=customer.email, next_path=next_path),
    )


@router.post("/verificar", response_class=HTMLResponse)
def confirm_email(
    request: Request,
    token: str = Form(...),
    next_path: str = Form(""),
    _csrf: None = Depends(validate_csrf),
    db: Session = Depends(get_db),
):
    next_path = safe_next_path(next_path)
    token_hash = sha256(token.encode()).hexdigest()
    customer = db.query(Customer).filter(Customer.verification_token_hash == token_hash).first()
    now = datetime.now(TIMEZONE).replace(tzinfo=None)
    if not customer or not customer.verification_expires_at or customer.verification_expires_at <= now:
        if customer:
            customer.verification_token_hash = None
            customer.verification_expires_at = None
            db.commit()
        return templates.TemplateResponse(
            request,
            "customer/verify.html",
            page_context(request, db, valid=False, token="", email=customer.email if customer else "", next_path=next_path),
            status_code=400,
        )

    customer.email_verified_at = now
    customer.verification_token_hash = None
    customer.verification_expires_at = None
    db.commit()
    request.session.clear()
    request.session["customer_id"] = customer.id
    csrf_value(request)
    return RedirectResponse(next_path or "/cliente/minha-conta?confirmado=1", status_code=303)


@router.get("/minha-conta", response_class=HTMLResponse)
def account(request: Request, db: Session = Depends(get_db)):
    customer = current_customer(request, db)
    if not customer:
        return RedirectResponse("/cliente/login", status_code=303)
    appointments = (
        db.query(Appointment)
        .options(joinedload(Appointment.service))
        .filter(Appointment.customer_id == customer.id)
        .order_by(Appointment.day.desc(), Appointment.start_time.desc())
        .all()
    )
    return templates.TemplateResponse(
        request,
        "customer/account.html",
        page_context(
            request, db, customer=customer, appointments=appointments,
            verified=request.query_params.get("confirmado") == "1",
        ),
    )


@router.post("/sair")
def logout(request: Request, _csrf: None = Depends(validate_csrf)):
    request.session.clear()
    return RedirectResponse("/", status_code=303)
