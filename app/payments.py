"""Manual Pix instructions. This module never claims to verify a bank transfer."""
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.settings_store import get_setting


def price_in_cents(price: float) -> int:
    return int((Decimal(str(price)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def pix_settings(db: Session) -> dict:
    key = get_setting(db, "pix_key").strip()
    recipient = get_setting(db, "pix_recipient").strip()
    return {"pix_available": bool(key and recipient), "pix_key": key, "pix_recipient": recipient}
