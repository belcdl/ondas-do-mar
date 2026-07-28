import logging

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.apartments import router as apartments_router
from app.api.auth import router as auth_router
from app.api.availability import router as availability_router
from app.api.bookings import router as bookings_router
from app.api.owners import router as owners_router
from app.api.payments import router as payments_router
from app.api.rate_rules import router as rate_rules_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.db.session import get_db

logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(title=settings.project_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(owners_router, prefix=settings.api_v1_str)
app.include_router(apartments_router, prefix=settings.api_v1_str)
app.include_router(bookings_router, prefix=settings.api_v1_str)
app.include_router(rate_rules_router, prefix=settings.api_v1_str)
app.include_router(availability_router, prefix=settings.api_v1_str)
app.include_router(payments_router, prefix=settings.api_v1_str)
app.include_router(auth_router, prefix=settings.api_v1_str)

register_exception_handlers(app)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
async def health_check_db(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    try:
        await db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Database health check failed")
        raise HTTPException(status_code=503, detail="Database connection failed")
    return {"status": "ok", "database": "connected"}
