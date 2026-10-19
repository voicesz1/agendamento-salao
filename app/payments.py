"""Payment helpers for manual Pix and Mercado Pago Checkout Pro."""
from decimal import Decimal, ROUND_HALF_UP
import logging
from uuid import uuid4

import httpx
from sqlalchemy.orm import Session

from app.config import MERCADOPAGO_ACCESS_TOKEN, MERCADOPAGO_ENABLED, PUBLIC_BASE_URL
from app.settings_store import get_setting

logger = logging.getLogger(__name__)


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
            # Credit and debit cards stay enabled. Mercado Pago does not allow
            # excluding account money, so remove only offline and Pix types.
            "excluded_payment_types": [
                {"id": "ticket"},
                {"id": "bank_transfer"},
            ],
            "installments": 12,
        },
        "metadata": {"appointment_id": appointment_id},
        "statement_descriptor": "CRYS NAILS",
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
        url_field = "sandbox_init_point" if MERCADOPAGO_ACCESS_TOKEN.startswith("TEST-") else "init_point"
        checkout_url = str(result.get(url_field, ""))
        if not preference_id or not checkout_url.startswith("https://"):
            raise RuntimeError("O Mercado Pago não retornou um link de pagamento válido.")
        return preference_id, checkout_url
    except httpx.HTTPStatusError as exc:
        try:
            details = exc.response.json()
        except ValueError:
            details = exc.response.text[:1000]
        logger.error(
            "Mercado Pago rejected checkout preference (HTTP %s): %s",
            exc.response.status_code,
            details,
        )
        raise RuntimeError("Não foi possível iniciar o pagamento. Tente novamente ou escolha outra forma.") from exc
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        logger.exception("Mercado Pago checkout preference request failed")
        raise RuntimeError("Não foi possível iniciar o pagamento. Tente novamente ou escolha outra forma.") from exc


class MercadoPagoRequestError(RuntimeError):
    def __init__(self, status_code: int, provider_error: str, cause_codes: tuple[str, ...]):
        super().__init__("Não foi possível iniciar o pagamento. Confira os dados e tente novamente.")
        self.status_code = status_code
        self.provider_error = provider_error
        self.cause_codes = cause_codes


def _payment_error_diagnostics(response: httpx.Response) -> tuple[str, tuple[str, ...]]:
    """Extract provider error identifiers only; never log its request or card data."""
    try:
        body = response.json()
    except ValueError:
        return "unknown", ()
    if not isinstance(body, dict):
        return "unknown", ()

    provider_error = str(body.get("error", "unknown"))
    if not provider_error.isascii() or not provider_error.replace("_", "").replace("-", "").isalnum():
        provider_error = "unknown"
    provider_error = provider_error[:80] or "unknown"

    causes = body.get("cause")
    cause_codes = tuple(
        str(cause["code"])[:40]
        for cause in causes
        if isinstance(cause, dict)
        and cause.get("code") is not None
        and str(cause["code"]).isascii()
        and str(cause["code"]).replace("_", "").replace("-", "").isalnum()
    ) if isinstance(causes, list) else ()
    return provider_error, cause_codes


class MercadoPagoUnavailableError(RuntimeError):
    """The card-type precheck failed before any payment request was sent."""


