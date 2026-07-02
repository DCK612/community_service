"""
定价参考业务服务 — 定价查询、管理逻辑。
"""

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

import repository.price_guide_repo as repo


async def list_price_guides(
    db: AsyncSession, *, category: Optional[str] = None, admin: bool = False
) -> Dict[str, Any]:
    """查询定价参考列表。

    Args:
        db: 数据库会话。
        category: 服务类别过滤（可选）。
        admin: 是否为管理端查询（含禁用的）。

    Returns:
        统一响应格式。
    """
    if admin:
        items = await repo.get_all_admin(db, category=category)
    else:
        items = await repo.get_all(db, category=category)

    return {
        "code": 200,
        "message": "查询成功",
        "data": [
            {
                "id": item.id,
                "category": item.category.value,
                "name": item.name,
                "description": item.description,
                "price_min": item.price_min,
                "price_max": item.price_max,
                "unit": item.unit,
                "price_range": f"¥{item.price_min} ~ ¥{item.price_max} / {item.unit}",
                "is_active": item.is_active,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            }
            for item in items
        ],
    }


async def create_price_guide(db: AsyncSession, data: dict) -> Dict[str, Any]:
    """创建定价参考。

    Args:
        db: 数据库会话。
        data: 定价数据。

    Returns:
        统一响应格式。
    """
    item = await repo.create(db, data)
    return {
        "code": 200,
        "message": "创建成功",
        "data": {"id": item.id, "name": item.name},
    }


async def update_price_guide(db: AsyncSession, price_id: int, data: dict) -> Dict[str, Any]:
    """更新定价参考。

    Args:
        db: 数据库会话。
        price_id: 定价 ID。
        data: 更新字段。

    Returns:
        统一响应格式。
    """
    item = await repo.update_by_id(db, price_id, data)
    if not item:
        return {"code": 404, "message": "定价记录不存在", "data": None}
    return {"code": 200, "message": "更新成功", "data": {"id": item.id}}


async def delete_price_guide(db: AsyncSession, price_id: int) -> Dict[str, Any]:
    """删除定价参考。

    Args:
        db: 数据库会话。
        price_id: 定价 ID。

    Returns:
        统一响应格式。
    """
    success = await repo.delete_by_id(db, price_id)
    if not success:
        return {"code": 404, "message": "定价记录不存在", "data": None}
    return {"code": 200, "message": "删除成功", "data": None}
