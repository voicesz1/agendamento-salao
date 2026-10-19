from sqlalchemy import LargeBinary, create_engine, event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL

url = make_url(DATABASE_URL)
is_sqlite = url.drivername.startswith("sqlite")
connect_args = {"check_same_thread": False, "timeout": 30} if is_sqlite else {"connect_timeout": 10}
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=2,
    max_overflow=0,
)

if is_sqlite:
    @event.listens_for(engine, "connect")
    def configure_sqlite(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def migrate_payments() -> None:
    """Preserve existing bookings; unknown historical prices remain unknown."""
    with engine.begin() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("appointments")}
        additions = {
            "amount_cents": "INTEGER NULL",
            "payment_method": "VARCHAR(20) NOT NULL DEFAULT 'no_local'",
            "payment_status": "VARCHAR(20) NOT NULL DEFAULT 'pendente'",
            "payment_confirmed_at": "TIMESTAMP NULL",
            "pix_key": "VARCHAR(254) NOT NULL DEFAULT ''",
            "pix_recipient": "VARCHAR(120) NOT NULL DEFAULT ''",
            "mercadopago_preference_id": "VARCHAR(100) NOT NULL DEFAULT ''",
            "mercadopago_payment_id": "VARCHAR(100) NOT NULL DEFAULT ''",
            "payment_provider_status": "VARCHAR(40) NOT NULL DEFAULT ''",
        }
        for name, sql_type in additions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE appointments ADD COLUMN {name} {sql_type}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_service_images() -> None:
    """Add optional image storage without changing existing services."""
    with engine.begin() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("services")}
        if "image_data" not in columns:
            sql_type = LargeBinary().compile(dialect=connection.dialect)
            connection.execute(text(f"ALTER TABLE services ADD COLUMN image_data {sql_type} NULL"))
        if "image_revision" not in columns:
            connection.execute(text("ALTER TABLE services ADD COLUMN image_revision VARCHAR(64) NOT NULL DEFAULT ''"))


def migrate_customer_accounts() -> None:
    """Add the optional customer link to existing appointment tables."""
    columns = {column["name"] for column in inspect(engine).get_columns("appointments")}
    with engine.begin() as connection:
        if "customer_id" not in columns:
            connection.execute(
                text("ALTER TABLE appointments ADD COLUMN customer_id INTEGER REFERENCES customers(id)")
            )

        customer_columns = {column["name"] for column in inspect(connection).get_columns("customers")}
        is_legacy_customer_schema = "email_verified_at" not in customer_columns
        new_columns = {
            "email_verified_at": "TIMESTAMP NULL",
            "verification_token_hash": "VARCHAR(64) NULL",
            "verification_expires_at": "TIMESTAMP NULL",
        }
        for name, sql_type in new_columns.items():
            if name not in customer_columns:
                connection.execute(text(f"ALTER TABLE customers ADD COLUMN {name} {sql_type}"))

        # Accounts created before email verification was introduced stay usable.
        if is_legacy_customer_schema:
            connection.execute(
                text(
                    "UPDATE customers SET email_verified_at = created_at "
                    "WHERE email_verified_at IS NULL AND verification_token_hash IS NULL"
                )
            )
