"""
派单引擎服务 — 智能匹配最优服务者。

优先级公式（分数越高越优先）：
score = credit_score × W1 + (5 - ongoing_orders) × W2 + distance_score × W3 + skill_match × W4 - timeout_count × W5

其中：
- credit_score: 服务者信用评分 (0-100)
- ongoing_orders: 当前在途订单数
- distance_score: 距离分（越近越高，最大 20）
- skill_match: 技能匹配度（0 或 10，取决于是否匹配需求类别）
- timeout_count: 近7天超时次数

过滤规则：
- 排除黑名单服务者
- 排除 OFFLINE 状态的服务者
- 排除 BUSY（在途订单 >= 5）的服务者
"""

import math
from typing import List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

import config
from models.user import ProviderProfile, ProviderStatus, UserBase
from repository.order_repo import order_repo
from repository.user_repo import user_repo


# ==================== 距离计算 ====================

def _haversine_distance(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
) -> float:
    """使用 Haversine 公式计算两点间的球面距离。

    Args:
        lat1, lon1: 第一点坐标。
        lat2, lon2: 第二点坐标。

    Returns:
        两点间距离（公里）。
    """
    R = 6371.0  # 地球半径（公里）

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _calc_distance_score(distance_km: float) -> float:
    """将距离转换为评分（越近越高，最大 20 分）。

    Args:
        distance_km: 距离（公里）。

    Returns:
        距离评分 0-20。
    """
    max_distance = 50.0  # 超过 50km 视为不可达
    if distance_km >= max_distance:
        return 0.0
    # 线性衰减：距离 0km -> 20分，50km -> 0分
    return config.DISPATCH_WEIGHT_DISTANCE_MAX * (1 - distance_km / max_distance)


# ==================== 技能匹配 ====================

# 订单类别到技能关键词的映射
CATEGORY_SKILL_MAP = {
    "REPAIR": ["维修", "修理", "修"],
    "CLEANING": ["保洁", "清洁", "打扫"],
    "MOVING": ["搬家", "搬运"],
    "TUTORING": ["家教", "辅导", "教学"],
    "ELDERLY_CARE": ["养老", "护理", "陪护"],
    "OTHER": [],
}


def _calc_skill_match(category: str, provider_skills: Optional[str]) -> float:
    """计算服务者技能匹配度。

    Args:
        category: 订单服务类别。
        provider_skills: 服务者技能标签（逗号分隔）。

    Returns:
        匹配得分（0 或 10）。
    """
    if not provider_skills:
        return 0.0

    provider_skill_list = [
        s.strip().lower() for s in provider_skills.split(",")
    ]
    target_keywords = CATEGORY_SKILL_MAP.get(category, [])

    for keyword in target_keywords:
        if any(keyword.lower() in skill for skill in provider_skill_list):
            return config.DISPATCH_WEIGHT_SKILL_MATCH

    # OTHER 类别默认匹配
    if category == "OTHER":
        return config.DISPATCH_WEIGHT_SKILL_MATCH

    return 0.0


# ==================== 派单引擎 ====================

async def calculate_dispatch_scores(
    db: AsyncSession,
    category: str,
    order_lat: Optional[float] = None,
    order_lon: Optional[float] = None,
) -> List[Tuple[UserBase, float]]:
    """为所有符合条件的服务者计算派单优先级评分。

    过滤条件：
    1. 在线状态（ONLINE）
    2. 未被拉黑
    3. 在途订单数 < 5

    评分规则：
    score = credit_score × 0.5 + (5 - ongoing) × 5 + distance × 1 + skill × 10 - timeout × 5

    Args:
        db: 异步数据库会话。
        category: 订单服务类别。
        order_lat: 订单地址纬度。
        order_lon: 订单地址经度。

    Returns:
        按评分降序排列的 (服务者UserBase, 评分) 列表。
    """
    # 获取所有在线且未拉黑的服务者
    providers = await user_repo.get_online_providers(db)

    scored: List[Tuple[UserBase, float]] = []

    for provider in providers:
        profile = provider.provider_profile
        if profile is None:
            continue

        # 在途订单数 >= 5 则视为繁忙，跳过
        if profile.ongoing_orders_count >= 5:
            continue

        score = 0.0

        # 1. 信用评分权重
        score += profile.credit_score * config.DISPATCH_WEIGHT_CREDIT_SCORE

        # 2. 在途订单权重（越少越好）
        score += (5 - profile.ongoing_orders_count) * config.DISPATCH_WEIGHT_ONGOING_ORDERS

        # 3. 距离分
        if order_lat is not None and order_lon is not None and \
           profile.latitude is not None and profile.longitude is not None:
            distance = _haversine_distance(
                order_lat, order_lon,
                profile.latitude, profile.longitude,
            )
            score += _calc_distance_score(distance)
        else:
            # 无坐标时给予默认距离分
            score += config.DISPATCH_WEIGHT_DISTANCE_MAX / 2

        # 4. 技能匹配度
        score += _calc_skill_match(category, profile.skills)

        # 5. 超时惩罚
        timeout_orders = await order_repo.get_timeout_orders(
            db, provider.id, config.TIMEOUT_WINDOW_DAYS
        )
        timeout_count = len(timeout_orders)
        score -= timeout_count * config.DISPATCH_WEIGHT_TIMEOUT_PENALTY

        scored.append((provider, round(score, 2)))

    # 按评分降序排列
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


async def get_available_orders_for_provider(
    db: AsyncSession,
    provider_id: int,
) -> List:
    """获取服务者可接的订单列表（按优先级排序）。

    当前简单实现：返回全部 PENDING 订单，
    实际应用中会结合服务者技能和位置做个性化排序。

    Args:
        db: 异步数据库会话。
        provider_id: 服务者 ID。

    Returns:
        可接订单列表。
    """
    # 校验服务者身份
    provider = await user_repo.get_by_id(db, provider_id)
    if provider is None or provider.provider_profile is None:
        raise ValueError("服务者不存在")
    if provider.provider_profile.blacklisted:
        raise ValueError("您已被拉黑，无法接单")

    orders = await order_repo.get_pending_orders(db)
    return list(orders)
