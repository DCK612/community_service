"""
定价参考数据仓储 — PriceGuide CRUD 操作。
"""

from typing import List, Optional

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from models.price_guide import PriceGuide


async def get_all(db: AsyncSession, *, category: Optional[str] = None) -> List[PriceGuide]:
    """获取所有启用的定价参考（可选按类别过滤）。

    Args:
        db: 数据库会话。
        category: 服务类别（可选），为 None 时返回全部。

    Returns:
        PriceGuide 列表。
    """
    stmt = select(PriceGuide).where(PriceGuide.is_active == True)
    if category:
        stmt = stmt.where(PriceGuide.category == category)
    stmt = stmt.order_by(PriceGuide.category, PriceGuide.id)

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_all_admin(
    db: AsyncSession, *, category: Optional[str] = None
) -> List[PriceGuide]:
    """获取所有定价记录（含禁用的，管理端用）。

    Args:
        db: 数据库会话。
        category: 服务类别（可选）。

    Returns:
        PriceGuide 列表。
    """
    stmt = select(PriceGuide)
    if category:
        stmt = stmt.where(PriceGuide.category == category)
    stmt = stmt.order_by(PriceGuide.category, PriceGuide.is_active.desc(), PriceGuide.id)

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_by_id(db: AsyncSession, price_id: int) -> Optional[PriceGuide]:
    """根据 ID 获取定价记录。

    Args:
        db: 数据库会话。
        price_id: 定价记录 ID。

    Returns:
        PriceGuide 实例或 None。
    """
    result = await db.execute(select(PriceGuide).where(PriceGuide.id == price_id))
    return result.scalar_one_or_none()


async def create(db: AsyncSession, data: dict) -> PriceGuide:
    """创建新的定价记录。

    Args:
        db: 数据库会话。
        data: 定价数据字典。

    Returns:
        新创建的 PriceGuide 实例。
    """
    item = PriceGuide(**data)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def update_by_id(db: AsyncSession, price_id: int, data: dict) -> Optional[PriceGuide]:
    """更新定价记录。

    Args:
        db: 数据库会话。
        price_id: 定价记录 ID。
        data: 要更新的字段字典。

    Returns:
        更新后的 PriceGuide 实例或 None。
    """
    result = await db.execute(
        update(PriceGuide).where(PriceGuide.id == price_id).values(**data)
    )
    await db.commit()
    if result.rowcount == 0:
        return None
    return await get_by_id(db, price_id)


async def delete_by_id(db: AsyncSession, price_id: int) -> bool:
    """删除定价记录。

    Args:
        db: 数据库会话。
        price_id: 定价记录 ID。

    Returns:
        是否成功删除。
    """
    result = await db.execute(delete(PriceGuide).where(PriceGuide.id == price_id))
    await db.commit()
    return result.rowcount > 0
