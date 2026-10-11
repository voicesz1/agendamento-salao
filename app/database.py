from sqlalchemy import create_engine, event, inspect, text
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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
