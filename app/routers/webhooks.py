"""Authenticated Mercado Pago payment notifications."""
import hashlib
import hmac
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import MERCADOPAGO_ACCESS_TOKEN, MERCADOPAGO_WEBHOOK_SECRET
from app.database import get_db
from app.models import Appointment
from app.config import TIMEZONE

router = APIRouter()


def _signature_is_valid(request: Request, data_id: str) -> bool:
    signature = request.headers.get("x-signature", "")
    request_id = request.headers.get("x-request-id", "")
    fields = dict(re.findall(r"(ts|v1)=([^,]+)", signature))
    timestamp, received = fields.get("ts", ""), fields.get("v1", "")
    if not MERCADOPAGO_WEBHOOK_SECRET or not request_id or not timestamp or not received:
        return False
    manifest = f"id:{data_id.lower()};request-id:{request_id};ts:{timestamp};"
    expected = hmac.new(
        MERCADOPAGO_WEBHOOK_SECRET.encode("utf-8"), manifest.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, received)


@router.post("/webhooks/mercadopago", include_in_schema=False)
async def mercadopago_webhook(request: Request, db: Session = Depends(get_db)):
    if not MERCADOPAGO_ACCESS_TOKEN or not MERCADOPAGO_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook de pagamento não configurado.")
    data_id = request.query_params.get("data.id", "").strip()
    event_type = request.query_params.get("type", "").strip()
    if not data_id:
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        data_id = str((payload.get("data") or {}).get("id", "")).strip()
        event_type = event_type or str(payload.get("type", "")).strip()
    if event_type not in {"payment", ""}:
        return {"received": True}
    if not data_id or not data_id.isdigit() or not _signature_is_valid(request, data_id):
        raise HTTPException(status_code=401, detail="Assinatura do webhook inválida.")

    try:
        response = httpx.get(
            f"https://api.mercadopago.com/v1/payments/{data_id}",
            headers={"Authorization": f"Bearer {MERCADOPAGO_ACCESS_TOKEN}"},
            timeout=15,
        )
        response.raise_for_status()
        payment = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Não foi possível consultar o pagamento.") from exc

    try:
        appointment_id = int(payment.get("external_reference", ""))
    except (TypeError, ValueError):
        return {"received": True}
    appointment = db.get(Appointment, appointment_id)
    if not appointment or appointment.payment_method != "cartao":
        return {"received": True}
    payment_id = str(payment.get("id", data_id))[:100]
    if appointment.payment_status == "pago" and appointment.mercadopago_payment_id != payment_id:
        return {"received": True}
    try:
        paid_cents = int((Decimal(str(payment.get("transaction_amount"))) * 100).quantize(Decimal("1")))
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Valor do pagamento inválido.")
    if payment.get("currency_id") != "BRL" or paid_cents != appointment.amount_cents:
        raise HTTPException(status_code=400, detail="Valor ou moeda do pagamento não confere.")

    status = str(payment.get("status", "unknown"))[:40]
    appointment.mercadopago_payment_id = payment_id
    appointment.payment_provider_status = status
    if status == "approved":
        appointment.payment_status = "pago"
        appointment.payment_confirmed_at = datetime.now(TIMEZONE).replace(tzinfo=None)
    elif status in {"refunded", "charged_back"}:
        appointment.payment_status = "estornado"
    elif status == "cancelled":
        appointment.payment_status = "cancelado"
    elif status == "rejected":
        appointment.payment_status = "recusado"
        appointment.payment_confirmed_at = None
    else:
        appointment.payment_status = "pendente"
        appointment.payment_confirmed_at = None
    db.commit()
    return {"received": True}
