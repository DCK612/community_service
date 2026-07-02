"""
订单模型 — 订单全生命周期管理。

状态流转：
PENDING -> ACCEPTED -> IN_PROGRESS -> WAITING_CONFIRM -> WAITING_REVIEW -> COMPLETED

每个状态变更自动记录时间戳，支持超时检测和计时统计。
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.database import Base


# ==================== 枚举定义 ====================

class OrderStatus(str, enum.Enum):
    """订单状态枚举 — 严格单向流转。"""
    PENDING = "PENDING"                    # 待接单（居民已发布）
    ACCEPTED = "ACCEPTED"                  # 已接单（服务者已接单，待开始服务）
    IN_PROGRESS = "IN_PROGRESS"            # 服务中（服务者已开始服务）
    WAITING_CONFIRM = "WAITING_CONFIRM"    # 待确认（服务者已完成，居民确认）
    WAITING_REVIEW = "WAITING_REVIEW"      # 待评价（居民已确认，待双方互评）
    COMPLETED = "COMPLETED"                # 已完成（双方已评价，订单归档）
    CANCELLED = "CANCELLED"                # 已取消（超时或被取消）


class OrderCategory(str, enum.Enum):
    """订单服务类别枚举。"""
    REPAIR = "REPAIR"          # 维修
    CLEANING = "CLEANING"      # 保洁
    MOVING = "MOVING"          # 搬家
    TUTORING = "TUTORING"      # 家教
    ELDERLY_CARE = "ELDERLY_CARE"  # 养老
    OTHER = "OTHER"            # 其他


# ==================== ORM 模型 ====================

class Order(Base):
    """订单表 — 记录完整的订单生命周期。

    包含 8 个时间戳字段，记录订单每个状态变更的精确时间：
    - created_at: 居民下单时间
    - accepted_at: 服务者接单时间
    - service_started_at: 服务开始时间
    - service_ended_at: 服务结束时间（服务者标记完成）
    - confirmed_at: 居民确认完成时间
    - reviewed_by_resident_at: 居民评价时间
    - reviewed_by_provider_at: 服务者评价时间
    - completed_at: 订单归档时间（双方评价完毕）
    """

    __tablename__ = "order"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 订单编号（唯一，格式: CS + 时间戳 + 随机数）
    order_no: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True, comment="订单编号"
    )
    # 订单状态
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus), default=OrderStatus.PENDING,
        nullable=False, index=True, comment="订单状态"
    )
    # 服务类别
    category: Mapped[OrderCategory] = mapped_column(
        Enum(OrderCategory), nullable=False, comment="服务类别"
    )
    # 居民用户ID（下单方）
    resident_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_base.id"), nullable=False, index=True,
        comment="居民用户ID"
    )
    # 服务者用户ID（接单方，接单前为空）
    provider_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user_base.id"), nullable=True, index=True,
        comment="服务者用户ID"
    )
    # 订单标题
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="订单标题"
    )
    # 订单描述
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="订单描述"
    )
    # 服务地址
    address: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="服务地址"
    )
    # 地址纬度
    latitude: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="地址纬度"
    )
    # 地址经度
    longitude: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="地址经度"
    )
    # 订单金额（居民出价，元）
    amount: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="订单金额（居民出价）"
    )
    # 预付款金额（amount * 50%）
    prepaid_amount: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="预付款金额"
    )
    # 预付款状态
    prepaid_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="UNPAID", comment="预付款状态: UNPAID/PAID"
    )
    # 平台抽成比例（默认 3%）
    platform_fee_rate: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.03, comment="平台抽成比例"
    )
    # 平台抽成金额（结算时计算，amount * 3%）
    platform_fee: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="平台抽成金额"
    )
    # 服务者结算金额（amount - platform_fee）
    settlement_amount: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="服务者结算金额"
    )
    # ========== 时间戳字段（全生命周期计时） ==========
    # 居民下单时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="下单时间"
    )
    # 服务者接单时间
    accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="接单时间"
    )
    # 服务开始时间（服务者点击"开始服务"）
    service_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="服务开始时间"
    )
    # 服务结束时间（服务者点击"完成服务"）
    service_ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="服务完成时间"
    )
    # 居民确认时间
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="居民确认时间"
    )
    # 居民评价时间
    reviewed_by_resident_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="居民评价时间"
    )
    # 服务者评价时间
    reviewed_by_provider_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="服务者评价时间"
    )
    # 订单归档时间（双方评价完成）
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="完成归档时间"
    )
    # 取消时间
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="取消时间"
    )
    # 是否超时（服务者在各阶段是否超时）
    is_timeout: Mapped[bool] = mapped_column(
        default=False, nullable=False, comment="是否超时"
    )
    # 超时阶段记录（accept/start/finish，逗号分隔）
    timeout_stages: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="超时阶段记录"
    )

    # 关联
    resident: Mapped["UserBase"] = relationship(
        "UserBase", foreign_keys=[resident_id], lazy="selectin"
    )
    provider: Mapped[Optional["UserBase"]] = relationship(
        "UserBase", foreign_keys=[provider_id], lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<Order(id={self.id}, order_no={self.order_no}, "
            f"status={self.status.value})>"
        )
