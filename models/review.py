"""
评价模型 — 双端互评打分体系。

居民评价服务者：5 个维度各 1-5 分
- resident_attitude: 服务态度
- professionalism: 专业程度
- punctuality: 守时情况
- cost: 收费合理性
- after_sale: 售后保障

服务者评价居民：3 个维度各 1-5 分
- provider_accuracy: 需求准确度
- cooperation: 配合度
- payment: 付款及时性
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

class ReviewType(str, enum.Enum):
    """评价类型枚举 — 区分居民评服务者 / 服务者评居民。"""
    RESIDENT_TO_PROVIDER = "RESIDENT_TO_PROVIDER"  # 居民评价服务者
    PROVIDER_TO_RESIDENT = "PROVIDER_TO_RESIDENT"  # 服务者评价居民


# ==================== ORM 模型 ====================

class Review(Base):
    """评价表 — 记录双端互评的详细打分。

    每条订单最多产生两条评价记录：
    - 居民对服务者的评价（review_type=RESIDENT_TO_PROVIDER）
    - 服务者对居民的评价（review_type=PROVIDER_TO_RESIDENT）
    """

    __tablename__ = "review"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 关联订单
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("order.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="关联订单ID"
    )
    # 评价类型
    review_type: Mapped[ReviewType] = mapped_column(
        Enum(ReviewType), nullable=False, comment="评价类型"
    )
    # 评价人用户ID
    reviewer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_base.id"), nullable=False,
        comment="评价人用户ID"
    )
    # 被评价人用户ID
    reviewed_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_base.id"), nullable=False,
        comment="被评价人用户ID"
    )
    # ========== 居民评价服务者维度（1-5分） ==========
    # 服务态度评分
    resident_attitude: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="服务态度 1-5"
    )
    # 专业程度评分
    professionalism: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="专业程度 1-5"
    )
    # 守时情况评分
    punctuality: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="守时情况 1-5"
    )
    # 收费合理性评分
    cost: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="收费合理性 1-5"
    )
    # 售后保障评分
    after_sale: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="售后保障 1-5"
    )

    # ========== 服务者评价居民维度（1-5分） ==========
    # 需求准确度评分
    provider_accuracy: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="需求准确度 1-5"
    )
    # 配合度评分
    cooperation: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="配合度 1-5"
    )
    # 付款及时性评分
    payment: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="付款及时性 1-5"
    )

    # 文字评价内容
    comment: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="文字评价内容"
    )
    # 评价时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="评价时间"
    )

    # 关联
    order: Mapped["Order"] = relationship("Order", lazy="selectin")
    reviewer: Mapped["UserBase"] = relationship(
        "UserBase", foreign_keys=[reviewer_id], lazy="selectin"
    )
    reviewed: Mapped["UserBase"] = relationship(
        "UserBase", foreign_keys=[reviewed_id], lazy="selectin"
    )

    @property
    def avg_score(self) -> float:
        """计算评价均分（根据评价类型返回对应维度的平均值）。

        Returns:
            float: 对应评价类型的维度均分（1-5）。
        """
        if self.review_type == ReviewType.RESIDENT_TO_PROVIDER:
            # 居民评价服务者：5 个维度
            scores = [
                self.resident_attitude,
                self.professionalism,
                self.punctuality,
                self.cost,
                self.after_sale,
            ]
        else:
            # 服务者评价居民：3 个维度
            scores = [
                self.provider_accuracy,
                self.cooperation,
                self.payment,
            ]
        valid_scores = [s for s in scores if s is not None]
        if not valid_scores:
            return 0.0
        return round(sum(valid_scores) / len(valid_scores), 2)

    def __repr__(self) -> str:
        return (
            f"<Review(id={self.id}, type={self.review_type.value}, "
            f"order_id={self.order_id})>"
        )
