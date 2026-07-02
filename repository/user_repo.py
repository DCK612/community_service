"""
用户 Repository — 封装用户相关的数据库操作。

包括用户基础表（UserBase）、居民扩展表（ResidentProfile）、
服务者扩展表（ProviderProfile）的 CRUD 及专用查询方法。
"""

from typing import List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.user import (
    ProviderProfile,
    ProviderStatus,
    ResidentProfile,
    UserBase,
    UserRole,
)
from repository.base import BaseRepository


class UserRepository(BaseRepository[UserBase]):
    """用户 Repository — 双人群用户数据访问层。"""

    def __init__(self) -> None:
        """初始化，绑定 UserBase 模型。"""
        super().__init__(UserBase)

    # ==================== UserBase 查询 ====================

    async def get_by_phone(
        self, db: AsyncSession, phone: str
    ) -> Optional[UserBase]:
        """按手机号查询用户。

        Args:
            db: 异步数据库会话。
            phone: 手机号。

        Returns:
            匹配的 UserBase 对象，不存在返回 None。
        """
        result = await db.execute(
            select(UserBase).where(UserBase.phone == phone)
        )
        return result.scalar_one_or_none()

    async def get_with_profile(
        self, db: AsyncSession, user_id: int
    ) -> Optional[UserBase]:
        """查询用户及其扩展资料（根据 role 加载对应 Profile）。

        Args:
            db: 异步数据库会话。
            user_id: 用户 ID。

        Returns:
            加载了 Profile 的 UserBase 对象。
        """
        result = await db.execute(
            select(UserBase)
            .where(UserBase.id == user_id)
            .options(
                selectinload(UserBase.resident_profile),
                selectinload(UserBase.provider_profile),
            )
        )
        return result.scalar_one_or_none()

    async def get_residents(
        self,
        db: AsyncSession,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[UserBase]:
        """查询全部居民用户。

        Args:
            db: 异步数据库会话。
            offset: 偏移量。
            limit: 每页数量。

        Returns:
            居民用户列表。
        """
        result = await db.execute(
            select(UserBase)
            .where(UserBase.role == UserRole.RESIDENT)
            .options(selectinload(UserBase.resident_profile))
            .offset(offset)
            .limit(limit)
        )
        return result.scalars().all()

    async def get_providers(
        self,
        db: AsyncSession,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[UserBase]:
        """查询全部服务者用户。

        Args:
            db: 异步数据库会话。
            offset: 偏移量。
            limit: 每页数量。

        Returns:
            服务者用户列表。
        """
        result = await db.execute(
            select(UserBase)
            .where(UserBase.role == UserRole.PROVIDER)
            .options(selectinload(UserBase.provider_profile))
            .offset(offset)
            .limit(limit)
        )
        return result.scalars().all()

    # ==================== ProviderProfile 查询 ====================

    async def get_provider_profile(
        self, db: AsyncSession, user_id: int
    ) -> Optional[ProviderProfile]:
        """按 user_id 查询服务者扩展资料。

        Args:
            db: 异步数据库会话。
            user_id: 用户基础表 ID。

        Returns:
            ProviderProfile 对象，不存在返回 None。
        """
        result = await db.execute(
            select(ProviderProfile).where(ProviderProfile.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_online_providers(
        self, db: AsyncSession
    ) -> Sequence[UserBase]:
        """查询所有在线且未被拉黑的服务者。

        Returns:
            在线服务者 UserBase 列表（已加载 ProviderProfile）。
        """
        result = await db.execute(
            select(UserBase)
            .join(UserBase.provider_profile)
            .where(
                ProviderProfile.status == ProviderStatus.ONLINE,
                ProviderProfile.blacklisted == False,
            )
            .options(selectinload(UserBase.provider_profile))
        )
        return result.scalars().all()

    async def get_providers_by_skill(
        self, db: AsyncSession, skill_keyword: str
    ) -> Sequence[UserBase]:
        """按技能关键词模糊搜索在线服务者。

        Args:
            db: 异步数据库会话。
            skill_keyword: 技能关键词（如 "维修"）。

        Returns:
            匹配的服务者列表。
        """
        result = await db.execute(
            select(UserBase)
            .join(UserBase.provider_profile)
            .where(
                ProviderProfile.status == ProviderStatus.ONLINE,
                ProviderProfile.blacklisted == False,
                ProviderProfile.skills.like(f"%{skill_keyword}%"),
            )
            .options(selectinload(UserBase.provider_profile))
        )
        return result.scalars().all()

    # ==================== ResidentProfile 查询 ====================

    async def get_resident_profile(
        self, db: AsyncSession, user_id: int
    ) -> Optional[ResidentProfile]:
        """按 user_id 查询居民扩展资料。

        Args:
            db: 异步数据库会话。
            user_id: 用户基础表 ID。

        Returns:
            ResidentProfile 对象，不存在返回 None。
        """
        result = await db.execute(
            select(ResidentProfile).where(ResidentProfile.user_id == user_id)
        )
        return result.scalar_one_or_none()

    # ==================== 创建用户（含扩展资料） ====================

    async def create_resident(
        self,
        db: AsyncSession,
        phone: str,
        nickname: str,
        address: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> UserBase:
        """创建居民用户（同时创建 UserBase + ResidentProfile）。

        Args:
            db: 异步数据库会话。
            phone: 手机号。
            nickname: 昵称。
            address: 默认地址。
            latitude: 纬度。
            longitude: 经度。

        Returns:
            新创建的 UserBase 对象（已加载 resident_profile）。
        """
        user = UserBase(
            role=UserRole.RESIDENT,
            phone=phone,
            nickname=nickname,
        )
        db.add(user)
        await db.flush()  # 获取 user.id

        profile = ResidentProfile(
            user_id=user.id,
            address=address,
            latitude=latitude,
            longitude=longitude,
        )
        db.add(profile)
        await db.commit()
        await db.refresh(user)
        return user

    async def create_provider(
        self,
        db: AsyncSession,
        phone: str,
        nickname: str,
        skills: Optional[str] = None,
        address: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> UserBase:
        """创建服务者用户（同时创建 UserBase + ProviderProfile）。

        Args:
            db: 异步数据库会话。
            phone: 手机号。
            nickname: 昵称。
            skills: 技能标签（逗号分隔）。
            address: 服务地址。
            latitude: 纬度。
            longitude: 经度。

        Returns:
            新创建的 UserBase 对象（已加载 provider_profile）。
        """
        user = UserBase(
            role=UserRole.PROVIDER,
            phone=phone,
            nickname=nickname,
        )
        db.add(user)
        await db.flush()

        profile = ProviderProfile(
            user_id=user.id,
            skills=skills,
            address=address,
            latitude=latitude,
            longitude=longitude,
            status=ProviderStatus.OFFLINE,
        )
        db.add(profile)
        await db.commit()
        await db.refresh(user)
        return user


# 单例实例，供 Service 层直接导入使用
user_repo = UserRepository()
