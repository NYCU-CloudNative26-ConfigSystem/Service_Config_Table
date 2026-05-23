import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import configure_logging
from app.database.connection import Base, engine
from app.database.redis import close_redis
from app.routers import auth, config_table, projects

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- startup ----
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables verified / created.")
    yield
    # ---- shutdown ----
    await engine.dispose()
    await close_redis()
    logger.info("Application shutdown complete.")


app = FastAPI(
    title=settings.app_name,
    description=(
        "Manages key-value pair config table entries. "
        "Each entry maps a **Key ID** (from Config Service) to a "
        "**Value ID** (from Config Service), recording the creator, "
        "their company, and the UTC creation timestamp."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — tighten origins in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
api_prefix = "/api/v1"
app.include_router(auth.router, prefix=api_prefix)
app.include_router(config_table.router, prefix=api_prefix)
app.include_router(projects.router, prefix=api_prefix)


@app.get("/health", tags=["health"], summary="Liveness probe")
async def health_check():
    return {"status": "ok"}
