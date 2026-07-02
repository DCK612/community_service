"""
管理端路由 — 仪表盘、黑名单管理、拉黑操作。
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import get_db
from repository.user_repo import user_repo
from service.blacklist_service import (
    check_and_auto_blacklist,
    get_blacklist_detail,
    scan_all_providers,
)

router = APIRouter(prefix="/admin", tags=["管理端"])


# ==================== 请求模型 ====================

class BlacklistRequest(BaseModel):
    """手动拉黑请求。"""
    provider_id: int = Field(..., description="服务者 ID")
    blacklist_type: str = Field(
        default="permanent",
        description="拉黑类型: permanent(永久) / temporary(临时)",
    )
    reason: Optional[str] = Field(default=None, description="拉黑原因")
    freeze_days: int = Field(default=7, ge=1, le=365, description="冻结天数（临时拉黑时有效）")


class ApiResponse(BaseModel):
    """统一 API 响应。"""
    code: int = Field(default=200)
    message: str = Field(default="成功")
    data: Optional[object] = Field(default=None)


# ==================== 仪表盘 ====================

@router.get("/dashboard", response_model=ApiResponse)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
):
    """管理端仪表盘 — 核心运营数据。

    包含：注册用户统计、订单统计、黑名单统计等。
    """
    from sqlalchemy import func, select

    from models.order import Order, OrderStatus
    from models.review import Review
    from models.user import UserRole, UserBase

    # 用户统计
    resident_count_result = await db.execute(
        select(func.count(UserBase.id)).where(UserBase.role == UserRole.RESIDENT)
    )
    resident_count = resident_count_result.scalar() or 0

    provider_count_result = await db.execute(
        select(func.count(UserBase.id)).where(UserBase.role == UserRole.PROVIDER)
    )
    provider_count = provider_count_result.scalar() or 0

    # 订单统计
    total_orders_result = await db.execute(select(func.count(Order.id)))
    total_orders = total_orders_result.scalar() or 0

    pending_result = await db.execute(
        select(func.count(Order.id)).where(Order.status == OrderStatus.PENDING)
    )
    pending_count = pending_result.scalar() or 0

    completed_result = await db.execute(
        select(func.count(Order.id)).where(Order.status == OrderStatus.COMPLETED)
    )
    completed_count = completed_result.scalar() or 0

    # 黑名单统计
    blacklist_result = await db.execute(
        select(func.count(UserBase.id))
        .join(UserBase.provider_profile)
        .where(UserBase.provider_profile.has(blacklisted=True))
    )
    blacklist_count = blacklist_result.scalar() or 0

    # 评价统计
    review_count_result = await db.execute(select(func.count(Review.id)))
    review_count = review_count_result.scalar() or 0

    return ApiResponse(
        code=200,
        message="查询成功",
        data={
            "users": {
                "residents": resident_count,
                "providers": provider_count,
                "total": resident_count + provider_count,
            },
            "orders": {
                "total": total_orders,
                "pending": pending_count,
                "completed": completed_count,
                "completion_rate": (
                    round(completed_count / total_orders * 100, 1)
                    if total_orders > 0 else 0
                ),
            },
            "reviews": {
                "total": review_count,
            },
            "blacklist": {
                "total": blacklist_count,
            },
        },
    )


# ==================== 黑名单列表 ====================

@router.get("/blacklist", response_model=ApiResponse)
async def get_blacklist(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
):
    """获取黑名单列表。"""
    details = await get_blacklist_detail(
        db,
        offset=(page - 1) * page_size,
        limit=page_size,
    )

    return ApiResponse(
        code=200,
        message="查询成功",
        data={
            "total": len(details),
            "page": page,
            "page_size": page_size,
            "blacklist": details,
        },
    )


# ==================== 手动拉黑 ====================

@router.post("/providers/{provider_id}/blacklist", response_model=ApiResponse)
async def blacklist_provider(
    provider_id: int,
    req: BlacklistRequest,
    db: AsyncSession = Depends(get_db),
):
    """手动将服务者加入黑名单。

    支持永久拉黑（permanent）和临时冻结（temporary）两种模式。
    """
    from repository.blacklist_repo import blacklist_repo

    provider = await user_repo.get_by_id(db, provider_id)
    if provider is None or provider.provider_profile is None:
        raise HTTPException(status_code=404, detail="服务者不存在")

    if req.blacklist_type not in ("permanent", "temporary"):
        raise HTTPException(
            status_code=400,
            detail="blacklist_type 必须为 permanent 或 temporary",
        )

    await blacklist_repo.add_to_blacklist(
        db,
        provider,
        blacklist_type=req.blacklist_type,
        freeze_days=req.freeze_days,
    )

    return ApiResponse(
        code=200,
        message=f"服务者 {provider_id} 已被{'永久拉黑' if req.blacklist_type == 'permanent' else '临时冻结' + str(req.freeze_days) + '天'}",
        data={
            "provider_id": provider_id,
            "blacklist_type": req.blacklist_type,
            "freeze_days": req.freeze_days if req.blacklist_type == "temporary" else None,
        },
    )


# ==================== 全局自动检查 ====================

@router.post("/scan-blacklist", response_model=ApiResponse)
async def scan_blacklist(
    db: AsyncSession = Depends(get_db),
):
    """触发全量扫描，自动拉黑违规服务者。

    检查信用分、投诉次数、超时次数等条件。
    """
    results = await scan_all_providers(db)

    return ApiResponse(
        code=200,
        message=f"扫描完成，新拉黑 {len(results)} 名服务者",
        data={"new_blacklisted": len(results), "details": results},
    )
