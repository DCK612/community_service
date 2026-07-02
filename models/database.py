"""
数据库引擎与异步会话管理模块。
基于 SQLAlchemy 异步引擎 + aiosqlite，开发环境使用 SQLite，
生产环境可无缝切换为 PostgreSQL。
"""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from config import DATABASE_URL


# 创建异步数据库引擎
# echo=False 关闭 SQL 日志，生产环境建议保持关闭
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

# 异步会话工厂
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# SQLAlchemy 声明式基类
class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""
    pass


async def get_db() -> AsyncSession:
    """FastAPI 依赖注入：获取异步数据库会话。

    用法：
        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """创建所有表（开发环境用，生产环境请使用 Alembic 迁移）。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """关闭数据库引擎连接池。"""
    await engine.dispose()
