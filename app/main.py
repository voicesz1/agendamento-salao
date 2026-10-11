from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import BASE_DIR, IS_PRODUCTION, SECRET_KEY, SESSION_HTTPS_ONLY, SESSION_MAX_AGE, validate_runtime_config
from app.database import Base, SessionLocal, engine, migrate_customer_accounts
from app.routers import admin, customers, public
from app.seed import seed_if_needed


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_runtime_config()
    Base.metadata.create_all(bind=engine)
    migrate_customer_accounts()
    db = SessionLocal()
    try:
        seed_if_needed(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="Agendamento Salão",
    lifespan=lifespan,
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=SESSION_MAX_AGE,
    same_site="strict",
    https_only=SESSION_HTTPS_ONLY,
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; form-action 'self'; "
        "base-uri 'self'; frame-ancestors 'none'",
    )
    if IS_PRODUCTION:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")
app.include_router(public.router)
app.include_router(customers.router)
app.include_router(admin.router)


@app.get("/healthz", include_in_schema=False)
def healthz():
    from sqlalchemy import text

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok"}