def create_mercadopago_card_payment(appointment, service_name: str, form_data: dict, idempotency_key: str) -> dict:
    """Create a credit or debit card payment from a Mercado Pago Brick token.

    The browser sends a token and payer metadata only; raw card details never
    reach this server or the salon database.
    """
    if not MERCADOPAGO_ENABLED:
        raise RuntimeError("Pagamento com cartão ainda não está configurado.")

    payer_data = form_data.get("payer")
    if not isinstance(payer_data, dict):
        raise ValueError("Dados do titular do cartão incompletos.")
    identification = payer_data.get("identification")
    if not isinstance(identification, dict):
        raise ValueError("Documento do titular do cartão incompleto.")

    token = str(form_data.get("token", "")).strip()
    payment_method_id = str(form_data.get("payment_method_id", "")).strip()
    installments = form_data.get("installments")
    email = str(payer_data.get("email", "")).strip()
    document_type = str(identification.get("type", "")).strip().upper()
    document_number = "".join(ch for ch in str(identification.get("number", "")) if ch.isdigit())
    issuer_raw = str(form_data.get("issuer_id", "")).strip()

    if not token or len(token) > 512:
        raise ValueError("Não foi possível validar os dados do cartão.")
    if not payment_method_id or len(payment_method_id) > 40:
        raise ValueError("Bandeira do cartão inválida.")
    # For Bricks, installments might be 1 for debit or more for credit.
    # The validation should be flexible.
    if isinstance(installments, bool) or not isinstance(installments, int) or not 1 <= installments <= 12:
        raise ValueError("Selecione uma opção de parcelamento válida.")
    if "@" not in email or len(email) > 254:
        raise ValueError("Informe um e-mail válido do titular.")
    if document_type not in {"CPF", "CNPJ"} or len(document_number) not in {11, 14}:
        raise ValueError("Informe um CPF ou CNPJ válido.")
    if issuer_raw and not issuer_raw.isdigit():
        raise ValueError("Emissor do cartão inválido.")

    try:
        methods_response = httpx.get(
            "https://api.mercadopago.com/v1/payment_methods",
            headers={"Authorization": f"Bearer {MERCADOPAGO_ACCESS_TOKEN}"},
            timeout=10,
        )
        methods_response.raise_for_status()
        methods = methods_response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise MercadoPagoUnavailableError("Não foi possível verificar a bandeira do cartão.") from exc
    
    method = (
        next(
            (item for item in methods if isinstance(item, dict) and item.get("id") == payment_method_id),
            None,
        )
        if isinstance(methods, list)
        else None
    )
    if not method or method.get("status") != "active":
        raise ValueError("Escolha um cartão ativo para continuar.")

    payer = {
        "email": email,
        "identification": {"type": document_type, "number": document_number},
    }
    first_name = str(payer_data.get("first_name", "")).strip()
    if first_name:
        payer["first_name"] = first_name[:120]

    payload = {
        "transaction_amount": float(Decimal(appointment.amount_cents) / 100),
        "token": token,
        "description": service_name[:250],
        "installments": installments,
        "payment_method_id": payment_method_id,
        "external_reference": str(appointment.id),
        "notification_url": f"{PUBLIC_BASE_URL}/webhooks/mercadopago",
        "payer": payer,
    }
    if issuer_raw:
        payload["issuer_id"] = int(issuer_raw)

    try:
        response = httpx.post(
            "https://api.mercadopago.com/v1/payments",
            headers={
                "Authorization": f"Bearer {MERCADOPAGO_ACCESS_TOKEN}",
                "Content-Type": "application/json",
                "X-Idempotency-Key": idempotency_key,
            },
            json=payload,
            timeout=25,
        )
    except httpx.HTTPError as exc:
        raise RuntimeError("O Mercado Pago ainda está verificando o pagamento.") from exc

    if not response.is_success:
        provider_error, cause_codes = _payment_error_diagnostics(response)
        logger.error(
            "Mercado Pago rejected card payment (HTTP %s; error=%s; cause_codes=%s)",
            response.status_code,
            provider_error,
            ",".join(cause_codes) or "none",
        )
        raise MercadoPagoRequestError(response.status_code, provider_error, cause_codes)
    try:
        result = response.json()
    except ValueError as exc:
        raise RuntimeError("O Mercado Pago ainda está verificando o pagamento.") from exc
    if not isinstance(result, dict) or not result.get("id") or not result.get("status"):
        raise RuntimeError("O Mercado Pago ainda está verificando o pagamento.")
    return result
