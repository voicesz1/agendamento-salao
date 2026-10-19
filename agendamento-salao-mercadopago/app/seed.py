from datetime import datetime, time

from sqlalchemy.orm import Session

from app.config import ADMIN_PASSWORD, DEFAULT_ADMIN_PASSWORD, DEFAULT_OWNER_WHATSAPP, DEFAULT_SALON_NAME, IS_PRODUCTION, TIMEZONE
from app.models import BusinessHours, Service, Setting
from app.security import hash_password, verify_password
from app.settings_store import get_setting, set_setting

SERVICES = [
    ("Manicure e pedicure", "Manicure simples", "Corte, lixamento e esmaltação tradicional nas mãos.", 35, 40),
    ("Manicure e pedicure", "Pedicure simples", "Cuidado dos pés com corte, lixamento e esmaltação.", 45, 50),
    ("Manicure e pedicure", "Manicure + pedicure", "Combo completo de mãos e pés com esmaltação tradicional.", 70, 80),
    ("Esmaltação em gel", "Gel nas mãos", "Esmaltação em gel com brilho duradouro nas mãos.", 80, 60),
    ("Esmaltação em gel", "Gel nos pés", "Esmaltação em gel nos pés, resistente e uniforme.", 90, 70),
    ("Esmaltação em gel", "Blindagem", "Proteção e fortalecimento das unhas naturais.", 90, 60),
    ("Esmaltação em gel", "Francesinha em gel", "Francesinha clássica ou reversa em gel.", 95, 75),
    ("Alongamento", "Alongamento em gel", "Alongamento completo em gel, formato à escolha.", 150, 120),
    ("Alongamento", "Alongamento em fibra", "Alongamento em fibra de vidro, estrutura firme.", 160, 120),
    ("Alongamento", "Manutenção de alongamento", "Manutenção, recrescimento e ajuste do alongamento.", 90, 90),
    ("Alongamento", "Baby boomer", "Degradê suave no alongamento, acabamento elegante.", 120, 90),
    ("Alongamento", "Remoção de gel ou alongamento", "Remoção segura sem danificar a unha natural.", 40, 30),
    ("Nail art", "Nail art completa", "Decoração artística em todas as unhas.", 55, 40),
    ("Spa", "Spa das mãos", "Esfoliação, hidratação e massagem nas mãos.", 55, 40),
    ("Spa", "Spa dos pés", "Esfoliação, hidratação e massagem nos pés.", 70, 50),
]


def seed_if_needed(db: Session) -> None:
    if not db.query(Service).first():
        for category, name, description, price, duration in SERVICES:
            db.add(
                Service(
                    name=name,
                    category=category,
                    description=description,
                    price=price,
                    duration_minutes=duration,
                    active=True,
                )
            )

    if not db.query(BusinessHours).first():
        for weekday in range(7):
            is_open = weekday != 6
            db.add(
                BusinessHours(
                    weekday=weekday,
                    is_open=is_open,
                    open_time=time(9, 0),
                    close_time=time(19, 0),
                    break_start=time(12, 0) if is_open else None,
                    break_end=time(13, 0) if is_open else None,
                )
            )

    defaults = {
        "salon_name": DEFAULT_SALON_NAME,
        "salon_tagline": "Unhas com cuidado, horário marcado",
        "owner_whatsapp": "" if IS_PRODUCTION else DEFAULT_OWNER_WHATSAPP,
        "slot_interval_minutes": "30",
        "seeded_at": datetime.now(TIMEZONE).isoformat(),
    }
    for key, value in defaults.items():
        if db.get(Setting, key) is None:
            set_setting(db, key, value)

    # Remove legacy integration credentials left by older versions.
    for key in ("callmebot_apikey", "webhook_url"):
        legacy_setting = db.get(Setting, key)
        if legacy_setting:
            db.delete(legacy_setting)

    owner_phone = db.get(Setting, "owner_whatsapp")
    if IS_PRODUCTION and owner_phone and owner_phone.value == DEFAULT_OWNER_WHATSAPP:
        set_setting(db, "owner_whatsapp", "")

    password_row = db.get(Setting, "admin_password_hash")
    if password_row is None:
        initial_password = ADMIN_PASSWORD if IS_PRODUCTION else DEFAULT_ADMIN_PASSWORD
        set_setting(db, "admin_password_hash", hash_password(initial_password))
    elif IS_PRODUCTION and verify_password(DEFAULT_ADMIN_PASSWORD, password_row.value):
        # Replace the well-known local bootstrap password when deploying an existing database.
        set_setting(db, "admin_password_hash", hash_password(ADMIN_PASSWORD))

    db.commit()
