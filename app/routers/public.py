from collections import defaultdict
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import BASE_DIR, TIMEZONE
from app.database import get_db
from app.models import Appointment, Service
from app.settings_store import get_setting
from app.slots import available_slots, now_local, slot_is_free
from app.whatsapp import format_message, notify_owner, wa_me_link

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
router = APIRouter()


def salon_context(db: Session) -> dict:
    return {
        "salon_name": get_setting(db, "salon_name", "Salão"),
        "salon_tagline": get_setting(db, "salon_tagline", ""),
    }


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    services = db.query(Service).filter(Service.active.is_(True)).order_by(Service.category, Service.name).all()
    grouped: dict[str, list[Service]] = defaultdict(list)
    for service in services:
        grouped[service.category].append(service)
    return templates.TemplateResponse(
        request,
        "index.html",
        {**salon_context(db), "grouped": grouped},
    )


@router.get("/agendar", response_class=HTMLResponse)
def agendar(request: Request, servico: int | None = None, db: Session = Depends(get_db)):
    services = db.query(Service).filter(Service.active.is_(True)).order_by(Service.name).all()
    selected = db.get(Service, servico) if servico else None
    today = now_local().date()
    dates = [today + timedelta(days=i) for i in range(21)]
    return templates.TemplateResponse(
        request,
        "agendar.html",
        {
            **salon_context(db),
            "services": services,
            "selected": selected,
            "dates": dates,
            "error": None,
        },
    )


@router.post("/agendar", response_class=HTMLResponse)
def criar_agendamento(
    request: Request,
    service_id: int = Form(...),
    day: str = Form(...),
    start_time: str = Form(...),
    client_name: str = Form(...),
    client_phone: str = Form(...),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    if db.bind and db.bind.dialect.name == "sqlite":
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    elif db.bind and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:day))"), {"day": day})
    service = db.get(Service, service_id)
    services = db.query(Service).filter(Service.active.is_(True)).order_by(Service.name).all()
    today = now_local().date()
    dates = [today + timedelta(days=i) for i in range(21)]

    def fail(message: str):
        return templates.TemplateResponse(
            request,
            "agendar.html",
            {
                **salon_context(db),
                "services": services,
                "selected": service,
                "dates": dates,
                "error": message,
            },
            status_code=400,
        )

    if not service or not service.active:
        return fail("Serviço indisponível.")

    if not 2 <= len(client_name.strip()) <= 120:
        return fail("Informe seu nome (de 2 a 120 caracteres).")
    phone_digits = "".join(ch for ch in client_phone if ch in "0123456789")
    if not 10 <= len(phone_digits) <= 15:
        return fail("Informe um WhatsApp válido com DDD e número.")
    if len(notes.strip()) > 1000:
        return fail("A observação deve ter no máximo 1.000 caracteres.")

    try:
        chosen_day = datetime.strptime(day, "%Y-%m-%d").date()
        start = datetime.strptime(start_time, "%H:%M").time()
    except ValueError:
        return fail("Data ou horário inválido.")

    today = now_local().date()
    if chosen_day < today or chosen_day > today + timedelta(days=20):
        return fail("Escolha uma data nos próximos 21 dias.")
    if not slot_is_free(db, service, chosen_day, start.strftime("%H:%M")):
        return fail("Esse horário não está mais disponível. Escolha outro.")

    end_dt = datetime.combine(chosen_day, start) + timedelta(minutes=service.duration_minutes)
    appointment = Appointment(
        service_id=service.id,
        client_name=client_name.strip(),
        client_phone=phone_digits,
        notes=notes.strip(),
        day=chosen_day,
        start_time=start,
        end_time=end_dt.time(),
        status="confirmado",
        created_at=datetime.now(TIMEZONE).replace(tzinfo=None),
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)

    sent, detail = notify_owner(db, appointment)
    appointment.whatsapp_sent = sent
    appointment.whatsapp_error = "" if sent else detail
    db.commit()

    owner_phone = get_setting(db, "owner_whatsapp")
    message = format_message(db, appointment)
    return templates.TemplateResponse(
        request,
        "confirmado.html",
        {
            **salon_context(db),
            "appointment": appointment,
            "whatsapp_sent": sent,
            "whatsapp_detail": detail,
            "wa_link": wa_me_link(owner_phone, message) if owner_phone else "",
        },
    )


@router.get("/api/horarios")
def api_horarios(servico: int, dia: date, db: Session = Depends(get_db)):
    service = db.get(Service, servico)
    if not service or not service.active:
        return {"slots": []}
    today = now_local().date()
    if dia < today or dia > today + timedelta(days=20):
        return {"slots": []}
    return {"slots": available_slots(db, service, dia)}
