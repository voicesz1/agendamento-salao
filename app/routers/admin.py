from datetime import date, datetime
import hmac
import secrets
from threading import Lock
import time

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.config import BASE_DIR
from app.database import get_db
from app.models import Appointment, BusinessHours, ClosedDate, Service
from app.security import hash_password, verify_password
from app.settings_store import get_setting, set_setting

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
router = APIRouter(prefix="/admin")
WEEKDAYS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


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


def logged_in(request: Request) -> bool:
    return request.session.get("admin") is True


def require_admin(request: Request):
    if not logged_in(request):
        return RedirectResponse("/admin/login", status_code=303)
    return None


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, db: Session = Depends(get_db)):
    if logged_in(request):
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(
        request,
        "admin/login.html",
        {"salon_name": get_setting(db, "salon_name"), "error": None, "csrf_token": csrf_value(request)},
    )


@router.post("/login", response_class=HTMLResponse)
def login(request: Request, password: str = Form(...), _csrf: None = Depends(validate_csrf), db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with LOGIN_LOCK:
        failures = [failed_at for failed_at in LOGIN_FAILURES.get(client_ip, []) if now - failed_at < 900]
        if len(failures) >= 10:
            return HTMLResponse("Muitas tentativas. Aguarde 15 minutos antes de tentar novamente.", status_code=429)
        if len(LOGIN_FAILURES) > 1000:
            LOGIN_FAILURES.clear()
        failures.append(now)
        LOGIN_FAILURES[client_ip] = failures
    stored = get_setting(db, "admin_password_hash")
    if stored and verify_password(password, stored):
        with LOGIN_LOCK:
            LOGIN_FAILURES.pop(client_ip, None)
        request.session.clear()
        request.session["admin"] = True
        csrf_value(request)
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(
        request,
        "admin/login.html",
        {"salon_name": get_setting(db, "salon_name"), "error": "Senha incorreta.", "csrf_token": csrf_value(request)},
        status_code=401,
    )


@router.post("/sair")
def logout(request: Request, _csrf: None = Depends(validate_csrf)):
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@router.get("", response_class=HTMLResponse)
def dashboard(request: Request, status: str = "todos", db: Session = Depends(get_db)):
    if (redirect := require_admin(request)):
        return redirect
    query = db.query(Appointment).options(joinedload(Appointment.service)).order_by(
        Appointment.day.desc(), Appointment.start_time.desc()
    )
    if status in {"confirmado", "cancelado"}:
        query = query.filter(Appointment.status == status)
    appointments = query.all()
    return templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        {
            "salon_name": get_setting(db, "salon_name"),
            "appointments": appointments,
            "csrf_token": csrf_value(request),
            "status": status,
            "counts": {
                "todos": db.query(Appointment).count(),
                "confirmado": db.query(Appointment).filter(Appointment.status == "confirmado").count(),
                "cancelado": db.query(Appointment).filter(Appointment.status == "cancelado").count(),
            },
        },
    )


@router.post("/agendamentos/{appointment_id}/status")
def update_status(request: Request, appointment_id: int, status: str = Form(...), _csrf: None = Depends(validate_csrf), db: Session = Depends(get_db)):
    if (redirect := require_admin(request)):
        return redirect
    appointment = db.get(Appointment, appointment_id)
    if appointment and status in {"confirmado", "cancelado"}:
        appointment.status = status
        db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.get("/servicos", response_class=HTMLResponse)
def services_page(request: Request, db: Session = Depends(get_db)):
    if (redirect := require_admin(request)):
        return redirect
    services = db.query(Service).order_by(Service.category, Service.name).all()
    return templates.TemplateResponse(
        request,
        "admin/servicos.html",
        {"salon_name": get_setting(db, "salon_name"), "services": services, "csrf_token": csrf_value(request), "error": request.query_params.get("erro")},
    )


@router.post("/servicos")
def create_service(
    request: Request,
    name: str = Form(...),
    category: str = Form(...),
    description: str = Form(""),
    price: float = Form(...),
    duration_minutes: int = Form(...),
    _csrf: None = Depends(validate_csrf),
    db: Session = Depends(get_db),
):
    if (redirect := require_admin(request)):
        return redirect
    if not name.strip() or not category.strip() or not 0 < price <= 100000 or not 5 <= duration_minutes <= 1440:
        return RedirectResponse("/admin/servicos?erro=validacao", status_code=303)
    db.add(
        Service(
            name=name.strip(),
            category=category.strip(),
            description=description.strip(),
            price=price,
            duration_minutes=duration_minutes,
            active=True,
        )
    )
    db.commit()
    return RedirectResponse("/admin/servicos", status_code=303)


@router.post("/servicos/{service_id}")
def update_service(
    request: Request,
    service_id: int,
    name: str = Form(...),
    category: str = Form(...),
    description: str = Form(""),
    price: float = Form(...),
    duration_minutes: int = Form(...),
    active: str | None = Form(None),
    _csrf: None = Depends(validate_csrf),
    db: Session = Depends(get_db),
):
    if (redirect := require_admin(request)):
        return redirect
    if not name.strip() or not category.strip() or not 0 < price <= 100000 or not 5 <= duration_minutes <= 1440:
        return RedirectResponse("/admin/servicos?erro=validacao", status_code=303)
    service = db.get(Service, service_id)
    if service:
        service.name = name.strip()
        service.category = category.strip()
        service.description = description.strip()
        service.price = price
        service.duration_minutes = duration_minutes
        service.active = active == "on"
        db.commit()
    return RedirectResponse("/admin/servicos", status_code=303)


