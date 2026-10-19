from collections import defaultdict
from datetime import date, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import BASE_DIR, MERCADOPAGO_ENABLED, MERCADOPAGO_PUBLIC_KEY, TIMEZONE
from app.csrf import csrf_value, validate_csrf, validate_csrf_header
from app.database import get_db
from app.models import Appointment, Service
from app.payments import (
    MercadoPagoRequestError,
    MercadoPagoUnavailableError,
    create_mercadopago_card_payment,
    pix_settings,
    price_in_cents,
)
from app.settings_store import get_setting
from app.slots import available_slots, now_local, slot_is_free
from app.whatsapp import format_message, notify_owner, wa_me_link

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
router = APIRouter()


@router.get("/login", include_in_schema=False)
def login_redirect():
    return RedirectResponse("/admin/login", status_code=303)


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
            "client_name": "",
            "client_phone": "",
            "csrf_token": csrf_value(request),
            "payment_method": "no_local",
            "mercadopago_enabled": MERCADOPAGO_ENABLED,
            **pix_settings(db),
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
    payment_method: str = Form("no_local"),
    _csrf: None = Depends(validate_csrf),
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
                "client_name": client_name,
                "client_phone": client_phone,
                "notes": notes,
                "selected_day": day,
                "csrf_token": csrf_value(request),
                "payment_method": payment_method,
                "mercadopago_enabled": MERCADOPAGO_ENABLED,
                **pix_settings(db),
            },
            status_code=400,
        )

    if not service or not service.active:
        return fail("Serviço indisponível.")

    pix = pix_settings(db)
    if payment_method not in {"pix", "no_local", "cartao"}:
        return fail("Escolha uma forma de pagamento disponível.")
    if payment_method == "cartao" and not MERCADOPAGO_ENABLED:
        return fail("Pagamento com cartão ainda não está disponível. Escolha outra forma.")
    if payment_method == "pix" and not pix["pix_available"]:
        return fail("O Pix ainda não está disponível. Escolha pagar no salão.")

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
        customer_id=None,
        service_id=service.id,
        client_name=client_name.strip(),
        client_phone=phone_digits,
        notes=notes.strip(),
        day=chosen_day,
        start_time=start,
        end_time=end_dt.time(),
        status="confirmado",
        created_at=datetime.now(TIMEZONE).replace(tzinfo=None),
        amount_cents=price_in_cents(service.price),
        payment_method=payment_method,
        payment_status="pendente",
        pix_key=pix["pix_key"] if payment_method == "pix" else "",
        pix_recipient=pix["pix_recipient"] if payment_method == "pix" else "",
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)

    if payment_method == "cartao":
        sent, detail = notify_owner(db, appointment)
        appointment.whatsapp_sent = sent
        appointment.whatsapp_error = "" if sent else detail
        db.commit()
        recent = request.session.get("recent_appointments", [])
        request.session["recent_appointments"] = (recent + [appointment.id])[-10:]
        return RedirectResponse(f"/pagamento/cartao/{appointment.id}", status_code=303)

    sent, detail = notify_owner(db, appointment)
    appointment.whatsapp_sent = sent
    appointment.whatsapp_error = "" if sent else detail
    db.commit()

    recent = request.session.get("recent_appointments", [])
    request.session["recent_appointments"] = (recent + [appointment.id])[-10:]
    return RedirectResponse(f"/agendamentos/{appointment.id}", status_code=303)


