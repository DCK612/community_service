"""
黑名单 Repository — 黑名单数据访问层。

管理服务者的黑名单记录：查询、拉黑、解封等操作。
"""

from datetime import datetime
from typing import List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import ProviderProfile, UserBase, UserRole
from repository.base import BaseRepository


class BlacklistRepository:
    """黑名单 Repository（不继承 BaseRepository，因为操作对象是 ProviderProfile）。"""

    async def get_blacklisted_providers(
        self,
        db: AsyncSession,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[UserBase]:
        """查询所有被拉黑的服务者。

        Args:
            db: 异步数据库会话。
            offset: 偏移量。
            limit: 每页数量。

        Returns:
            被拉黑的服务者列表。
        """
        result = await db.execute(
            select(UserBase)
            .join(UserBase.provider_profile)
            .where(ProviderProfile.blacklisted == True)
            .offset(offset)
            .limit(limit)
        )
        return result.scalars().all()

    async def add_to_blacklist(
        self,
        db: AsyncSession,
        provider: UserBase,
        blacklist_type: str = "permanent",
        freeze_days: int = 0,
    ) -> ProviderProfile:
        """将服务者加入黑名单。

        Args:
            db: 异步数据库会话。
            provider: UserBase 对象（role=PROVIDER）。
            blacklist_type: 类型，permanent(永久) 或 temporary(临时冻结)。
            freeze_days: 临时冻结天数（permanent 时忽略）。

        Returns:
            更新后的 ProviderProfile。
        """
        profile = provider.provider_profile
        if profile is None:
            raise ValueError(f"用户 {provider.id} 没有 ProviderProfile")

        profile.blacklisted = True
        profile.blacklist_type = blacklist_type
        profile.blacklisted_at = datetime.now()

        if blacklist_type == "temporary" and freeze_days > 0:
            from datetime import timedelta
            profile.blacklist_until = datetime.now() + timedelta(days=freeze_days)
        else:
            profile.blacklist_until = None

        # 修改状态为离线
        from models.user import ProviderStatus
        profile.status = ProviderStatus.OFFLINE

        await db.commit()
        await db.refresh(profile)
        return profile

    async def remove_from_blacklist(
        self, db: AsyncSession, provider: UserBase
    ) -> ProviderProfile:
        """将服务者移出黑名单。

        Args:
            db: 异步数据库会话。
            provider: UserBase 对象。

        Returns:
            更新后的 ProviderProfile。
        """
        profile = provider.provider_profile
        if profile is None:
            raise ValueError(f"用户 {provider.id} 没有 ProviderProfile")

        profile.blacklisted = False
        profile.blacklist_type = None
        profile.blacklisted_at = None
        profile.blacklist_until = None

        await db.commit()
        await db.refresh(profile)
        return profile

    async def check_and_release_frozen(
        self, db: AsyncSession
    ) -> List[int]:
        """检查所有临时冻结的服务者，到期自动解封。

        Args:
            db: 异步数据库会话。

        Returns:
            本次解封的服务者 user_id 列表。
        """
        now = datetime.now()
        result = await db.execute(
            select(UserBase)
            .join(UserBase.provider_profile)
            .where(
                ProviderProfile.blacklisted == True,
                ProviderProfile.blacklist_type == "temporary",
                ProviderProfile.blacklist_until <= now,
                ProviderProfile.blacklist_until.isnot(None),
            )
        )
        frozen_providers = result.scalars().all()

        released_ids: List[int] = []
        for provider in frozen_providers:
            await self.remove_from_blacklist(db, provider)
            released_ids.append(provider.id)

        return released_ids


# 单例
blacklist_repo = BlacklistRepository()
