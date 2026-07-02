"""
评价 Repository — 评价数据访问层。

提供双端互评的 CRUD 和统计查询。
"""

from typing import List, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.order import Order
from models.review import Review, ReviewType
from repository.base import BaseRepository


class ReviewRepository(BaseRepository[Review]):
    """评价 Repository。"""

    def __init__(self) -> None:
        """初始化，绑定 Review 模型。"""
        super().__init__(Review)

    async def get_by_order(
        self,
        db: AsyncSession,
        order_id: int,
        review_type: Optional[ReviewType] = None,
    ) -> Sequence[Review]:
        """查询指定订单的评价记录。

        Args:
            db: 异步数据库会话。
            order_id: 订单 ID。
            review_type: 可选，按评价类型过滤。

        Returns:
            评价记录列表。
        """
        stmt = select(Review).where(Review.order_id == order_id)
        if review_type is not None:
            stmt = stmt.where(Review.review_type == review_type)
        result = await db.execute(stmt)
        return result.scalars().all()

    async def has_reviewed(
        self,
        db: AsyncSession,
        order_id: int,
        reviewer_id: int,
    ) -> bool:
        """检查评价人是否已对该订单评价。

        Args:
            db: 异步数据库会话。
            order_id: 订单 ID。
            reviewer_id: 评价人 ID。

        Returns:
            已评价返回 True，否则 False。
        """
        result = await db.execute(
            select(func.count(Review.id))
            .where(
                Review.order_id == order_id,
                Review.reviewer_id == reviewer_id,
            )
        )
        return (result.scalar() or 0) > 0

    async def get_reviews_for_provider(
        self,
        db: AsyncSession,
        provider_id: int,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[Review]:
        """查询服务者被评价的记录（只查居民对服务者的评价）。

        Args:
            db: 异步数据库会话。
            provider_id: 服务者用户 ID。
            offset: 偏移量。
            limit: 每页数量。

        Returns:
            评价记录列表。
        """
        result = await db.execute(
            select(Review)
            .where(
                Review.reviewed_id == provider_id,
                Review.review_type == ReviewType.RESIDENT_TO_PROVIDER,
            )
            .order_by(Review.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return result.scalars().all()

    async def get_avg_rating_for_provider(
        self, db: AsyncSession, provider_id: int
    ) -> float:
        """计算服务者的平均评分（基于居民评价的5个维度均分）。

        Args:
            db: 异步数据库会话。
            provider_id: 服务者用户 ID。

        Returns:
            平均评分（1-5），保留两位小数。
        """
        reviews = await self.get_reviews_for_provider(db, provider_id)
        if not reviews:
            return 5.0  # 无评价默认满分

        avg_scores = [r.avg_score for r in reviews if r.avg_score > 0]
        if not avg_scores:
            return 5.0

        return round(sum(avg_scores) / len(avg_scores), 2)

    async def count_complaint_reviews(
        self, db: AsyncSession, provider_id: int
    ) -> int:
        """统计服务者收到的低分差评（均分 <= 2）数量。

        Args:
            db: 异步数据库会话。
            provider_id: 服务者用户 ID。

        Returns:
            低分评价数量。
        """
        reviews = await self.get_reviews_for_provider(db, provider_id)
        return sum(1 for r in reviews if r.avg_score <= 2)


# 单例
review_repo = ReviewRepository()
