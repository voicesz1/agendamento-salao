from urllib.parse import quote

from sqlalchemy.orm import Session

from app.models import Appointment
from app.settings_store import get_setting


def format_message(db: Session, appointment: Appointment) -> str:
    salon = get_setting(db, "salon_name", "Salão")
    service = appointment.service
    amount = f"R$ {appointment.amount_cents / 100:.2f}" if appointment.amount_cents is not None else "consulte o salão"
    return (
        f"✨ Novo agendamento — {salon}\n\n"
        f"Serviço: {service.name}\n"
        f"Valor reservado: {amount}\n"
        f"Pagamento: {'Pix' if appointment.payment_method == 'pix' else 'no salão'} — {appointment.payment_status}\n"
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
    # Não há envio automático: a confirmação oferece um link manual para o WhatsApp.
    return False, "O aviso pode ser enviado manualmente pelo WhatsApp."
