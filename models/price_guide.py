"""
定价参考模型 — 社区服务项目参考价格标准。

管理员可增删改，居民下单时展示，服务者接单时参考。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base
from models.order import OrderCategory


class PriceGuide(Base):
    """定价参考表 — 各服务类别的参考价格区间。

    字段说明：
    - category: 服务类别（与 OrderCategory 一致）
    - name: 具体服务项目名称（如"水管维修"、"空调清洗"）
    - description: 服务详情描述
    - price_min: 参考最低价（元）
    - price_max: 参考最高价（元）
    - unit: 计价单位（次 / 小时 / 平方米 / 台 等）
    - is_active: 是否启用（禁用后前端不展示）
    """

    __tablename__ = "price_guide"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 服务类别（维修/保洁/搬家/家教/养老/其他）
    category: Mapped[OrderCategory] = mapped_column(
        Enum(OrderCategory), nullable=False, index=True, comment="服务类别"
    )

    # 服务项目名称
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="服务项目名称"
    )

    # 服务描述
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="服务描述"
    )

    # 参考最低价（元）
    price_min: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="参考最低价（元）"
    )

    # 参考最高价（元）
    price_max: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="参考最高价（元）"
    )

    # 计价单位
    unit: Mapped[str] = mapped_column(
        String(20), nullable=False, default="次", comment="计价单位"
    )

    # 是否启用
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="是否启用"
    )

    # 创建时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间"
    )

    # 更新时间
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )

    def __repr__(self) -> str:
        return (
            f"<PriceGuide(id={self.id}, category={self.category.value}, "
            f"name={self.name}, ¥{self.price_min}~{self.price_max}/{self.unit})>"
        )
