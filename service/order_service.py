"""
订单服务 — 订单创建与全生命周期状态流转。

每个状态变更自动记录对应时间戳，遵循严格单向流转规则：
PENDING -> ACCEPTED -> IN_PROGRESS -> WAITING_CONFIRM -> WAITING_REVIEW -> COMPLETED
"""

import random
import string
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from models.order import Order, OrderCategory, OrderStatus
from models.user import ProviderProfile, ProviderStatus, UserBase
from repository.order_repo import order_repo
from repository.user_repo import user_repo


# ==================== 订单编号生成 ====================

def _generate_order_no() -> str:
    """生成唯一订单编号：CS + 时间戳 + 4位随机字符。

    Returns:
        格式为 CS20260702A3B7 的订单编号。
    """
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_part = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"CS{timestamp}{random_part}"


# ==================== 订单创建 ====================

async def create_order(
    db: AsyncSession,
    resident_id: int,
    title: str,
    category: OrderCategory,
    address: str,
    description: Optional[str] = None,
    amount: Optional[float] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> Order:
    """居民创建新订单。

    Args:
        db: 异步数据库会话。
        resident_id: 居民用户 ID。
        title: 订单标题。
        category: 服务类别。
        address: 服务地址。
        description: 订单描述。
        amount: 订单金额。
        latitude: 地址纬度。
        longitude: 地址经度。

    Returns:
        新创建的 Order 对象。

    Raises:
        ValueError: 用户不存在或不是居民角色。
    """
    # 校验居民身份
    resident = await user_repo.get_by_id(db, resident_id)
    if resident is None:
        raise ValueError(f"居民用户不存在: {resident_id}")
    if resident.role.value != "RESIDENT":
        raise ValueError(f"用户 {resident_id} 不是居民角色")

    # 构建订单对象
    order = Order(
        order_no=_generate_order_no(),
        resident_id=resident_id,
        title=title,
        category=category,
        address=address,
        description=description,
        amount=amount,
        latitude=latitude,
        longitude=longitude,
        status=OrderStatus.PENDING,
    )
    return await order_repo.create(db, order)


# ==================== 订单状态流转 ====================

async def accept_order(
    db: AsyncSession,
    order: Order,
    provider: UserBase,
) -> Order:
    """服务者接单：PENDING -> ACCEPTED。

    校验项：
    - 订单必须为 PENDING 状态
    - 服务者必须在线且未被拉黑
    - 接单后服务者在途订单数 +1

    Args:
        db: 异步数据库会话。
        order: 订单对象。
        provider: 服务者 UserBase 对象。

    Returns:
        更新后的 Order 对象。

    Raises:
        ValueError: 状态校验失败。
    """
    if order.status != OrderStatus.PENDING:
        raise ValueError(f"订单 {order.order_no} 当前状态为 {order.status.value}，无法接单")

    profile = provider.provider_profile
    if profile is None:
        raise ValueError(f"用户 {provider.id} 不是服务者角色")
    if profile.blacklisted:
        raise ValueError(f"服务者 {provider.nickname} 已被拉黑，无法接单")
    if profile.status != ProviderStatus.ONLINE:
        raise ValueError(f"服务者 {provider.nickname} 当前不在线")

    # 更新订单
    order.provider_id = provider.id
    order = await order_repo.update_status(db, order, OrderStatus.ACCEPTED)

    # 在途订单数 +1
    profile.ongoing_orders_count += 1
    await db.commit()

    return order


async def start_service(
    db: AsyncSession,
    order: Order,
    provider_id: int,
) -> Order:
    """服务者开始服务：ACCEPTED -> IN_PROGRESS。

    Args:
        db: 异步数据库会话。
        order: 订单对象。
        provider_id: 服务者 ID（用于鉴权）。

    Returns:
        更新后的 Order 对象。
    """
    if order.status != OrderStatus.ACCEPTED:
        raise ValueError(f"订单 {order.order_no} 当前状态为 {order.status.value}，无法开始服务")
    if order.provider_id != provider_id:
        raise ValueError("只有接单的服务者才能开始服务")

    return await order_repo.update_status(db, order, OrderStatus.IN_PROGRESS)


async def finish_service(
    db: AsyncSession,
    order: Order,
    provider_id: int,
) -> Order:
    """服务者完成服务：IN_PROGRESS -> WAITING_CONFIRM。

    Args:
        db: 异步数据库会话。
        order: 订单对象。
        provider_id: 服务者 ID。

    Returns:
        更新后的 Order 对象。
    """
    if order.status != OrderStatus.IN_PROGRESS:
        raise ValueError(f"订单 {order.order_no} 当前状态为 {order.status.value}，无法完成服务")
    if order.provider_id != provider_id:
        raise ValueError("只有接单的服务者才能完成服务")

    order = await order_repo.update_status(db, order, OrderStatus.WAITING_CONFIRM)

    # 在途订单数 -1
    profile = await user_repo.get_provider_profile(db, provider_id)
    if profile and profile.ongoing_orders_count > 0:
        profile.ongoing_orders_count -= 1
        await db.commit()

    return order


async def confirm_order(
    db: AsyncSession,
    order: Order,
    resident_id: int,
) -> Order:
    """居民确认完成：WAITING_CONFIRM -> WAITING_REVIEW。

    Args:
        db: 异步数据库会话。
        order: 订单对象。
        resident_id: 居民 ID。

    Returns:
        更新后的 Order 对象。
    """
    if order.status != OrderStatus.WAITING_CONFIRM:
        raise ValueError(f"订单 {order.order_no} 当前状态为 {order.status.value}，无法确认")
    if order.resident_id != resident_id:
        raise ValueError("只有下单居民才能确认完成")

    return await order_repo.update_status(db, order, OrderStatus.WAITING_REVIEW)


async def complete_order(
    db: AsyncSession,
    order: Order,
) -> Order:
    """订单归档：WAITING_REVIEW -> COMPLETED（双方评价完毕后调用）。

    Args:
        db: 异步数据库会话。
        order: 订单对象。

    Returns:
        更新后的 Order 对象。
    """
    if order.status != OrderStatus.WAITING_REVIEW:
        raise ValueError(f"订单 {order.order_no} 当前状态为 {order.status.value}，无法归档")

    return await order_repo.update_status(db, order, OrderStatus.COMPLETED)


async def cancel_order(
    db: AsyncSession,
    order: Order,
    reason: str = "用户取消",
) -> Order:
    """取消订单：任意非终态 -> CANCELLED。

    终态（COMPLETED / CANCELLED）不可取消。

    Args:
        db: 异步数据库会话。
        order: 订单对象。
        reason: 取消原因。

    Returns:
        更新后的 Order 对象。
    """
    if order.status in (OrderStatus.COMPLETED, OrderStatus.CANCELLED):
        raise ValueError(f"订单 {order.order_no} 已处于终态，无法取消")

    return await order_repo.update_status(db, order, OrderStatus.CANCELLED)


async def mark_order_timeout(
    db: AsyncSession,
    order: Order,
    stage: str,
) -> Order:
    """标记订单超时。

    Args:
        db: 异步数据库会话。
        order: 订单对象。
        stage: 超时阶段（accept / start / finish / confirm）。

    Returns:
        更新后的 Order 对象。
    """
    order.is_timeout = True

    # 记录超时阶段
    if order.timeout_stages:
        existing = set(order.timeout_stages.split(","))
        existing.add(stage)
        order.timeout_stages = ",".join(sorted(existing))
    else:
        order.timeout_stages = stage

    await db.commit()
    await db.refresh(order)
    return order
