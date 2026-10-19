from datetime import date, datetime
import hmac
import time
from threading import Lock

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.config import BASE_DIR, TIMEZONE
from app.csrf import csrf_value, validate_csrf
from app.database import get_db
from app.models import Appointment, BusinessHours, ClosedDate, Service
from app.payments import pix_settings
from app.security import hash_password, verify_password
from app.service_images import read_service_image, set_service_image
from app.settings_store import get_setting, set_setting

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
router = APIRouter(prefix="/admin")
WEEKDAYS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
ADMIN_LOGIN_FAILURES: dict[str, list[float]] = {}
ADMIN_LOGIN_LOCK = Lock()


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
        {
            "salon_name": get_setting(db, "salon_name", "Salão"),
            "csrf_token": csrf_value(request),
            "error": None,
        },
    )


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    password: str = Form(...),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    try:
        validate_csrf(request, csrf)
    except HTTPException as exc:
        if exc.status_code != 403:
            raise
        return templates.TemplateResponse(
            request,
            "admin/login.html",
            {
                "salon_name": get_setting(db, "salon_name", "Salão"),
                "csrf_token": csrf_value(request),
                "error": "Sua sessão de acesso expirou ou não pôde ser validada. Digite a senha e tente novamente. Se o erro continuar, permita cookies e abra o site por HTTPS.",
            },
            status_code=403,
        )
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with ADMIN_LOGIN_LOCK:
        failures = [stamp for stamp in ADMIN_LOGIN_FAILURES.get(client_ip, []) if now - stamp < 900]
        if len(failures) >= 10:
            ADMIN_LOGIN_FAILURES[client_ip] = failures
            message = "Muitas tentativas. Aguarde 15 minutos antes de tentar novamente."
            status_code = 429
        else:
            message = None
            status_code = 401

    if message:
        return templates.TemplateResponse(
            request,
            "admin/login.html",
            {"salon_name": get_setting(db, "salon_name", "Salão"), "csrf_token": csrf_value(request), "error": message},
            status_code=status_code,
        )

    password_hash = get_setting(db, "admin_password_hash")
    if password_hash and verify_password(password, password_hash):
        with ADMIN_LOGIN_LOCK:
            ADMIN_LOGIN_FAILURES.pop(client_ip, None)
        request.session.clear()
        request.session["admin"] = True
        csrf_value(request)
        return RedirectResponse("/admin", status_code=303)

    with ADMIN_LOGIN_LOCK:
        ADMIN_LOGIN_FAILURES[client_ip] = failures + [now]
    return templates.TemplateResponse(
        request,
        "admin/login.html",
        {
            "salon_name": get_setting(db, "salon_name", "Salão"),
            "csrf_token": csrf_value(request),
            "error": "Senha incorreta.",
        },
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


@router.post("/agendamentos/{appointment_id}/pagamento")
def confirm_payment(
    request: Request, appointment_id: int, received: str = Form(""),
    _csrf: None = Depends(validate_csrf), db: Session = Depends(get_db),
):
    if (redirect := require_admin(request)):
        return redirect
    appointment = db.get(Appointment, appointment_id)
    if not appointment or appointment.status != "confirmado" or appointment.payment_method == "cartao" or received != "conferido":
        raise HTTPException(status_code=400, detail="Confira o recebimento de um agendamento ativo.")
    if appointment.payment_status != "pago":
        appointment.payment_status = "pago"
        appointment.payment_confirmed_at = datetime.now(TIMEZONE).replace(tzinfo=None)
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
    image: UploadFile | None = File(None),
    _csrf: None = Depends(validate_csrf),
    db: Session = Depends(get_db),
):
    if (redirect := require_admin(request)):
        return redirect
    if not name.strip() or not category.strip() or not 0 < price <= 100000 or not 5 <= duration_minutes <= 1440:
        return RedirectResponse("/admin/servicos?erro=validacao", status_code=303)
    try:
        image_data = read_service_image(image)
    except ValueError:
        return RedirectResponse("/admin/servicos?erro=imagem", status_code=303)
    service = Service(
        name=name.strip(),
        category=category.strip(),
        description=description.strip(),
        price=price,
        duration_minutes=duration_minutes,
        active=True,
    )
    if image_data is not None:
        set_service_image(service, image_data)
    db.add(service)
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
    image: UploadFile | None = File(None),
    remove_image: str | None = Form(None),
    _csrf: None = Depends(validate_csrf),
    db: Session = Depends(get_db),
):
    if (redirect := require_admin(request)):
        return redirect
    if not name.strip() or not category.strip() or not 0 < price <= 100000 or not 5 <= duration_minutes <= 1440:
        return RedirectResponse("/admin/servicos?erro=validacao", status_code=303)
    service = db.get(Service, service_id)
    if service:
        try:
            image_data = read_service_image(image)
        except ValueError:
            return RedirectResponse("/admin/servicos?erro=imagem", status_code=303)
        service.name = name.strip()
        service.category = category.strip()
        service.description = description.strip()
        service.price = price
        service.duration_minutes = duration_minutes
        service.active = active == "on"
        if image_data is not None:
            set_service_image(service, image_data)
        elif remove_image == "on":
            set_service_image(service, None)
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
            **pix_settings(db),
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
    pix_key: str = Form(""),
    pix_recipient: str = Form(""),
    _csrf: None = Depends(validate_csrf),
    db: Session = Depends(get_db),
):
    if (redirect := require_admin(request)):
        return redirect
    if len(salon_name.strip()) < 2 or (new_password.strip() and len(new_password.strip()) < 12):
        return RedirectResponse("/admin/config?erro=validacao", status_code=303)
    if (bool(pix_key.strip()) != bool(pix_recipient.strip())
            or len(pix_key.strip()) > 254 or len(pix_recipient.strip()) > 120
            or any(ord(char) < 32 for char in pix_key.strip())):
        return RedirectResponse("/admin/config?erro=pix", status_code=303)
    set_setting(db, "salon_name", salon_name.strip())
    set_setting(db, "salon_tagline", salon_tagline.strip())
    set_setting(db, "owner_whatsapp", "".join(ch for ch in owner_whatsapp if ch in "0123456789"))
    set_setting(db, "pix_key", pix_key.strip())
    set_setting(db, "pix_recipient", pix_recipient.strip())
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
            **pix_settings(db),
            "csrf_token": csrf_value(request),
        },
    )
