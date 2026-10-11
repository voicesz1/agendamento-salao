from urllib.parse import quote

import httpx
from sqlalchemy.orm import Session

from app.models import Appointment
from app.settings_store import get_setting


def format_message(db: Session, appointment: Appointment) -> str:
    salon = get_setting(db, "salon_name", "Salão")
    service = appointment.service
    return (
        f"✨ Novo agendamento — {salon}\n\n"
        f"Serviço: {service.name}\n"
        f"Valor: R$ {service.price:.2f}\n"
        f"Cliente: {appointment.client_name}\n"
        f"WhatsApp: {appointment.client_phone}\n"
        f"Data: {appointment.day.strftime('%d/%m/%Y')} às {appointment.start_time.strftime('%H:%M')}\n"
        f"Duração: {service.duration_minutes} min"
        + (f"\nObs.: {appointment.notes}" if appointment.notes else "")
    )


def wa_me_link(phone: str, text: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    return f"https://wa.me/{digits}?text={quote(text)}"


def notify_owner(db: Session, appointment: Appointment) -> tuple[bool, str]:
    phone = get_setting(db, "owner_whatsapp")
    text = format_message(db, appointment)
    if not phone:
        return False, "WhatsApp do dono não configurado"

    api_key = get_setting(db, "callmebot_apikey")
    webhook = get_setting(db, "webhook_url")

    try:
        if webhook:
            response = httpx.post(
                webhook,
                json={"phone": phone, "text": text, "appointment_id": appointment.id},
                timeout=12,
            )
            response.raise_for_status()
            return True, "Enviado pelo webhook"

        if api_key:
            response = httpx.get(
                "https://api.callmebot.com/whatsapp.php",
                params={"phone": phone, "text": text, "apikey": api_key},
                timeout=12,
            )
            response.raise_for_status()
            return True, "Enviado pelo CallMeBot"

        return False, "Configure a chave CallMeBot ou um webhook para envio automático"
    except httpx.HTTPError:
        return False, "Não foi possível enviar a notificação automática. O agendamento continua confirmado."
    except Exception:
        return False, "Ocorreu um erro ao enviar a notificação automática. O agendamento continua confirmado."
