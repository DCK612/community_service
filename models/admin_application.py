"""
管理员申请审批模型 — 管理员权限申请与审批记录。
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.database import Base


class ApplicationStatus(str, enum.Enum):
    """申请状态枚举。"""
    PENDING = "PENDING"      # 待审批
    APPROVED = "APPROVED"    # 已通过
    REJECTED = "REJECTED"    # 已拒绝


class AdminApplication(Base):
    """管理员申请表 — 用户申请成为管理员的记录。

    SUPER_ADMIN 审批后可设定权限级别（L1/L2/L3）。
    """

    __tablename__ = "admin_application"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 申请人 ID
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_base.id"), nullable=False, comment="申请人ID"
    )
    # 申请理由
    reason: Mapped[str] = mapped_column(
        Text, nullable=False, comment="申请理由"
    )
    # 申请状态
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus), default=ApplicationStatus.PENDING,
        nullable=False, comment="申请状态"
    )
    # 审批人 ID
    reviewed_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user_base.id"), nullable=True, comment="审批人ID"
    )
    # 审批时间
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="审批时间"
    )
    # 申请时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="申请时间"
    )

    # 关联
    applicant: Mapped["UserBase"] = relationship(
        "UserBase", foreign_keys=[user_id], lazy="selectin"
    )
    reviewer: Mapped[Optional["UserBase"]] = relationship(
        "UserBase", foreign_keys=[reviewed_by], lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<AdminApplication(id={self.id}, user_id={self.user_id}, "
            f"status={self.status.value})>"
        )
