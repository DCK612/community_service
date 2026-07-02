"""
定价参考路由 — 查询/管理服务项目参考价格。

公开接口（居民端/服务者端可用）：
- GET  /price-guide           查询所有已启用的定价参考
- GET  /price-guide/{category} 按类别查询

管理端接口：
- GET    /admin/price-guide           查询所有（含禁用）
- POST   /admin/price-guide           创建定价
- PUT    /admin/price-guide/{id}      更新定价
- DELETE /admin/price-guide/{id}      删除定价
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import async_session_factory
from models.order import OrderCategory
from service import price_guide_service

router = APIRouter(prefix="/price-guide", tags=["定价参考"])


# ==================== 请求/响应模型 ====================

class PriceGuideCreate(BaseModel):
    """创建定价参考的请求体。"""
    category: str = Field(..., description="服务类别: REPAIR/CLEANING/MOVING/TUTORING/ELDERLY_CARE/OTHER")
    name: str = Field(..., description="服务项目名称")
    description: Optional[str] = Field(None, description="服务描述")
    price_min: float = Field(..., description="参考最低价（元）")
    price_max: float = Field(..., description="参考最高价（元）")
    unit: str = Field(default="次", description="计价单位")


class PriceGuideUpdate(BaseModel):
    """更新定价参考的请求体 — 所有字段可选。"""
    category: Optional[str] = Field(None, description="服务类别")
    name: Optional[str] = Field(None, description="服务项目名称")
    description: Optional[str] = Field(None, description="服务描述")
    price_min: Optional[float] = Field(None, description="参考最低价")
    price_max: Optional[float] = Field(None, description="参考最高价")
    unit: Optional[str] = Field(None, description="计价单位")
    is_active: Optional[bool] = Field(None, description="是否启用")


# ==================== 依赖注入 ====================

async def get_db():
    """获取数据库会话（依赖注入）。"""
    async with async_session_factory() as session:
        yield session


# ==================== 公开接口 ====================

@router.get("")
async def list_price_guides(
    category: Optional[str] = Query(None, description="服务类别过滤"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """查询已启用的定价参考列表（居民端/服务者端）。"""
    return await price_guide_service.list_price_guides(db, category=category)


@router.get("/{category}")
async def list_by_category(
    category: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """按服务类别查询定价参考。"""
    return await price_guide_service.list_price_guides(db, category=category.upper())


# ==================== 管理端接口 ====================

admin_router = APIRouter(prefix="/admin/price-guide", tags=["管理端-定价管理"])


@admin_router.get("")
async def admin_list_price_guides(
    category: Optional[str] = Query(None, description="服务类别过滤"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """管理端查询所有定价参考（含禁用）。"""
    return await price_guide_service.list_price_guides(db, category=category, admin=True)


@admin_router.post("")
async def admin_create_price_guide(
    body: PriceGuideCreate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """管理端创建定价参考。"""
    data = body.model_dump(exclude_none=True)
    return await price_guide_service.create_price_guide(db, data)


@admin_router.put("/{price_id}")
async def admin_update_price_guide(
    price_id: int,
    body: PriceGuideUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """管理端更新定价参考。"""
    data = {k: v for k, v in body.model_dump(exclude_none=True).items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="至少提供一个更新字段")
    return await price_guide_service.update_price_guide(db, price_id, data)


@admin_router.delete("/{price_id}")
async def admin_delete_price_guide(
    price_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """管理端删除定价参考。"""
    return await price_guide_service.delete_price_guide(db, price_id)
