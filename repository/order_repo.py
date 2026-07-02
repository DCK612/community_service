"""
订单 Repository — 订单数据访问层。

提供订单全生命周期的数据库操作：创建、状态流转、查询等。
"""

from datetime import datetime, timedelta
from typing import List, Optional, Sequence

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from models.order import Order, OrderStatus
from repository.base import BaseRepository


class OrderRepository(BaseRepository[Order]):
    """订单 Repository。"""

    def __init__(self) -> None:
        """初始化，绑定 Order 模型。"""
        super().__init__(Order)

    async def get_by_order_no(
        self, db: AsyncSession, order_no: str
    ) -> Optional[Order]:
        """按订单编号查询订单。

        Args:
            db: 异步数据库会话。
            order_no: 订单编号。

        Returns:
            匹配的 Order 对象，不存在返回 None。
        """
        result = await db.execute(
            select(Order).where(Order.order_no == order_no)
        )
        return result.scalar_one_or_none()

    async def get_by_resident(
        self,
        db: AsyncSession,
        resident_id: int,
        status: Optional[OrderStatus] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[Order]:
        """查询居民的订单列表。

        Args:
            db: 异步数据库会话。
            resident_id: 居民用户 ID。
            status: 可选的状态过滤。
            offset: 偏移量。
            limit: 每页数量。

        Returns:
            订单列表（按创建时间倒序）。
        """
        stmt = (
            select(Order)
            .where(Order.resident_id == resident_id)
        )
        if status is not None:
            stmt = stmt.where(Order.status == status)
        stmt = stmt.order_by(Order.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_by_provider(
        self,
        db: AsyncSession,
        provider_id: int,
        status: Optional[OrderStatus] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[Order]:
        """查询服务者的订单列表。

        Args:
            db: 异步数据库会话。
            provider_id: 服务者用户 ID。
            status: 可选的状态过滤。
            offset: 偏移量。
            limit: 每页数量。

        Returns:
            订单列表（按创建时间倒序）。
        """
        stmt = (
            select(Order)
            .where(Order.provider_id == provider_id)
        )
        if status is not None:
            stmt = stmt.where(Order.status == status)
        stmt = stmt.order_by(Order.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_pending_orders(
        self,
        db: AsyncSession,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Order]:
        """查询所有待接单订单（PENDING 状态）。

        Returns:
            待接单订单列表。
        """
        result = await db.execute(
            select(Order)
            .where(Order.status == OrderStatus.PENDING)
            .order_by(Order.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        return result.scalars().all()

    async def count_ongoing_by_provider(
        self, db: AsyncSession, provider_id: int
    ) -> int:
        """统计服务者在途订单数（已接单但未完成）。

        Args:
            db: 异步数据库会话。
            provider_id: 服务者用户 ID。

        Returns:
            在途订单数。
        """
        result = await db.execute(
            select(func.count(Order.id))
            .where(
                Order.provider_id == provider_id,
                Order.status.in_([
                    OrderStatus.ACCEPTED,
                    OrderStatus.IN_PROGRESS,
                ]),
            )
        )
        return result.scalar() or 0

    async def get_timeout_orders(
        self,
        db: AsyncSession,
        provider_id: int,
        window_days: int,
    ) -> Sequence[Order]:
        """查询服务者在指定时间窗口内的超时订单。

        Args:
            db: 异步数据库会话。
            provider_id: 服务者用户 ID。
            window_days: 时间窗口（天）。

        Returns:
            超时订单列表。
        """
        cutoff = datetime.now() - timedelta(days=window_days)
        result = await db.execute(
            select(Order)
            .where(
                Order.provider_id == provider_id,
                Order.is_timeout == True,
                Order.created_at >= cutoff,
            )
        )
        return result.scalars().all()

    async def update_status(
        self,
        db: AsyncSession,
        order: Order,
        new_status: OrderStatus,
    ) -> Order:
        """更新订单状态并打对应时间戳。

        Args:
            db: 异步数据库会话。
            order: 要更新的订单对象。
            new_status: 新状态。

        Returns:
            更新后的订单对象。
        """
        now = datetime.now()
        order.status = new_status

        # 根据新状态自动打时间戳
        status_timestamp_map = {
            OrderStatus.ACCEPTED: "accepted_at",
            OrderStatus.IN_PROGRESS: "service_started_at",
            OrderStatus.WAITING_CONFIRM: "service_ended_at",
            OrderStatus.WAITING_REVIEW: "confirmed_at",
            OrderStatus.COMPLETED: "completed_at",
            OrderStatus.CANCELLED: "cancelled_at",
        }
        field_name = status_timestamp_map.get(new_status)
        if field_name and hasattr(order, field_name):
            setattr(order, field_name, now)

        await db.commit()
        await db.refresh(order)
        return order


# 单例
order_repo = OrderRepository()
