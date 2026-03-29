import os
import traceback
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import FRONTEND_URL
from app.logger import api_logger, backend_logger, log_to_supabase
from app.routers import health
from app.routers.banking import router as banking_router
from app.routers.protected_test import router as protected_test_router
from app.routers.webhooks import router as webhooks_router

app = FastAPI(title="Accounting API", version="1.0.0")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    import time
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    start = time.monotonic()

    api_logger.info(f"📥 {request.method} {request.url.path} req={request_id}")
    log_to_supabase({
        "layer": "api",
        "level": "info",
        "message": f"{request.method} {request.url.path}",
        "method": request.method,
        "url": str(request.url.path),
        "request_id": request_id,
    })

    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        tb = traceback.format_exc()
        api_logger.error(f"❌ {request.method} {request.url.path} unhandled: {exc}\n{tb}")
        log_to_supabase({
            "layer": "api",
            "level": "error",
            "message": f"unhandled exception: {exc}",
            "method": request.method,
            "url": str(request.url.path),
            "request_id": request_id,
            "duration_ms": duration_ms,
            "context": {"traceback": tb},
        })
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    duration_ms = int((time.monotonic() - start) * 1000)
    api_logger.info(f"📤 {request.method} {request.url.path} → {response.status_code} ({duration_ms}ms) req={request_id}")
    log_to_supabase({
        "layer": "api",
        "level": "info",
        "message": f"{request.method} {request.url.path} → {response.status_code}",
        "method": request.method,
        "url": str(request.url.path),
        "status_code": response.status_code,
        "duration_ms": duration_ms,
        "request_id": request_id,
    })

    response.headers["X-Request-ID"] = request_id
    return response


# CORS must be added AFTER the logging middleware so it is the outermost layer.
# If added before, the logging middleware's JSONResponse(500) bypasses CORS entirely
# and the browser sees a cross-origin error with no Access-Control-Allow-Origin header.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL.rstrip("/")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(protected_test_router)
app.include_router(webhooks_router)
app.include_router(banking_router)


@app.on_event("startup")
async def startup_event():
    """Log env var presence (never values) and verify Supabase connectivity."""
    env_vars = [
        "SUPABASE_URL", "SUPABASE_SERVICE_KEY", "FRONTEND_URL",
        "APP_USER_ID", "ENABLE_BANKING_WEBHOOK_SECRET",
        "ENABLE_BANKING_APP_ID", "ENABLE_BANKING_PRIVATE_KEY",
    ]
    presence = {var: bool(os.getenv(var)) for var in env_vars}
    backend_logger.info(f"🚀 [Backend] starting — env vars: {presence}")
    log_to_supabase({
        "layer": "backend",
        "level": "info",
        "message": "startup",
        "context": {"env_vars_present": presence},
    })

    try:
        from app.database import get_db
        get_db().table("logs").select("id").limit(1).execute()
        backend_logger.info("✅ [Backend] Supabase connection ok")
        log_to_supabase({"layer": "backend", "level": "info", "message": "supabase connection ok"})
    except Exception as e:
        backend_logger.error(f"❌ [Backend] Supabase connection failed: {e}")
