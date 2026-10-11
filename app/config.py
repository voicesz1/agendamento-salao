import os
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.engine import make_url

BASE_DIR = Path(__file__).resolve().parent.parent
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV == "production"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'salao.db'}")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
SECRET_KEY = os.getenv("SECRET_KEY", "development-only-secret-change-before-deploying")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
SESSION_HTTPS_ONLY = os.getenv("SESSION_HTTPS_ONLY", str(IS_PRODUCTION)).lower() in {"1", "true", "yes"}
SESSION_MAX_AGE = int(os.getenv("SESSION_MAX_AGE", "28800"))
TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "America/Sao_Paulo"))
DEFAULT_ADMIN_PASSWORD = "admin123"
DEFAULT_OWNER_WHATSAPP = "5511999999999"
DEFAULT_SALON_NAME = "Atelier das Unhas"


def validate_runtime_config() -> None:
    """Fail early when production is started with unsafe or unusable settings."""
    if SESSION_MAX_AGE < 300:
        raise RuntimeError("SESSION_MAX_AGE deve ser de pelo menos 300 segundos.")
    try:
        make_url(DATABASE_URL)
    except Exception as exc:
        raise RuntimeError("DATABASE_URL inválida.") from exc
    if not IS_PRODUCTION:
        return
    if len(SECRET_KEY) < 32 or SECRET_KEY == "development-only-secret-change-before-deploying":
        raise RuntimeError("Defina SECRET_KEY com pelo menos 32 caracteres aleatórios em produção.")
    if len(ADMIN_PASSWORD) < 12:
        raise RuntimeError("Defina ADMIN_PASSWORD com pelo menos 12 caracteres em produção.")
