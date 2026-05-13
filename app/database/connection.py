from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def _async_database_url(url: str) -> str:
    """Ensure the database URL uses an async driver.

    Converts bare ``postgresql://`` and ``postgres://`` URLs to
    ``postgresql+asyncpg://`` so that SQLAlchemy's async engine works even
    when the environment variable is set without the explicit driver suffix.
    """
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix):]
    return url


engine = create_async_engine(_async_database_url(settings.database_url), echo=settings.debug)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
