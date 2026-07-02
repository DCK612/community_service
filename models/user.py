"""
用户模型 — 双人群用户体系（居民 / 服务者互斥）。

role 字段采用枚举约束，确保一个用户只能是 RESIDENT 或 PROVIDER 之一。
ProviderProfile 包含信用评分、平均评分、黑名单状态和服务状态等核心字段。
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
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

class UserRole(str, enum.Enum):
    """用户角色枚举：居民 / 服务者 / 管理员。"""
    RESIDENT = "RESIDENT"    # 居民（下单方）
    PROVIDER = "PROVIDER"    # 服务者（接单方）
    ADMIN = "ADMIN"          # 管理员


class ProviderStatus(str, enum.Enum):
    """服务者在线状态枚举。"""
    ONLINE = "ONLINE"        # 在线可接单
    OFFLINE = "OFFLINE"      # 离线
    BUSY = "BUSY"            # 忙碌中


# ==================== ORM 模型 ====================

class UserBase(Base):
    """用户基础表 — 存储居民和服务者的公共字段。

    role 为 RESIDENT 时：关联 ResidentProfile 一对一扩展表。
    role 为 PROVIDER 时：关联 ProviderProfile 一对一扩展表。
    """

    __tablename__ = "user_base"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 用户角色（RESIDENT | PROVIDER），互斥不可同时拥有
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), nullable=False, comment="用户角色：RESIDENT 或 PROVIDER"
    )
    # 手机号（唯一登录标识）
    phone: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True, comment="手机号"
    )
    # 用户昵称
    nickname: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="用户昵称"
    )
    # 头像 URL
    avatar_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, comment="头像地址"
    )
    # 密码哈希
    password_hash: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, comment="密码哈希（bcrypt）"
    )
    # 注册时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="注册时间"
    )

    # 关联：一对一 -> ResidentProfile / ProviderProfile
    resident_profile: Mapped[Optional["ResidentProfile"]] = relationship(
        "ResidentProfile", back_populates="user", uselist=False, lazy="selectin"
    )
    provider_profile: Mapped[Optional["ProviderProfile"]] = relationship(
        "ProviderProfile", back_populates="user", uselist=False, lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<UserBase(id={self.id}, role={self.role.value}, phone={self.phone})>"


class ResidentProfile(Base):
    """居民扩展信息表 — 存储居民特有的属性。

    每个居民对应一条 UserBase (role=RESIDENT)，通过 user_id 一对一关联。
    """

    __tablename__ = "resident_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 关联用户基础表
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_base.id", ondelete="CASCADE"),
        unique=True, nullable=False, comment="用户基础表ID"
    )
    # 默认服务地址
    address: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, comment="默认服务地址"
    )
    # 地址坐标（纬度，用于距离计算）
    latitude: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="地址纬度"
    )
    # 地址坐标（经度，用于距离计算）
    longitude: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="地址经度"
    )
    # 累计下单次数
    total_orders: Mapped[int] = mapped_column(
        Integer, default=0, comment="累计下单次数"
    )

    # 反向关联
    user: Mapped["UserBase"] = relationship(
        "UserBase", back_populates="resident_profile"
    )

    def __repr__(self) -> str:
        return f"<ResidentProfile(id={self.id}, user_id={self.user_id})>"


class ProviderProfile(Base):
    """服务者扩展信息表 — 存储服务者特有的属性。

    包含信用评分体系、黑名单机制、在线状态和技能标签等核心字段。
    """

    __tablename__ = "provider_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 关联用户基础表
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_base.id", ondelete="CASCADE"),
        unique=True, nullable=False, comment="用户基础表ID"
    )
    # 信用评分（0-100，初始值 80）
    credit_score: Mapped[int] = mapped_column(
        Integer, default=80, nullable=False, comment="信用评分 0-100"
    )
    # 平均评分（1-5分，来自居民评价）
    avg_rating: Mapped[float] = mapped_column(
        Float, default=5.0, nullable=False, comment="平均评分 1-5"
    )
    # 是否被拉黑
    blacklisted: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="是否在黑名单中"
    )
    # 黑名单类型：permanent(永久) / temporary(临时冻结)
    blacklist_type: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="黑名单类型: permanent / temporary"
    )
    # 黑名单加入时间
    blacklisted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="黑名单加入时间"
    )
    # 黑名单解封时间（临时冻结适用）
    blacklist_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="临时冻结解封时间"
    )
    # 在线状态
    status: Mapped[ProviderStatus] = mapped_column(
        Enum(ProviderStatus), default=ProviderStatus.OFFLINE,
        nullable=False, comment="在线状态: ONLINE/OFFLINE/BUSY"
    )
    # 技能标签（逗号分隔，如 "维修,保洁,搬家"）
    skills: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, comment="技能标签（逗号分隔）"
    )
    # 服务地址
    address: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, comment="服务地址"
    )
    # 地址纬度
    latitude: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="地址纬度"
    )
    # 地址经度
    longitude: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="地址经度"
    )
    # 当前在途订单数（已接单但未完成）
    ongoing_orders_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="当前在途订单数"
    )
    # 累计超时次数
    timeout_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="累计超时次数"
    )
    # 累计投诉次数
    complaint_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="累计被投诉次数"
    )
    # 身份证号（实名认证）
    id_card: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="身份证号"
    )

    # 反向关联
    user: Mapped["UserBase"] = relationship(
        "UserBase", back_populates="provider_profile"
    )

    def __repr__(self) -> str:
        return (
            f"<ProviderProfile(id={self.id}, user_id={self.user_id}, "
            f"credit_score={self.credit_score}, status={self.status.value})>"
        )


# ==================== 管理员枚举与模型 ====================

class AdminRole(str, enum.Enum):
    """管理员角色枚举 — 三级权限体系。"""
    SUPER_ADMIN = "SUPER_ADMIN"  # 超级管理员（唯一，DDD账号）
    ADMIN_L1 = "ADMIN_L1"        # 一级：只读看板 + 订单查看
    ADMIN_L2 = "ADMIN_L2"        # 二级：L1 + 订单管理 + 用户管理
    ADMIN_L3 = "ADMIN_L3"        # 三级：L2 + 定价配置 + 黑名单管理 + 审批权限


class Administrator(Base):
    """管理员表 — 存储管理员的权限级别与审批状态。

    user_id 关联 UserBase，管理员必须首先是注册用户。
    审批流程：用户申请 → SUPER_ADMIN 审批 → is_approved=True。
    """

    __tablename__ = "administrator"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 关联用户基础表
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_base.id", ondelete="CASCADE"),
        unique=True, nullable=False, comment="用户基础表ID"
    )
    # 管理员权限级别
    admin_role: Mapped[AdminRole] = mapped_column(
        Enum(AdminRole), nullable=False, comment="管理员角色"
    )
    # 是否已通过审批
    is_approved: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="是否已审批通过"
    )
    # 审批人 ID（SUPER_ADMIN）
    approved_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user_base.id"), nullable=True, comment="审批人ID"
    )
    # 审批时间
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="审批时间"
    )
    # 创建时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="申请时间"
    )

    # 关联
    user: Mapped["UserBase"] = relationship(
        "UserBase", foreign_keys=[user_id], lazy="selectin"
    )
    reviewer: Mapped[Optional["UserBase"]] = relationship(
        "UserBase", foreign_keys=[approved_by], lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<Administrator(id={self.id}, user_id={self.user_id}, "
            f"role={self.admin_role.value}, approved={self.is_approved})>"
        )
