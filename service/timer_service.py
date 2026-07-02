"""
定时器服务 — 订单各阶段耗时计算与超时检测。

检查订单在各阶段的停留时间是否超过配置阈值：
- 待接单超时（PENDING 超过 ORDER_ACCEPT_TIMEOUT_MINUTES）
- 待开始超时（ACCEPTED 超过 ORDER_START_TIMEOUT_MINUTES）
- 服务超时（IN_PROGRESS 超过 ORDER_FINISH_TIMEOUT_MINUTES）
- 确认超时（WAITING_CONFIRM 超过 ORDER_CONFIRM_TIMEOUT_MINUTES）
"""

from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import config
from models.order import Order, OrderStatus
from repository.order_repo import order_repo
from service.order_service import mark_order_timeout


# ==================== 耗时计算 ====================

def calc_stage_duration(
    order: Order,
    stage: str,
) -> Optional[float]:
    """计算订单在指定阶段的耗时（分钟）。

    Args:
        order: 订单对象。
        stage: 阶段名称（accept / start / service / confirm / total）。

    Returns:
        耗时（分钟），若缺少起止时间戳则返回 None。
    """
    now = datetime.now()

    stage_configs = {
        "accept": (
            order.created_at,
            order.accepted_at or now,
            config.ORDER_ACCEPT_TIMEOUT_MINUTES,
            "待接单",
        ),
        "start": (
            order.accepted_at,
            order.service_started_at or now,
            config.ORDER_START_TIMEOUT_MINUTES,
            "待开始服务",
        ),
        "service": (
            order.service_started_at,
            order.service_ended_at or now,
            config.ORDER_FINISH_TIMEOUT_MINUTES,
            "服务中",
        ),
        "confirm": (
            order.service_ended_at,
            order.confirmed_at or now,
            config.ORDER_CONFIRM_TIMEOUT_MINUTES,
            "待确认",
        ),
    }

    config_entry = stage_configs.get(stage)
    if config_entry is None:
        return None

    start_time, end_time, timeout_minutes, display_name = config_entry
    if start_time is None:
        return None

    duration = (end_time - start_time).total_seconds() / 60
    return round(duration, 2)


def calc_total_duration(order: Order) -> Optional[float]:
    """计算订单总耗时（从创建到完成，分钟）。

    Args:
        order: 订单对象。

    Returns:
        总耗时（分钟）。
    """
    if order.completed_at:
        duration = (order.completed_at - order.created_at).total_seconds() / 60
        return round(duration, 2)

    if order.cancelled_at:
        duration = (order.cancelled_at - order.created_at).total_seconds() / 60
        return round(duration, 2)

    # 未完成的订单：计算到当前时间
    duration = (datetime.now() - order.created_at).total_seconds() / 60
    return round(duration, 2)


# ==================== 超时检测 ====================

def _is_stage_timeout(
    start_time: Optional[datetime],
    end_time: Optional[datetime],
    timeout_minutes: int,
) -> bool:
    """判断某个阶段是否超时。

    Args:
        start_time: 阶段开始时间。
        end_time: 阶段结束时间（None 表示进行中，用当前时间）。
        timeout_minutes: 超时阈值（分钟）。

    Returns:
        超时返回 True。
    """
    if start_time is None:
        return False

    end = end_time or datetime.now()
    duration = (end - start_time).total_seconds() / 60
    return duration > timeout_minutes


async def check_order_timeouts(
    db: AsyncSession,
    order: Order,
) -> List[Tuple[str, str]]:
    """检查订单各阶段是否超时，并标记。

    超时检查基于订单当前状态：
    - PENDING: 检查 accept 阶段
    - ACCEPTED: 检查 start 阶段
    - IN_PROGRESS: 检查 service 阶段
    - WAITING_CONFIRM: 检查 confirm 阶段

    Args:
        db: 异步数据库会话。
        order: 订单对象。

    Returns:
        超时的阶段列表 [(stage_key, description), ...]。
    """
    timeouts: List[Tuple[str, str]] = []

    # PENDING: 检查是否超过接单时限
    if order.status == OrderStatus.PENDING:
        if _is_stage_timeout(
            order.created_at, order.accepted_at,
            config.ORDER_ACCEPT_TIMEOUT_MINUTES,
        ):
            timeouts.append(("accept", "待接单超时"))

    # ACCEPTED: 检查是否超过开始服务时限
    elif order.status == OrderStatus.ACCEPTED:
        if _is_stage_timeout(
            order.accepted_at, order.service_started_at,
            config.ORDER_START_TIMEOUT_MINUTES,
        ):
            timeouts.append(("start", "待开始服务超时"))

    # IN_PROGRESS: 检查是否超过服务时限
    elif order.status == OrderStatus.IN_PROGRESS:
        if _is_stage_timeout(
            order.service_started_at, order.service_ended_at,
            config.ORDER_FINISH_TIMEOUT_MINUTES,
        ):
            timeouts.append(("finish", "服务超时"))

    # WAITING_CONFIRM: 检查是否超过确认时限
    elif order.status == OrderStatus.WAITING_CONFIRM:
        if _is_stage_timeout(
            order.service_ended_at, order.confirmed_at,
            config.ORDER_CONFIRM_TIMEOUT_MINUTES,
        ):
            timeouts.append(("confirm", "待确认超时"))

    # 标记超时
    for stage_key, desc in timeouts:
        await mark_order_timeout(db, order, stage_key)

    return timeouts


async def scan_all_active_orders(
    db: AsyncSession,
) -> dict:
    """扫描所有活跃订单（非终态），检测超时并标记。

    Returns:
        统计结果 {"checked": int, "timeouts_found": int, "details": [...]}
    """
    # 获取所有活跃订单
    result = await db.execute(
        select(Order).where(
            Order.status.in_([
                OrderStatus.PENDING,
                OrderStatus.ACCEPTED,
                OrderStatus.IN_PROGRESS,
                OrderStatus.WAITING_CONFIRM,
                OrderStatus.WAITING_REVIEW,
            ])
        )
    )
    active_orders = result.scalars().all()

    stats = {
        "checked": len(active_orders),
        "timeouts_found": 0,
        "details": [],
    }

    for order in active_orders:
        timeouts = await check_order_timeouts(db, order)
        if timeouts:
            stats["timeouts_found"] += 1
            for stage_key, desc in timeouts:
                stats["details"].append({
                    "order_id": order.id,
                    "order_no": order.order_no,
                    "stage": stage_key,
                    "description": desc,
                })

    return stats
