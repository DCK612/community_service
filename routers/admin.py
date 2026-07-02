"""
管理端路由 — 三级权限体系：仪表盘、订单管理、用户管理、定价管理、申请审批、黑名单。
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from models.database import get_db
from models.order import Order, OrderStatus, OrderCategory
from models.user import UserRole, UserBase, ProviderProfile
from models.price_guide import PriceGuide
from models.review import Review
from repository.user_repo import user_repo
from repository.order_repo import order_repo
from service.blacklist_service import get_blacklist_detail
from routers.auth import require_admin_l1, require_admin_l2, require_admin_l3, require_super_admin

router = APIRouter(prefix="/admin", tags=["管理端"])


# ==================== 请求模型 ====================

class BlacklistRequest(BaseModel):
    """拉黑/解黑请求。"""
    provider_id: int = Field(..., description="服务者 ID")
    reason: Optional[str] = Field(default=None, description="原因")


class PriceGuideRequest(BaseModel):
    """定价配置请求。"""
    category: str = Field(..., description="服务类别: REPAIR/CLEANING/MOVING/TUTORING/ELDERLY_CARE/OTHER")
    name: str = Field(..., min_length=1, max_length=100, description="服务项目名称")
    description: Optional[str] = Field(default=None, description="服务描述")
    price_min: float = Field(..., gt=0, description="参考最低价")
    price_max: float = Field(..., gt=0, description="参考最高价")
    unit: str = Field(default="次", description="计价单位")
    is_active: bool = Field(default=True, description="是否启用")


class ApiResponse(BaseModel):
    """统一 API 响应。"""
    code: int = Field(default=200)
    message: str = Field(default="成功")
    data: Optional[object] = Field(default=None)


# ==================== 仪表盘（L1+） ====================

@router.get("/dashboard", response_model=ApiResponse)
async def get_dashboard(
    current_user=Depends(require_admin_l1),
    db: AsyncSession = Depends(get_db),
):
    """管理端仪表盘 — L1 及以上权限。"""
    # 用户统计
    resident_count = (await db.execute(
        select(func.count(UserBase.id)).where(UserBase.role == UserRole.RESIDENT)
    )).scalar() or 0

    provider_count = (await db.execute(
        select(func.count(UserBase.id)).where(UserBase.role == UserRole.PROVIDER)
    )).scalar() or 0

    # 订单统计
    total_orders = (await db.execute(select(func.count(Order.id)))).scalar() or 0
    pending_count = (await db.execute(
        select(func.count(Order.id)).where(Order.status == OrderStatus.PENDING)
    )).scalar() or 0
    completed_count = (await db.execute(
        select(func.count(Order.id)).where(Order.status == OrderStatus.COMPLETED)
    )).scalar() or 0

    # 收入统计（已支付预付的订单总金额）
    paid_orders = (await db.execute(
        select(func.sum(Order.amount)).where(Order.prepaid_status == "PAID")
    )).scalar() or 0

    # 黑名单统计
    blacklist_count = (await db.execute(
        select(func.count(ProviderProfile.id)).where(ProviderProfile.blacklisted == True)
    )).scalar() or 0

    return ApiResponse(code=200, message="查询成功", data={
        "users": {"residents": resident_count, "providers": provider_count,
                  "total": resident_count + provider_count},
        "orders": {"total": total_orders, "pending": pending_count,
                   "completed": completed_count,
                   "completion_rate": round(completed_count / total_orders * 100, 1) if total_orders else 0},
        "revenue": round(float(paid_orders), 2),
        "blacklist": {"total": blacklist_count},
    })


# ==================== 订单管理（L2+） ====================

@router.get("/orders", response_model=ApiResponse)
async def get_all_orders(
    status: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user=Depends(require_admin_l2),
    db: AsyncSession = Depends(get_db),
):
    """全部订单列表 — L2 及以上权限。"""
    stmt = select(Order)
    if status:
        stmt = stmt.where(Order.status == status)
    stmt = stmt.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size)

    total_result = await db.execute(select(func.count(Order.id)))
    total = total_result.scalar() or 0

    result = await db.execute(stmt)
    orders = result.scalars().all()

    return ApiResponse(code=200, message="查询成功", data={
        "total": total, "page": page, "page_size": page_size,
        "orders": [{
            "id": o.id, "order_no": o.order_no, "category": str(o.category),
            "description": o.description, "address": o.address,
            "amount": o.amount, "prepaid_amount": o.prepaid_amount,
            "prepaid_status": o.prepaid_status,
            "status": o.status.value, "resident_id": o.resident_id,
            "provider_id": o.provider_id,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        } for o in orders],
    })


@router.post("/orders/{order_id}/cancel", response_model=ApiResponse)
async def cancel_order_admin(
    order_id: int,
    reason: str = Query(default="管理员取消"),
    current_user=Depends(require_admin_l2),
    db: AsyncSession = Depends(get_db),
):
    """管理员取消订单 — L2 及以上权限。"""
    import datetime
    order = await order_repo.get_by_id(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status in (OrderStatus.COMPLETED, OrderStatus.CANCELLED):
        raise HTTPException(status_code=400, detail="终态订单无法取消")

    order.status = OrderStatus.CANCELLED
    order.cancelled_at = datetime.datetime.now()
    await db.commit()
    await db.refresh(order)

    return ApiResponse(code=200, message="订单已取消", data={"order_id": order_id, "status": order.status.value})


# ==================== 用户管理（L2+） ====================

@router.get("/users", response_model=ApiResponse)
async def get_all_users(
    role: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user=Depends(require_admin_l2),
    db: AsyncSession = Depends(get_db),
):
    """全部用户列表 — L2 及以上权限。"""
    stmt = select(UserBase)
    if role:
        stmt = stmt.where(UserBase.role == role)
    stmt = stmt.order_by(UserBase.created_at.desc()).offset((page - 1) * page_size).limit(page_size)

    total_result = await db.execute(select(func.count(UserBase.id)))
    total = total_result.scalar() or 0

    result = await db.execute(stmt)
    users = result.scalars().all()

    return ApiResponse(code=200, message="查询成功", data={
        "total": total, "page": page, "page_size": page_size,
        "users": [{
            "id": u.id, "phone": u.phone, "nickname": u.nickname,
            "role": u.role.value,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        } for u in users],
    })


# ==================== 黑名单管理（L3+） ====================

@router.get("/blacklist", response_model=ApiResponse)
async def get_blacklist(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user=Depends(require_admin_l3),
    db: AsyncSession = Depends(get_db),
):
    """黑名单列表 — L3 及以上权限。"""
    details = await get_blacklist_detail(db, offset=(page - 1) * page_size, limit=page_size)
    return ApiResponse(code=200, message="查询成功", data={
        "total": len(details), "page": page, "page_size": page_size, "blacklist": details,
    })


@router.post("/providers/{provider_id}/blacklist", response_model=ApiResponse)
async def blacklist_provider(
    provider_id: int,
    req: BlacklistRequest,
    current_user=Depends(require_admin_l3),
    db: AsyncSession = Depends(get_db),
):
    """拉黑服务者 — L3 及以上权限。"""
    from repository.blacklist_repo import blacklist_repo

    provider = await user_repo.get_by_id(db, provider_id)
    if provider is None or provider.provider_profile is None:
        raise HTTPException(status_code=404, detail="服务者不存在")

    await blacklist_repo.add_to_blacklist(db, provider, blacklist_type="permanent", freeze_days=365)
    return ApiResponse(code=200, message=f"服务者 {provider_id} 已拉黑",
                       data={"provider_id": provider_id})


@router.post("/providers/{provider_id}/unblacklist", response_model=ApiResponse)
async def unblacklist_provider(
    provider_id: int,
    current_user=Depends(require_admin_l3),
    db: AsyncSession = Depends(get_db),
):
    """解黑服务者 — L3 及以上权限。"""
    provider = await user_repo.get_by_id(db, provider_id)
    if provider is None or provider.provider_profile is None:
        raise HTTPException(status_code=404, detail="服务者不存在")

    provider.provider_profile.blacklisted = False
    await db.commit()
    return ApiResponse(code=200, message=f"服务者 {provider_id} 已解黑",
                       data={"provider_id": provider_id})


# ==================== 定价管理（L3+） ====================

@router.get("/price-guides", response_model=ApiResponse)
async def get_price_guides(
    category: Optional[str] = None,
    current_user=Depends(require_admin_l3),
    db: AsyncSession = Depends(get_db),
):
    """定价参考列表 — L3 及以上权限。"""
    stmt = select(PriceGuide)
    if category:
        stmt = stmt.where(PriceGuide.category == category)
    stmt = stmt.order_by(PriceGuide.category, PriceGuide.name)

    result = await db.execute(stmt)
    guides = result.scalars().all()

    return ApiResponse(code=200, message="查询成功", data={
        "total": len(guides),
        "price_guides": [{
            "id": g.id, "category": str(g.category), "name": g.name,
            "description": g.description,
            "price_min": g.price_min, "price_max": g.price_max,
            "unit": g.unit, "is_active": g.is_active,
            "created_at": g.created_at.isoformat() if g.created_at else None,
        } for g in guides],
    })


@router.post("/price-guides", response_model=ApiResponse)
async def create_price_guide(
    req: PriceGuideRequest,
    current_user=Depends(require_admin_l3),
    db: AsyncSession = Depends(get_db),
):
    """新增定价条目 — L3 及以上权限。"""
    guide = PriceGuide(
        category=req.category,
        name=req.name,
        description=req.description,
        price_min=req.price_min,
        price_max=req.price_max,
        unit=req.unit,
        is_active=req.is_active,
    )
    db.add(guide)
    await db.commit()
    await db.refresh(guide)

    return ApiResponse(code=201, message="定价条目已创建", data={"id": guide.id, "name": guide.name})


@router.put("/price-guides/{guide_id}", response_model=ApiResponse)
async def update_price_guide(
    guide_id: int,
    req: PriceGuideRequest,
    current_user=Depends(require_admin_l3),
    db: AsyncSession = Depends(get_db),
):
    """编辑定价条目 — L3 及以上权限。"""
    result = await db.execute(select(PriceGuide).where(PriceGuide.id == guide_id))
    guide = result.scalar_one_or_none()
    if guide is None:
        raise HTTPException(status_code=404, detail="定价条目不存在")

    guide.category = req.category
    guide.name = req.name
    guide.description = req.description
    guide.price_min = req.price_min
    guide.price_max = req.price_max
    guide.unit = req.unit
    guide.is_active = req.is_active
    await db.commit()
    await db.refresh(guide)

    return ApiResponse(code=200, message="定价条目已更新", data={"id": guide.id, "name": guide.name})


@router.delete("/price-guides/{guide_id}", response_model=ApiResponse)
async def delete_price_guide(
    guide_id: int,
    current_user=Depends(require_admin_l3),
    db: AsyncSession = Depends(get_db),
):
    """删除定价条目 — L3 及以上权限。"""
    result = await db.execute(select(PriceGuide).where(PriceGuide.id == guide_id))
    guide = result.scalar_one_or_none()
    if guide is None:
        raise HTTPException(status_code=404, detail="定价条目不存在")

    await db.delete(guide)
    await db.commit()

    return ApiResponse(code=200, message="定价条目已删除", data={"id": guide_id})
