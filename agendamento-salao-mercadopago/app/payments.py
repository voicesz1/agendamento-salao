"""Payment helpers for manual Pix and Mercado Pago Checkout Pro."""
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

import httpx

from sqlalchemy.orm import Session

from app.settings_store import get_setting
from app.config import MERCADOPAGO_ACCESS_TOKEN, MERCADOPAGO_ENABLED, PUBLIC_BASE_URL


def price_in_cents(price: float) -> int:
    return int((Decimal(str(price)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def pix_settings(db: Session) -> dict:
    key = get_setting(db, "pix_key").strip()
    recipient = get_setting(db, "pix_recipient").strip()
    return {"pix_available": bool(key and recipient), "pix_key": key, "pix_recipient": recipient}


def create_mercadopago_preference(appointment, service_name: str) -> tuple[str, str]:
    """Create a hosted Checkout Pro session; card data stays with Mercado Pago."""
    if not MERCADOPAGO_ENABLED:
        raise RuntimeError("Pagamento com cartão ainda não está configurado.")
    appointment_id = str(appointment.id)
    return_url = f"{PUBLIC_BASE_URL}/agendamentos/{appointment_id}"
    payload = {
        "items": [{
            "id": appointment_id,
            "title": service_name[:250],
            "quantity": 1,
            "currency_id": "BRL",
            "unit_price": float(Decimal(appointment.amount_cents) / 100),
        }],
        "external_reference": appointment_id,
        "back_urls": {
            "success": return_url,
            "pending": return_url,
            "failure": return_url,
        },
        "auto_return": "approved",
        "notification_url": f"{PUBLIC_BASE_URL}/webhooks/mercadopago",
        "payment_methods": {
            "excluded_payment_types": [
                {"id": "ticket"},
                {"id": "bank_transfer"},
                {"id": "account_money"},
            ]
        },
        "metadata": {"appointment_id": appointment_id},
        "statement_descriptor": "AGENDAMENTO SALAO",
    }
    try:
        response = httpx.post(
            "https://api.mercadopago.com/checkout/preferences",
            headers={
                "Authorization": f"Bearer {MERCADOPAGO_ACCESS_TOKEN}",
                "Content-Type": "application/json",
                "X-Idempotency-Key": str(uuid4()),
            },
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()
        preference_id = str(result.get("id", ""))
        checkout_url = str(result.get("init_point", ""))
        if not preference_id or not checkout_url.startswith("https://"):
            raise RuntimeError("O Mercado Pago não retornou um link de pagamento válido.")
        return preference_id, checkout_url
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        raise RuntimeError("Não foi possível iniciar o pagamento. Tente novamente ou escolha outra forma.") from exc