@router.get("/pagamento/cartao/{appointment_id}", response_class=HTMLResponse)
def card_checkout(request: Request, appointment_id: int, db: Session = Depends(get_db)):
    appointment = db.get(Appointment, appointment_id)
    if not appointment or appointment_id not in request.session.get("recent_appointments", []):
        raise HTTPException(status_code=404, detail="Agendamento não encontrado nesta sessão.")
    if appointment.payment_method != "cartao":
        raise HTTPException(status_code=404, detail="Pagamento com cartão não encontrado.")
    if appointment.status == "cancelado":
        return RedirectResponse(f"/agendamentos/{appointment.id}", status_code=303)
    if appointment.payment_status == "pago":
        return RedirectResponse(f"/agendamentos/{appointment.id}", status_code=303)
    if appointment.payment_status not in {"recusado", "cancelado"} and (
        appointment.mercadopago_payment_id or appointment.payment_provider_status == "processing"
    ):
        return RedirectResponse(f"/agendamentos/{appointment.id}", status_code=303)
    if not MERCADOPAGO_ENABLED or appointment.amount_cents is None:
        raise HTTPException(status_code=503, detail="Pagamento com cartão ainda não está configurado.")

    return templates.TemplateResponse(
        request,
        "card_checkout.html",
        {
            **salon_context(db),
            "appointment": appointment,
            "csrf_token": csrf_value(request),
            "mercadopago_public_key": MERCADOPAGO_PUBLIC_KEY,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post("/api/pagamentos/cartao/{appointment_id}")
def submit_card_payment(
    request: Request,
    appointment_id: int,
    form_data: dict = Body(...),
    _csrf: None = Depends(validate_csrf_header),
    db: Session = Depends(get_db),
):
    appointment = db.get(Appointment, appointment_id)
    if not appointment or appointment_id not in request.session.get("recent_appointments", []):
        raise HTTPException(status_code=404, detail="Agendamento não encontrado nesta sessão.")
    if appointment.payment_method != "cartao" or appointment.status == "cancelado":
        raise HTTPException(status_code=404, detail="Pagamento não disponível para esta reserva.")
    confirmation_url = f"/agendamentos/{appointment.id}"
    if appointment.payment_status == "pago":
        return {"status": "approved", "redirect": confirmation_url}
    if appointment.payment_status not in {"pendente", "recusado", "cancelado"}:
        raise HTTPException(status_code=409, detail="Este pagamento não pode ser repetido.")
    if appointment.payment_status == "pendente" and (
        appointment.mercadopago_payment_id or appointment.payment_provider_status == "processing"
    ):
        return {"status": "processing", "redirect": confirmation_url}
    if not MERCADOPAGO_ENABLED or appointment.amount_cents is None:
        raise HTTPException(status_code=503, detail="Pagamento com cartão ainda não está configurado.")

    attempts = request.session.get("mp_card_attempts", {})
    if not isinstance(attempts, dict):
        attempts = {}
    attempt_key = str(appointment.id)
    idempotency_key = attempts.get(attempt_key)
    if not idempotency_key:
        idempotency_key = str(uuid4())
        attempts[attempt_key] = idempotency_key
        request.session["mp_card_attempts"] = attempts

    previous_status = appointment.payment_status
    appointment.payment_status = "pendente"
    appointment.payment_provider_status = "processing"
    db.commit()

    try:
        payment = create_mercadopago_card_payment(
            appointment, appointment.service.name, form_data, idempotency_key
        )
    except ValueError as exc:
        appointment.payment_status = previous_status
        appointment.payment_provider_status = ""
        db.commit()
        attempts.pop(attempt_key, None)
        request.session["mp_card_attempts"] = attempts
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except MercadoPagoUnavailableError:
        appointment.payment_status = previous_status
        appointment.payment_provider_status = ""
        db.commit()
        return JSONResponse(
            status_code=503,
            content={"detail": "Não foi possível verificar o cartão agora. Tente novamente em alguns instantes."},
        )
    except MercadoPagoRequestError as exc:
        if exc.status_code < 500:
            appointment.payment_status = previous_status
            appointment.payment_provider_status = ""
            db.commit()
            attempts.pop(attempt_key, None)
            request.session["mp_card_attempts"] = attempts
            return JSONResponse(
                status_code=502,
                content={"detail": "Não foi possível iniciar o pagamento. Confira os dados e tente novamente."},
            )
        # The remote API may have created a payment before the network failed.
        # Keep this attempt locked until its signed webhook updates the status.
        db.commit()
        return {"status": "processing", "redirect": confirmation_url}
    except RuntimeError:
        # A timeout has an unknown outcome. Do not risk creating a duplicate
        # charge; the webhook or the Mercado Pago dashboard will settle it.
        db.commit()
        return {"status": "processing", "redirect": confirmation_url}

    payment_id = str(payment.get("id", ""))[:100]
    provider_status = str(payment.get("status", "unknown"))[:40]
    appointment.mercadopago_payment_id = payment_id
    appointment.payment_provider_status = provider_status
    if provider_status == "approved":
        appointment.payment_status = "pago"
        appointment.payment_confirmed_at = datetime.now(TIMEZONE).replace(tzinfo=None)
    elif provider_status in {"rejected", "cancelled"}:
        appointment.payment_status = "recusado" if provider_status == "rejected" else "cancelado"
        appointment.payment_confirmed_at = None
        # A new card and token require a new Mercado Pago idempotency key.
        attempts.pop(attempt_key, None)
        request.session["mp_card_attempts"] = attempts
    else:
        appointment.payment_status = "pendente"
        appointment.payment_confirmed_at = None
    db.commit()
    return {"status": provider_status, "redirect": confirmation_url}


@router.get("/agendamentos/{appointment_id}", response_class=HTMLResponse)
def confirmation(request: Request, appointment_id: int, db: Session = Depends(get_db)):
    appointment = db.get(Appointment, appointment_id)
    if not appointment or appointment_id not in request.session.get("recent_appointments", []):
        raise HTTPException(status_code=404, detail="Agendamento não encontrado nesta sessão.")

    owner_phone = get_setting(db, "owner_whatsapp")
    message = format_message(db, appointment)
    return templates.TemplateResponse(
        request,
        "confirmado.html",
        {
            **salon_context(db),
            "appointment": appointment,
            "whatsapp_sent": appointment.whatsapp_sent,
            "whatsapp_detail": appointment.whatsapp_error,
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
