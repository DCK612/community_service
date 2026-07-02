"""
支付定价服务 — 价格校验、预付计算、结算计算。
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.price_guide import PriceGuide
from models.order import OrderCategory


async def validate_price(
    db: AsyncSession,
    price: float,
    category: str,
) -> Optional[PriceGuide]:
    """校验用户出价是否不低于定价参考最低价。

    Args:
        db: 异步数据库会话。
        price: 用户出价（元）。
        category: 服务类别。

    Returns:
        匹配的 PriceGuide 对象（若有）。

    Raises:
        ValueError: price < 所有同类别定价参考的 price_min。
    """
    result = await db.execute(
        select(PriceGuide)
        .where(
            PriceGuide.category == category,
            PriceGuide.is_active == True,
        )
    )
    guides = result.scalars().all()

    if not guides:
        # 该类别无定价参考，不限制
        return None

    # 找到所有最低价中的最小值
    min_price = min(g.price_min for g in guides)

    if price < min_price:
        raise ValueError(
            f"出价 ¥{price:.2f} 低于「{category}」类别最低参考价 ¥{min_price:.2f}，请重新出价"
        )

    return guides[0]


def calculate_prepaid(total_price: float) -> float:
    """计算预付款金额 = total_price * 50%。

    Args:
        total_price: 订单总价。

    Returns:
        预付款金额。
    """
    return round(total_price * 0.5, 2)


def calculate_settlement(
    total_price: float,
    platform_fee_rate: float = 0.03,
) -> tuple:
    """计算平台抽成和服务者结算金额。

    Args:
        total_price: 订单总价。
        platform_fee_rate: 平台抽成比例，默认 3%。

    Returns:
        (platform_fee, settlement_amount) 元组。
    """
    platform_fee = round(total_price * platform_fee_rate, 2)
    settlement_amount = round(total_price - platform_fee, 2)
    return platform_fee, settlement_amount
