"""
黑名单服务 — 自动检测并处理违规服务者。

触发条件（均通过 config 可配）：
1. 信用分 < CREDIT_SCORE_THRESHOLD（默认 30）→ 永久拉黑
2. 累计投诉次数 >= COMPLAINT_COUNT_THRESHOLD（默认 3）→ 永久拉黑
3. 7天内超时次数 >= TIMEOUT_COUNT_THRESHOLD（默认 3）→ 临时冻结
"""

from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

import config
from models.user import ProviderProfile, UserBase
from repository.blacklist_repo import blacklist_repo
from repository.order_repo import order_repo
from repository.review_repo import review_repo
from repository.user_repo import user_repo


async def check_and_auto_blacklist(
    db: AsyncSession,
    provider_id: int,
) -> Optional[dict]:
    """自动检查服务者是否触发黑名单条件并处理。

    检查顺序：
    1. 信用分过低 → 永久拉黑
    2. 投诉次数过多 → 永久拉黑
    3. 超时次数过多 → 临时冻结 7 天

    Args:
        db: 异步数据库会话。
        provider_id: 服务者 ID。

    Returns:
        触发拉黑时返回详情字典，未触发返回 None。
    """
    provider = await user_repo.get_by_id(db, provider_id)
    if provider is None or provider.provider_profile is None:
        return None

    profile = provider.provider_profile

    # 已在黑名单中，跳过
    if profile.blacklisted:
        return None

    # 条件1：信用分低于阈值 → 永久拉黑
    if profile.credit_score < config.CREDIT_SCORE_THRESHOLD:
        await blacklist_repo.add_to_blacklist(
            db, provider,
            blacklist_type="permanent",
        )
        return {
            "provider_id": provider_id,
            "reason": "信用分过低",
            "detail": f"信用分 {profile.credit_score} < 阈值 {config.CREDIT_SCORE_THRESHOLD}",
            "action": "permanent_ban",
        }

    # 条件2：投诉次数超过阈值 → 永久拉黑
    complaint_count = await review_repo.count_complaint_reviews(db, provider_id)
    profile.complaint_count = complaint_count
    await db.commit()

    if complaint_count >= config.COMPLAINT_COUNT_THRESHOLD:
        await blacklist_repo.add_to_blacklist(
            db, provider,
            blacklist_type="permanent",
        )
        return {
            "provider_id": provider_id,
            "reason": "投诉次数过多",
            "detail": f"投诉 {complaint_count} 次 >= 阈值 {config.COMPLAINT_COUNT_THRESHOLD}",
            "action": "permanent_ban",
        }

    # 条件3：7天内超时次数超过阈值 → 临时冻结 7 天
    timeout_orders = await order_repo.get_timeout_orders(
        db, provider_id, config.TIMEOUT_WINDOW_DAYS
    )
    timeout_count = len(timeout_orders)

    if timeout_count >= config.TIMEOUT_COUNT_THRESHOLD:
        await blacklist_repo.add_to_blacklist(
            db, provider,
            blacklist_type="temporary",
            freeze_days=config.TIMEOUT_WINDOW_DAYS,
        )
        return {
            "provider_id": provider_id,
            "reason": "超时次数过多",
            "detail": f"{config.TIMEOUT_WINDOW_DAYS}天内超时 {timeout_count} 次 >= 阈值 {config.TIMEOUT_COUNT_THRESHOLD}",
            "action": f"temporary_freeze_{config.TIMEOUT_WINDOW_DAYS}d",
        }

    return None


async def scan_all_providers(
    db: AsyncSession,
) -> list[dict]:
    """扫描所有服务者，自动拉黑违规者。

    Returns:
        本次被拉黑的服务者详情列表。
    """
    providers = await user_repo.get_providers(db)
    results = []

    for provider in providers:
        result = await check_and_auto_blacklist(db, provider.id)
        if result:
            results.append(result)

    return results


async def release_expired_frozen(
    db: AsyncSession,
) -> list[int]:
    """释放所有已到期的临时冻结服务者。

    Returns:
        本次解封的 provider_id 列表。
    """
    return await blacklist_repo.check_and_release_frozen(db)


async def get_blacklist_detail(
    db: AsyncSession,
    offset: int = 0,
    limit: int = 100,
):
    """获取黑名单详情列表。

    Returns:
        (黑名单列表, 总数)
    """
    providers = await blacklist_repo.get_blacklisted_providers(
        db, offset=offset, limit=limit
    )

    details = []
    for p in providers:
        profile = p.provider_profile
        details.append({
            "user_id": p.id,
            "nickname": p.nickname,
            "phone": p.phone,
            "credit_score": profile.credit_score,
            "complaint_count": profile.complaint_count,
            "timeout_count": profile.timeout_count,
            "blacklist_type": profile.blacklist_type,
            "blacklisted_at": (
                profile.blacklisted_at.isoformat()
                if profile.blacklisted_at else None
            ),
            "blacklist_until": (
                profile.blacklist_until.isoformat()
                if profile.blacklist_until else None
            ),
        })

    return details
