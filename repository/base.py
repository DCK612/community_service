"""
Repository 泛型 CRUD 基类。

提供通用的增删改查方法，所有具体 Repository 继承此类。
使用 SQLAlchemy 异步 API（AsyncSession）。
"""

from typing import Any, Generic, List, Optional, Sequence, Type, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from models.database import Base


# 泛型类型变量，代表任意 ORM 模型
ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """泛型 CRUD 基类。

    提供以下通用方法：
    - get_by_id: 按主键查询单条
    - get_all: 查询全部（支持分页）
    - create: 新增单条
    - update: 更新单条
    - delete: 按主键删除
    - count: 统计数量
    - exists: 判断是否存在
    """

    def __init__(self, model: Type[ModelType]):
        """初始化 Repository。

        Args:
            model: 对应的 ORM 模型类。
        """
        self.model = model

    # ==================== 查询方法 ====================

    async def get_by_id(
        self, db: AsyncSession, obj_id: int
    ) -> Optional[ModelType]:
        """按主键 ID 查询单条记录。

        Args:
            db: 异步数据库会话。
            obj_id: 主键 ID。

        Returns:
            匹配的 ORM 对象，不存在则返回 None。
        """
        result = await db.execute(
            select(self.model).where(self.model.id == obj_id)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        db: AsyncSession,
        offset: int = 0,
        limit: int = 100,
        order_by: Any = None,
        filters: Optional[List[Any]] = None,
    ) -> Sequence[ModelType]:
        """查询全部记录（支持分页、排序、过滤）。

        Args:
            db: 异步数据库会话。
            offset: 偏移量。
            limit: 每页数量。
            order_by: 排序字段（如 Model.created_at.desc()）。
            filters: 过滤条件列表（如 [Model.status == "ONLINE"]）。

        Returns:
            匹配的 ORM 对象列表。
        """
        stmt: Select = select(self.model)

        # 应用过滤条件
        if filters:
            stmt = stmt.where(*filters)

        # 应用排序
        if order_by is not None:
            stmt = stmt.order_by(order_by)

        stmt = stmt.offset(offset).limit(limit)
        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_one_by_filter(
        self, db: AsyncSession, filters: List[Any]
    ) -> Optional[ModelType]:
        """按条件查询单条记录。

        Args:
            db: 异步数据库会话。
            filters: SQLAlchemy 过滤条件列表。

        Returns:
            匹配的第一条 ORM 对象，不存在则返回 None。
        """
        stmt = select(self.model).where(*filters)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    # ==================== 写入方法 ====================

    async def create(self, db: AsyncSession, obj: ModelType) -> ModelType:
        """新增单条记录。

        Args:
            db: 异步数据库会话。
            obj: 要新增的 ORM 对象实例。

        Returns:
            刷新后的 ORM 对象（含自增 ID）。
        """
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return obj

    async def create_all(
        self, db: AsyncSession, objs: List[ModelType]
    ) -> List[ModelType]:
        """批量新增记录。

        Args:
            db: 异步数据库会话。
            objs: ORM 对象实例列表。

        Returns:
            新增的对象列表。
        """
        db.add_all(objs)
        await db.commit()
        return objs

    async def update(
        self, db: AsyncSession, obj: ModelType, values: dict
    ) -> ModelType:
        """更新单条记录的指定字段。

        Args:
            db: 异步数据库会话。
            obj: 要更新的 ORM 对象实例。
            values: 要更新的字段字典，如 {"status": "ONLINE"}。

        Returns:
            更新后的 ORM 对象。
        """
        for key, value in values.items():
            if hasattr(obj, key):
                setattr(obj, key, value)
        await db.commit()
        await db.refresh(obj)
        return obj

    async def delete(self, db: AsyncSession, obj: ModelType) -> None:
        """删除单条记录。

        Args:
            db: 异步数据库会话。
            obj: 要删除的 ORM 对象实例。
        """
        await db.delete(obj)
        await db.commit()

    # ==================== 统计方法 ====================

    async def count(self, db: AsyncSession, filters: Optional[List[Any]] = None) -> int:
        """统计记录数量。

        Args:
            db: 异步数据库会话。
            filters: 可选的过滤条件列表。

        Returns:
            记录总数。
        """
        stmt = select(func.count(self.model.id))
        if filters:
            stmt = stmt.where(*filters)
        result = await db.execute(stmt)
        return result.scalar() or 0

    async def exists(
        self, db: AsyncSession, filters: List[Any]
    ) -> bool:
        """判断是否存在满足条件的记录。

        Args:
            db: 异步数据库会话。
            filters: 过滤条件列表。

        Returns:
            存在返回 True，否则 False。
        """
        count = await self.count(db, filters)
        return count > 0
