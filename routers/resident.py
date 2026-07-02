"""
居民端路由 — 注册、下单、查单、确认完成、评价、支付。

统一响应格式：{"code": int, "message": str, "data": Any}
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import get_db
from models.order import Order
from models.user import UserBase
from repository.order_repo import order_repo
from repository.user_repo import user_repo
from service.order_service import (
    cancel_order,
    confirm_order as service_confirm_order,
    create_order as service_create_order,
)
from service.review_service import create_resident_review
from service.payment_service import validate_price, calculate_prepaid

router = APIRouter(prefix="/resident", tags=["居民端"])


# ==================== 请求 / 响应模型 (Pydantic v2) ====================

class ResidentRegisterRequest(BaseModel):
    """居民注册请求。"""
    phone: str = Field(..., min_length=11, max_length=11, description="手机号")
    nickname: str = Field(..., min_length=1, max_length=50, description="昵称")
    address: Optional[str] = Field(default=None, description="地址")
    latitude: Optional[float] = Field(default=None, description="纬度")
    longitude: Optional[float] = Field(default=None, description="经度")


class CreateOrderRequest(BaseModel):
    """下单请求。"""
    resident_id: int = Field(..., description="居民 ID")
    category: str = Field(..., description="服务类别: REPAIR/CLEANING/MOVING/TUTORING/ELDERLY_CARE/OTHER")
    description: str = Field(..., max_length=500, description="需求描述")
    address: str = Field(..., max_length=200, description="服务地址")
    total_price: float = Field(..., gt=0, description="订单总价（元）")
    latitude: Optional[float] = Field(default=None, description="地址纬度")
    longitude: Optional[float] = Field(default=None, description="地址经度")
    expected_time: Optional[str] = Field(default=None, description="期望服务时间")


class ConfirmOrderRequest(BaseModel):
    """确认完成请求。"""
    resident_id: int = Field(..., description="居民 ID")


class ResidentReviewRequest(BaseModel):
    """居民评价请求。"""
    resident_id: int = Field(..., description="居民 ID")
    attitude: int = Field(..., ge=1, le=5, description="服务态度 1-5")
    professionalism: int = Field(..., ge=1, le=5, description="专业程度 1-5")
    punctuality: int = Field(..., ge=1, le=5, description="守时情况 1-5")
    cost: int = Field(..., ge=1, le=5, description="收费合理性 1-5")
    after_sale: int = Field(..., ge=1, le=5, description="售后保障 1-5")
    comment: Optional[str] = Field(default=None, description="文字评价")


class ApiResponse(BaseModel):
    """统一 API 响应。"""
    code: int = Field(default=200, description="状态码，200 成功")
    message: str = Field(default="成功", description="响应消息")
    data: Any = Field(default=None, description="响应数据")


# ==================== 居民注册 ====================

@router.post("/register", response_model=ApiResponse)
async def resident_register(
    req: ResidentRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """注册居民账号。

    手机号唯一，重复注册返回已存在账号。
    """
    # 检查手机号是否已注册
    existing = await user_repo.get_by_phone(db, req.phone)
    if existing:
        return ApiResponse(
            code=200,
            message="手机号已注册，返回已有账号",
            data={
                "user_id": existing.id,
                "nickname": existing.nickname,
                "role": existing.role.value,
            },
        )

    user = await user_repo.create_resident(
        db,
        phone=req.phone,
        nickname=req.nickname,
        address=req.address,
        latitude=req.latitude,
        longitude=req.longitude,
    )

    return ApiResponse(
        code=201,
        message="居民注册成功",
        data={
            "user_id": user.id,
            "nickname": user.nickname,
            "role": user.role.value,
        },
    )


# ==================== 下单 ====================

@router.post("/orders", response_model=ApiResponse)
async def create_order(
    req: CreateOrderRequest,
    db: AsyncSession = Depends(get_db),
):
    """居民下单。

    校验出价不低于定价参考最低价 → 计算预付50% → 创建订单（prepaid_status=UNPAID）。
    """
    # 1. 校验最低价
    try:
        await validate_price(db, req.total_price, req.category)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. 计算预付金额和平台费率
    prepaid_amount = calculate_prepaid(req.total_price)
    platform_fee_rate = 0.03

    # 3. 创建订单
    order = await service_create_order(
        db,
        resident_id=req.resident_id,
        category=req.category,
        description=req.description,
        address=req.address,
        amount=req.total_price,
        latitude=req.latitude,
        longitude=req.longitude,
    )

    # 4. 设置支付相关字段
    order.prepaid_amount = prepaid_amount
    order.prepaid_status = "UNPAID"
    order.platform_fee_rate = platform_fee_rate
    await db.commit()
    await db.refresh(order)

    return ApiResponse(
        code=201,
        message="下单成功，请支付预付",
        data={
            "order_id": order.id,
            "order_no": order.order_no,
            "status": order.status.value,
            "total_price": req.total_price,
            "prepaid_amount": prepaid_amount,
            "prepaid_status": order.prepaid_status,
        },
    )


# ==================== 支付预付 ====================

@router.post("/orders/{order_id}/pay", response_model=ApiResponse)
async def pay_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
):
    """模拟支付预付（设置 prepaid_status=PAID）。

    支付后订单进入待抢单池，服务者可通过 GET /provider/orders/available 查看。
    """
    order = await order_repo.get_by_id(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.prepaid_status == "PAID":
        raise HTTPException(status_code=400, detail="订单已支付，无需重复支付")

    order.prepaid_status = "PAID"
    await db.commit()
    await db.refresh(order)

    return ApiResponse(
        code=200,
        message="预付支付成功，订单已进入抢单池",
        data={
            "order_id": order.id,
            "order_no": order.order_no,
            "prepaid_amount": order.prepaid_amount,
            "prepaid_status": order.prepaid_status,
        },
    )


# ==================== 查单 ====================

@router.get("/orders", response_model=ApiResponse)
async def get_resident_orders(
    resident_id: int,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """查询居民的全部订单。

    Args:
        resident_id: 居民 ID（必填）。
        status: 按状态筛选（可选）。
        page: 页码。
        page_size: 每页条数。
    """
    orders, total = await order_repo.get_by_resident(
        db,
        resident_id=resident_id,
        status=status,
        offset=(page - 1) * page_size,
        limit=page_size,
    )

    return ApiResponse(
        code=200,
        message="查询成功",
        data={
            "total": total,
            "page": page,
            "page_size": page_size,
            "orders": [
                {
                    "id": o.id,
                    "order_no": o.order_no,
                    "category": o.category,
                    "description": o.description,
                    "address": o.address,
                    "status": o.status.value,
                    "price": o.price,
                    "provider_id": o.provider_id,
                    "created_at": o.created_at.isoformat() if o.created_at else None,
                    "accepted_at": o.accepted_at.isoformat() if o.accepted_at else None,
                    "service_started_at": o.service_started_at.isoformat() if o.service_started_at else None,
                    "service_ended_at": o.service_ended_at.isoformat() if o.service_ended_at else None,
                }
                for o in orders
            ],
        },
    )


# ==================== 确认完成 ====================

@router.post("/orders/{order_id}/confirm", response_model=ApiResponse)
async def confirm_order(
    order_id: int,
    req: ConfirmOrderRequest,
    db: AsyncSession = Depends(get_db),
):
    """居民确认服务完成。

    订单状态从 WAITING_CONFIRM 变为 WAITING_REVIEW。
    """
    order = await order_repo.get_by_id(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")

    await service_confirm_order(db, order, req.resident_id)

    return ApiResponse(
        code=200,
        message="确认完成成功，请评价",
        data={"order_id": order_id, "status": order.status.value},
    )


# ==================== 评价 ====================

@router.post("/reviews", response_model=ApiResponse)
async def resident_review(
    req: ResidentReviewRequest,
    order_id: int,
    db: AsyncSession = Depends(get_db),
):
    """居民评价服务者。

    评分维度：服务态度、专业程度、守时情况、收费合理性、售后保障（1-5分）。
    """
    order = await order_repo.get_by_id(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")

    review = await create_resident_review(
        db,
        order=order,
        resident_id=req.resident_id,
        attitude=req.attitude,
        professionalism=req.professionalism,
        punctuality=req.punctuality,
        cost=req.cost,
        after_sale=req.after_sale,
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
