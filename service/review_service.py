"""
评价服务 — 双端互评与信用分计算。

综合信用分计算公式：
final_score = 居民评价均分 × 0.7 + 被评均分(服务者评居民) × 0.3 + 系统加减分

系统自动加减分规则：
- 30分钟内接单：+3 分
- 好评（均分 >= 4）：+5 分
- 被投诉（差评均分 <= 2）：-20 分
- 超时：-10 分 / 次
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

import config
from models.order import Order, OrderStatus
from models.review import Review, ReviewType
from models.user import UserBase
from repository.order_repo import order_repo
from repository.review_repo import review_repo
from repository.user_repo import user_repo


# ==================== 评价创建 ====================

async def create_resident_review(
    db: AsyncSession,
    order: Order,
    resident_id: int,
    attitude: int,
    professionalism: int,
    punctuality: int,
    cost: int,
    after_sale: int,
    comment: Optional[str] = None,
) -> Review:
    """居民评价服务者。

    校验：
    - 订单状态为 WAITING_REVIEW
    - 评价人是订单居民
    - 未重复评价
    - 各项评分在 1-5 范围内

    Args:
        db: 异步数据库会话。
        order: 订单对象。
        resident_id: 居民 ID。
        attitude: 服务态度 1-5。
        professionalism: 专业程度 1-5。
        punctuality: 守时情况 1-5。
        cost: 收费合理性 1-5。
        after_sale: 售后保障 1-5。
        comment: 文字评价。

    Returns:
        新创建的 Review 对象。
    """
    # 校验订单状态
    if order.status != OrderStatus.WAITING_REVIEW:
        raise ValueError(f"订单状态为 {order.status.value}，不可评价")

    # 校验评价人
    if order.resident_id != resident_id:
        raise ValueError("只有下单居民才能评价服务者")

    # 校验是否已评价
    has_reviewed = await review_repo.has_reviewed(
        db, order.id, resident_id
    )
    if has_reviewed:
        raise ValueError("您已对该订单评价过")

    # 校验分值范围
    scores = [attitude, professionalism, punctuality, cost, after_sale]
    for s in scores:
        if s < 1 or s > 5:
            raise ValueError(f"评分必须在 1-5 之间，传入: {s}")

    review = Review(
        order_id=order.id,
        review_type=ReviewType.RESIDENT_TO_PROVIDER,
        reviewer_id=resident_id,
        reviewed_id=order.provider_id,
        resident_attitude=attitude,
        professionalism=professionalism,
        punctuality=punctuality,
        cost=cost,
        after_sale=after_sale,
        comment=comment,
    )
    review = await review_repo.create(db, review)

    # 记录居民评价时间
    order.reviewed_by_resident_at = review.created_at
    await db.commit()

    # 检查双方是否都已完成评价，若是则归档订单
    provider_reviewed = await review_repo.has_reviewed(
        db, order.id, order.provider_id
    )
    if provider_reviewed:
        from service.order_service import complete_order
        await complete_order(db, order)

    # 更新服务者信用分
    await update_provider_credit_score(db, order.provider_id)

    return review


async def create_provider_review(
    db: AsyncSession,
    order: Order,
    provider_id: int,
    accuracy: int,
    cooperation: int,
    payment: int,
    comment: Optional[str] = None,
) -> Review:
    """服务者评价居民。

    校验：
    - 订单状态为 WAITING_REVIEW
    - 评价人是订单服务者
    - 未重复评价
    - 各项评分在 1-5 范围内

    Args:
        db: 异步数据库会话。
        order: 订单对象。
        provider_id: 服务者 ID。
        accuracy: 需求准确度 1-5。
        cooperation: 配合度 1-5。
        payment: 付款及时性 1-5。
        comment: 文字评价。

    Returns:
        新创建的 Review 对象。
    """
    if order.status != OrderStatus.WAITING_REVIEW:
        raise ValueError(f"订单状态为 {order.status.value}，不可评价")

    if order.provider_id != provider_id:
        raise ValueError("只有接单服务者才能评价居民")

    has_reviewed = await review_repo.has_reviewed(db, order.id, provider_id)
    if has_reviewed:
        raise ValueError("您已对该订单评价过")

    scores = [accuracy, cooperation, payment]
    for s in scores:
        if s < 1 or s > 5:
            raise ValueError(f"评分必须在 1-5 之间，传入: {s}")

    review = Review(
        order_id=order.id,
        review_type=ReviewType.PROVIDER_TO_RESIDENT,
        reviewer_id=provider_id,
        reviewed_id=order.resident_id,
        provider_accuracy=accuracy,
        cooperation=cooperation,
        payment=payment,
        comment=comment,
    )
    review = await review_repo.create(db, review)

    # 记录服务者评价时间
    order.reviewed_by_provider_at = review.created_at
    await db.commit()

    # 检查双方是否都已完成评价
    resident_reviewed = await review_repo.has_reviewed(
        db, order.id, order.resident_id
    )
    if resident_reviewed:
        from service.order_service import complete_order
        await complete_order(db, order)

    await update_provider_credit_score(db, order.provider_id)

    return review


# ==================== 信用分计算 ====================

async def update_provider_credit_score(
    db: AsyncSession,
    provider_id: int,
) -> int:
    """更新服务者综合信用分。

    公式：final = 居民评价均分 × 0.7 + 被评均分 × 0.3 + 系统加减分

    系统加减分规则：
    - 30分钟内接单：+3
    - 好评（均分 >= 4）：+5
    - 差评（均分 <= 2，视为投诉）：-20
    - 超时：-10/次

    Args:
        db: 异步数据库会话。
        provider_id: 服务者 ID。

    Returns:
        更新后的信用分。
    """
    profile = await user_repo.get_provider_profile(db, provider_id)
    if profile is None:
        raise ValueError(f"服务者不存在: {provider_id}")

    # 基础分 = 80（初始值）
    base_score = 80.0

    # 1. 居民评价均分（0.7 权重）
    avg_rating = await review_repo.get_avg_rating_for_provider(db, provider_id)
    profile.avg_rating = avg_rating
    review_score = avg_rating * 20.0 * config.REVIEW_WEIGHT_RESIDENT  # 转百分制

    # 2. 被评均分（0.3 权重，这里简化：用 avg_rating 近似）
    provider_score = avg_rating * 20.0 * config.REVIEW_WEIGHT_PROVIDER

    # 3. 系统加减分
    system_bonus = 0

    # 检查最近是否有快速接单（接单时间 - 创建时间 < 30分钟）
    provider_orders = await order_repo.get_by_provider(db, provider_id, limit=10)
    for o in provider_orders:
        if o.accepted_at and o.created_at:
            delta = (o.accepted_at - o.created_at).total_seconds() / 60
            if delta <= 30:
                system_bonus += config.SCORE_QUICK_ACCEPT_BONUS
                break  # 只计一次

    # 检查超时惩罚
    for o in provider_orders:
        if o.is_timeout and not hasattr(o, '_timeout_penalized'):
            system_bonus += config.SCORE_TIMEOUT_PENALTY  # -10

    # 检查最近评价的好评/差评
    recent_reviews = await review_repo.get_reviews_for_provider(
        db, provider_id, limit=10
    )
    has_good_review = any(r.avg_score >= 4.0 for r in recent_reviews)
    if has_good_review:
        system_bonus += config.SCORE_GOOD_REVIEW_BONUS

    complaint_count = await review_repo.count_complaint_reviews(db, provider_id)
    system_bonus += complaint_count * config.SCORE_COMPLAINT_PENALTY

    # 综合计算
    final_score = base_score + review_score + provider_score + system_bonus

    # 限制范围 0-100
    final_score = max(0, min(100, final_score))
    profile.credit_score = int(final_score)

    # 更新投诉计数到 profile
    profile.complaint_count = complaint_count

    await db.commit()
    await db.refresh(profile)

    return profile.credit_score


async def get_provider_score_detail(
    db: AsyncSession,
    provider_id: int,
) -> dict:
    """获取服务者信用分明细。

    Args:
        db: 异步数据库会话。
        provider_id: 服务者 ID。

    Returns:
        包含各项分数的字典。
    """
    profile = await user_repo.get_provider_profile(db, provider_id)
    if profile is None:
        raise ValueError(f"服务者不存在: {provider_id}")

    avg_rating = await review_repo.get_avg_rating_for_provider(db, provider_id)
    complaint_count = await review_repo.count_complaint_reviews(db, provider_id)

    return {
        "provider_id": provider_id,
        "credit_score": profile.credit_score,
        "avg_rating": avg_rating,
        "complaint_count": complaint_count,
        "timeout_count": profile.timeout_count,
        "blacklisted": profile.blacklisted,
        "blacklist_type": profile.blacklist_type,
    }
