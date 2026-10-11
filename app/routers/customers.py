import hmac
import re
import secrets
import time
from datetime import datetime
from threading import Lock

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.config import BASE_DIR, TIMEZONE
from app.database import get_db
from app.models import Appointment, Customer
from app.security import hash_password, verify_password
from app.settings_store import get_setting

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
router = APIRouter(prefix="/cliente")
LOGIN_FAILURES: dict[str, list[float]] = {}
LOGIN_LOCK = Lock()


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


@router.get("/cadastro", response_class=HTMLResponse)
def register_form(request: Request, db: Session = Depends(get_db)):
    if current_customer(request, db):
        return RedirectResponse("/cliente/minha-conta", status_code=303)
    return templates.TemplateResponse(
        request,
        "customer/auth.html",
        page_context(request, db, mode="register", error=None),
    )


@router.post("/cadastro", response_class=HTMLResponse)
def register(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    password: str = Form(...),
    _csrf: None = Depends(validate_csrf),
    db: Session = Depends(get_db),
):
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

    if error:
        return templates.TemplateResponse(
            request,
            "customer/auth.html",
            page_context(request, db, mode="register", error=error, name=name.strip(), email=normalized_email, phone=phone),
            status_code=400,
        )

    customer = Customer(
        name=name.strip(),
        email=normalized_email,
        phone=phone_digits,
        password_hash=hash_password(password),
        created_at=datetime.now(TIMEZONE).replace(tzinfo=None),
    )
    db.add(customer)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(
            request,
            "customer/auth.html",
            page_context(request, db, mode="register", error="Já existe uma conta com este e-mail.", name=name.strip(), email=normalized_email, phone=phone),
            status_code=400,
        )

    request.session.clear()
    request.session["customer_id"] = customer.id
    csrf_value(request)
    return RedirectResponse("/cliente/minha-conta", status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, db: Session = Depends(get_db)):
    if current_customer(request, db):
        return RedirectResponse("/cliente/minha-conta", status_code=303)
    if request.session.get("admin") is True:
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(
        request,
        "customer/auth.html",
        page_context(request, db, mode="login", error=None),
    )


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    username_or_email: str = Form(...),
    password: str = Form(...),
    _csrf: None = Depends(validate_csrf),
    db: Session = Depends(get_db),
):
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
    admin_password_hash = get_setting(db, "admin_password_hash")
    is_owner = identifier == "dona" and admin_password_hash and verify_password(password, admin_password_hash)
    if is_owner or (customer and verify_password(password, customer.password_hash)):
        with LOGIN_LOCK:
            LOGIN_FAILURES.pop(client_ip, None)
        request.session.clear()
        if is_owner:
            request.session["admin"] = True
            return RedirectResponse("/admin", status_code=303)
        request.session["customer_id"] = customer.id
        csrf_value(request)
        return RedirectResponse("/cliente/minha-conta", status_code=303)

    return templates.TemplateResponse(
        request,
        "customer/auth.html",
        page_context(request, db, mode="login", error="Usuário/e-mail ou senha incorretos.", username_or_email=username_or_email.strip()),
        status_code=401,
    )


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
        page_context(request, db, customer=customer, appointments=appointments),
    )


@router.post("/sair")
def logout(request: Request, _csrf: None = Depends(validate_csrf)):
    request.session.clear()
    return RedirectResponse("/", status_code=303)
