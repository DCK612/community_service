"""
服务者端路由 — 状态切换、抢单大厅、开始/结束服务、信用分查询、评价居民。
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import get_db
from models.user import ProviderStatus
from repository.order_repo import order_repo
from repository.user_repo import user_repo
from service.dispatch_service import get_nearby_orders
from service.order_service import (
    accept_order as service_accept_order,
    finish_service as service_finish_order,
    start_service as service_start_order,
)
from service.review_service import (
    create_provider_review,
    get_provider_score_detail,
)

router = APIRouter(prefix="/provider", tags=["服务者端"])


# ==================== 请求模型 ====================

class ProviderStatusRequest(BaseModel):
    """服务者状态切换请求。"""
    provider_id: int = Field(..., description="服务者 ID")
    status: str = Field(..., description="状态: ONLINE / OFFLINE / BUSY")


class GrabOrderRequest(BaseModel):
    """抢单请求。"""
    provider_id: int = Field(..., description="服务者 ID")
    latitude: float = Field(..., description="服务者当前纬度")
    longitude: float = Field(..., description="服务者当前经度")


class StartServiceRequest(BaseModel):
    """开始服务请求。"""
    provider_id: int = Field(..., description="服务者 ID")


class FinishServiceRequest(BaseModel):
    """完成服务请求。"""
    provider_id: int = Field(..., description="服务者 ID")


class ProviderReviewRequest(BaseModel):
    """服务者评价居民请求。"""
    provider_id: int = Field(..., description="服务者 ID")
    accuracy: int = Field(..., ge=1, le=5, description="需求准确度 1-5")
    cooperation: int = Field(..., ge=1, le=5, description="配合度 1-5")
    payment: int = Field(..., ge=1, le=5, description="付款及时性 1-5")
    comment: Optional[str] = Field(default=None, description="文字评价")


class ApiResponse(BaseModel):
    """统一 API 响应。"""
    code: int = Field(default=200)
    message: str = Field(default="成功")
    data: Optional[object] = Field(default=None)


# ==================== 状态切换 ====================

@router.put("/status", response_model=ApiResponse)
async def update_provider_status(
    req: ProviderStatusRequest,
    db: AsyncSession = Depends(get_db),
):
    """服务者切换在线状态。

    支持 ONLINE（可接单）/ OFFLINE（下线）/ BUSY（繁忙）三种状态。
    """
    status_map = {
        "ONLINE": ProviderStatus.ONLINE,
        "OFFLINE": ProviderStatus.OFFLINE,
        "BUSY": ProviderStatus.BUSY,
    }

    new_status = status_map.get(req.status.upper())
    if new_status is None:
        raise HTTPException(
            status_code=400,
            detail=f"无效状态: {req.status}，可选: {list(status_map.keys())}",
        )

    provider = await user_repo.get_by_id(db, req.provider_id)
    if provider is None or provider.provider_profile is None:
        raise HTTPException(status_code=404, detail="服务者不存在")

    provider.provider_profile.status = new_status
    await db.commit()

    return ApiResponse(
        code=200,
        message=f"状态已切换为 {req.status.upper()}",
        data={"provider_id": req.provider_id, "status": req.status.upper()},
    )


# ==================== 抢单大厅（附近订单池） ====================

@router.post("/orders/available", response_model=ApiResponse)
async def get_available_orders(
    req: GrabOrderRequest,
    db: AsyncSession = Depends(get_db),
):
    """获取附近待抢订单池。

    返回 PENDING 且 prepaid_status=PAID 的订单，按服务者距离升序排列。
    同时更新服务者当前位置坐标。
    """
    # 更新服务者位置
    provider = await user_repo.get_by_id(db, req.provider_id)
    if provider is None or provider.provider_profile is None:
        raise HTTPException(status_code=404, detail="服务者不存在")

    profile = provider.provider_profile
    profile.latitude = req.latitude
    profile.longitude = req.longitude
    await db.commit()

    # 获取附近订单
    nearby = await get_nearby_orders(
        db,
        provider_id=req.provider_id,
        provider_lat=req.latitude,
        provider_lon=req.longitude,
    )

    return ApiResponse(
        code=200,
        message="查询成功",
        data={
            "total": len(nearby),
            "orders": [
                {
                    "order_id": o.id,
                    "order_no": o.order_no,
                    "category": o.category,
                    "description": o.description,
                    "address": o.address,
                    "total_price": o.amount,
                    "prepaid_amount": o.prepaid_amount,
                    "prepaid_status": o.prepaid_status,
                    "distance_km": dist,
                    "created_at": o.created_at.isoformat() if o.created_at else None,
                }
                for o, dist in nearby
            ],
        },
    )


# ==================== 抢单（原子操作，先到先得） ====================

@router.post("/orders/{order_id}/grab", response_model=ApiResponse)
async def grab_order(
    order_id: int,
    req: GrabOrderRequest,
    db: AsyncSession = Depends(get_db),
):
    """抢单 — 原子操作，先到先得。

    校验：订单 PENDING + prepaid_status=PAID → 原子更新为 ACCEPTED。
    """
    order = await order_repo.get_by_id(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")

    if order.status.value != "PENDING":
        raise HTTPException(status_code=400, detail=f"订单状态为 {order.status.value}，无法抢单")

    if order.prepaid_status != "PAID":
        raise HTTPException(status_code=400, detail="该订单尚未支付预付，无法抢单")

    # 原子抢单：利用唯一约束 provider_id 为 None 时才可更新
    # 此处直接调用 accept_order，由 service 层做并发安全校验
    await service_accept_order(db, order, req.provider_id)

    return ApiResponse(
        code=200,
        message="抢单成功！",
        data={"order_id": order_id, "order_no": order.order_no, "status": order.status.value},
    )


# ==================== 开始服务 ====================

@router.post("/orders/{order_id}/start", response_model=ApiResponse)
async def start_service(
    order_id: int,
    req: StartServiceRequest,
    db: AsyncSession = Depends(get_db),
):
    """服务者开始服务。

    订单状态从 ACCEPTED → IN_PROGRESS，记录 service_started_at。
    """
    order = await order_repo.get_by_id(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")

    await service_start_order(db, order, req.provider_id)

    return ApiResponse(
        code=200,
        message="已开始服务",
        data={"order_id": order_id, "status": order.status.value},
    )


# ==================== 完成服务 ====================

@router.post("/orders/{order_id}/finish", response_model=ApiResponse)
async def finish_service(
    order_id: int,
    req: FinishServiceRequest,
    db: AsyncSession = Depends(get_db),
):
    """服务者完成服务。

    订单状态从 IN_PROGRESS → WAITING_CONFIRM，记录 service_ended_at。
    """
    order = await order_repo.get_by_id(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")

    await service_finish_order(db, order, req.provider_id)

    return ApiResponse(
        code=200,
        message="服务已完成，等待居民确认",
        data={"order_id": order_id, "status": order.status.value},
    )


# ==================== 信用分查询 ====================

@router.get("/profile/score", response_model=ApiResponse)
async def get_provider_score(
    provider_id: int = Query(..., description="服务者 ID"),
    db: AsyncSession = Depends(get_db),
):
    """查询服务者信用分明细。"""
    detail = await get_provider_score_detail(db, provider_id)

    return ApiResponse(
        code=200,
        message="查询成功",
        data=detail,
    )


# ==================== 评价居民 ====================

@router.post("/reviews", response_model=ApiResponse)
async def provider_review(
    req: ProviderReviewRequest,
    order_id: int = Query(..., description="订单 ID"),
    db: AsyncSession = Depends(get_db),
):
    """服务者评价居民。

    评分维度：需求准确度、配合度、付款及时性（1-5分）。
    """
    order = await order_repo.get_by_id(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")

    review = await create_provider_review(
        db,
        order=order,
        provider_id=req.provider_id,
        accuracy=req.accuracy,
        cooperation=req.cooperation,
        payment=req.payment,
        comment=req.comment,
    )

    return ApiResponse(
        code=201,
        message="评价成功",
        data={
            "review_id": review.id,
            "avg_score": review.avg_score,
            "order_id": order_id,
        },
    )
