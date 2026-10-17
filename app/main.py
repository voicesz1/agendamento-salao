from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import (
    ANDROID_APP_PACKAGE,
    ANDROID_APP_SHA256_CERT_FINGERPRINT,
    BASE_DIR,
    IS_PRODUCTION,
    SECRET_KEY,
    SESSION_HTTPS_ONLY,
    SESSION_MAX_AGE,
    validate_runtime_config,
)
from app.database import Base, SessionLocal, engine, migrate_customer_accounts, migrate_payments, migrate_service_images
from app.routers import admin, media, public
from app.seed import seed_if_needed


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_runtime_config()
    Base.metadata.create_all(bind=engine)
    migrate_customer_accounts()
    migrate_payments()
    migrate_service_images()
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
    if not request.url.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "no-store")
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


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(
        BASE_DIR / "app" / "static" / "sw.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


@app.get("/.well-known/assetlinks.json", include_in_schema=False)
def android_asset_links():
    fingerprints = [value.strip().upper() for value in ANDROID_APP_SHA256_CERT_FINGERPRINT.split(",") if value.strip()]
    if not fingerprints:
        return JSONResponse(content=[])
    for fingerprint in fingerprints:
        parts = fingerprint.split(":")
        if len(parts) != 32 or any(len(part) != 2 or any(char not in "0123456789ABCDEF" for char in part) for part in parts):
            return JSONResponse(content={"error": "ANDROID_APP_SHA256_CERT_FINGERPRINT inválida."}, status_code=503)
    package_names = [value.strip() for value in ANDROID_APP_PACKAGE.split(",") if value.strip()]
    if not package_names:
        return JSONResponse(content={"error": "ANDROID_APP_SHA256_CERT_FINGERPRINT inválida."}, status_code=503)
    return JSONResponse(
        content=[
            {
                "relation": ["delegate_permission/common.handle_all_urls"],
                "target": {
                    "namespace": "android_app",
                    "package_name": package_name,
                    "sha256_cert_fingerprints": fingerprints,
                },
            }
            for package_name in package_names
        ],
        headers={"Cache-Control": "public, max-age=300"},
    )


app.include_router(public.router)
app.include_router(admin.router)
app.include_router(media.router)


@app.get("/healthz", include_in_schema=False)
def healthz():
    from sqlalchemy import text

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok"}