@router.get("/horarios", response_class=HTMLResponse)
def hours_page(request: Request, db: Session = Depends(get_db)):
    if (redirect := require_admin(request)):
        return redirect
    hours = db.query(BusinessHours).order_by(BusinessHours.weekday).all()
    closed = db.query(ClosedDate).order_by(ClosedDate.day).all()
    return templates.TemplateResponse(
        request,
        "admin/horarios.html",
        {
            "salon_name": get_setting(db, "salon_name"),
            "hours": hours,
            "weekdays": WEEKDAYS,
            "closed": closed,
            "interval": get_setting(db, "slot_interval_minutes", "30"),
            "csrf_token": csrf_value(request),
            "error": request.query_params.get("erro"),
        },
    )


@router.post("/horarios")
async def save_hours(request: Request, db: Session = Depends(get_db)):
    if (redirect := require_admin(request)):
        return redirect
    form = await request.form()
    expected = request.session.get("csrf_token", "")
    if not expected or not hmac.compare_digest(expected, str(form.get("csrf", ""))):
        raise HTTPException(status_code=403, detail="Requisição inválida.")
    interval = str(form.get("slot_interval_minutes") or "30")
    if interval not in {"15", "30", "60"}:
        return RedirectResponse("/admin/horarios?erro=validacao", status_code=303)
    parsed_hours = []
    try:
        for weekday in range(7):
            start = datetime.strptime(str(form.get(f"start_{weekday}") or "09:00"), "%H:%M").time()
            end = datetime.strptime(str(form.get(f"end_{weekday}") or "19:00"), "%H:%M").time()
            break_start_text = str(form.get(f"break_start_{weekday}") or "")
            break_end_text = str(form.get(f"break_end_{weekday}") or "")
            break_start = datetime.strptime(break_start_text, "%H:%M").time() if break_start_text else None
            break_end = datetime.strptime(break_end_text, "%H:%M").time() if break_end_text else None
            if end <= start or (break_start is None) != (break_end is None):
                raise ValueError
            if break_start and (break_end <= break_start or break_start < start or break_end > end):
                raise ValueError
            parsed_hours.append((start, end, break_start, break_end))
    except ValueError:
        return RedirectResponse("/admin/horarios?erro=validacao", status_code=303)
    set_setting(db, "slot_interval_minutes", interval)
    for weekday in range(7):
        row = db.query(BusinessHours).filter(BusinessHours.weekday == weekday).first()
        if not row:
            continue
        row.is_open = form.get(f"open_{weekday}") == "on"
        row.open_time, row.close_time, row.break_start, row.break_end = parsed_hours[weekday]
    db.commit()
    return RedirectResponse("/admin/horarios", status_code=303)


@router.post("/folgas")
def add_closed(request: Request, day: date = Form(...), reason: str = Form("Folga"), _csrf: None = Depends(validate_csrf), db: Session = Depends(get_db)):
    if (redirect := require_admin(request)):
        return redirect
    chosen = day
    if not db.query(ClosedDate).filter(ClosedDate.day == chosen).first():
        db.add(ClosedDate(day=chosen, reason=reason.strip() or "Folga"))
        db.commit()
    return RedirectResponse("/admin/horarios", status_code=303)


@router.post("/folgas/{closed_id}/excluir")
def delete_closed(request: Request, closed_id: int, _csrf: None = Depends(validate_csrf), db: Session = Depends(get_db)):
    if (redirect := require_admin(request)):
        return redirect
    row = db.get(ClosedDate, closed_id)
    if row:
        db.delete(row)
        db.commit()
    return RedirectResponse("/admin/horarios", status_code=303)


@router.get("/config", response_class=HTMLResponse)
def config_page(request: Request, db: Session = Depends(get_db)):
    if (redirect := require_admin(request)):
        return redirect
    return templates.TemplateResponse(
        request,
        "admin/config.html",
        {
            "salon_name": get_setting(db, "salon_name"),
            "salon_tagline": get_setting(db, "salon_tagline"),
            "owner_whatsapp": get_setting(db, "owner_whatsapp"),
            "saved": False,
            "csrf_token": csrf_value(request),
            "error": request.query_params.get("erro"),
        },
    )


@router.post("/config", response_class=HTMLResponse)
def save_config(
    request: Request,
    salon_name: str = Form(...),
    salon_tagline: str = Form(""),
    owner_whatsapp: str = Form(""),
    new_password: str = Form(""),
    _csrf: None = Depends(validate_csrf),
    db: Session = Depends(get_db),
):
    if (redirect := require_admin(request)):
        return redirect
    if len(salon_name.strip()) < 2 or (new_password.strip() and len(new_password.strip()) < 12):
        return RedirectResponse("/admin/config?erro=validacao", status_code=303)
    set_setting(db, "salon_name", salon_name.strip())
    set_setting(db, "salon_tagline", salon_tagline.strip())
    set_setting(db, "owner_whatsapp", "".join(ch for ch in owner_whatsapp if ch in "0123456789"))
    if new_password.strip():
        set_setting(db, "admin_password_hash", hash_password(new_password.strip()))
    db.commit()
    return templates.TemplateResponse(
        request,
        "admin/config.html",
        {
            "salon_name": salon_name.strip(),
            "salon_tagline": salon_tagline.strip(),
            "owner_whatsapp": "".join(ch for ch in owner_whatsapp if ch in "0123456789"),
            "saved": True,
            "csrf_token": csrf_value(request),
        },
    )
