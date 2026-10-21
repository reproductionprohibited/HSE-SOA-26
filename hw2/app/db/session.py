from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)

# expire_on_commit=False — объекты остаются доступны после commit для сборки ответа
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)
