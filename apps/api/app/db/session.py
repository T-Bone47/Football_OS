from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

settings = get_settings()
# pool_pre_ping (Phase 17 incident drills): after a database restart, pooled
# connections are dead; pinging on checkout replaces them instead of failing requests.
engine = create_async_engine(settings.database_url, echo=False, future=True, pool_pre_ping=True)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session
