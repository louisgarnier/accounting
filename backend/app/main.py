from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.routers import health
from app.routers.banking import router as banking_router
from app.routers.protected_test import router as protected_test_router
from app.routers.webhooks import router as webhooks_router
from app.config import FRONTEND_URL
from app.logger import api_logger

app = FastAPI(title="Accounting API", version="1.0.0")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    api_logger.info(f"📥 {request.method} {request.url.path}")
    response = await call_next(request)
    api_logger.info(f"📤 {request.method} {request.url.path} → {response.status_code}")
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(protected_test_router)
app.include_router(webhooks_router)
app.include_router(banking_router)
