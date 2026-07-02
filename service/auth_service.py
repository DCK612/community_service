"""
用户认证服务 — 密码哈希、登录验证、JWT 生成、管理员申请审批。
"""

import bcrypt
import jwt
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import AI_PROVIDER
from models.user import UserBase, UserRole, AdminRole, Administrator
from models.admin_application import AdminApplication, ApplicationStatus
from repository.user_repo import user_repo

# JWT 配置
SECRET_KEY = "community-service-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 7 * 24 * 60  # 7天


def hash_password(password: str) -> str:
    """生成 bcrypt 哈希密码。"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码。"""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """生成 JWT 访问令牌。"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def authenticate_user(db, phone: str, password: str) -> Optional[UserBase]:
    """验证用户手机号和密码。"""
    user = await user_repo.get_by_phone(db, phone)
    if not user or not user.password_hash:
        return None
    if verify_password(password, user.password_hash):
        return user
    return None


async def register_resident(db, phone: str, nickname: str, password: str, **kwargs):
    """注册居民账号。"""
    hashed = hash_password(password)
    return await user_repo.create_resident(
        db,
        phone=phone,
        nickname=nickname,
        password_hash=hashed,
        **kwargs
    )


async def register_provider(db, phone: str, nickname: str, password: str, **kwargs):
    """注册服务者账号。"""
    hashed = hash_password(password)
    return await user_repo.create_provider(
        db,
        phone=phone,
        nickname=nickname,
        password_hash=hashed,
        **kwargs
    )


# ==================== 超级管理员初始化 ====================

async def init_super_admin(db: AsyncSession) -> None:
    """初始化超级管理员 DDD/1234。

    检查是否存在 phone="DDD" 的超级管理员，不存在则创建。
    首次启动时由 init_db.py 调用。
    """
    # 检查 DDD 账号是否已存在
    existing = await user_repo.get_by_phone(db, "DDD")
    if existing:
        # 检查是否已有 Administrator 记录
        result = await db.execute(
            select(Administrator).where(Administrator.user_id == existing.id)
        )
        admin = result.scalar_one_or_none()
        if admin and admin.admin_role == AdminRole.SUPER_ADMIN and admin.is_approved:
            return  # 已存在，无需初始化

    # 创建 UserBase
    hashed = hash_password("1234")
    user = UserBase(
        role=UserRole.ADMIN,
        phone="DDD",
        nickname="超级管理员",
        password_hash=hashed,
    )
    db.add(user)
    await db.flush()

    # 创建 Administrator 记录
    admin = Administrator(
        user_id=user.id,
        admin_role=AdminRole.SUPER_ADMIN,
        is_approved=True,
    )
    db.add(admin)
    await db.commit()
    print("[初始化] 超级管理员 DDD 已创建")


# ==================== 管理员申请审批 ====================

async def apply_admin(
    db: AsyncSession,
    user_id: int,
    reason: str,
) -> AdminApplication:
    """提交管理员申请。

    Args:
        db: 异步数据库会话。
        user_id: 申请人用户 ID。
        reason: 申请理由。

    Returns:
        创建的 AdminApplication 对象。

    Raises:
        ValueError: 用户已提交过待审批的申请。
    """
    # 检查是否已有待审批的申请
    result = await db.execute(
        select(AdminApplication)
        .where(
            AdminApplication.user_id == user_id,
            AdminApplication.status == ApplicationStatus.PENDING,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise ValueError("您已有待审批的管理员申请，请耐心等待")

    application = AdminApplication(
        user_id=user_id,
        reason=reason,
        status=ApplicationStatus.PENDING,
    )
    db.add(application)
    await db.commit()
    await db.refresh(application)
    return application


async def approve_admin_application(
    db: AsyncSession,
    application_id: int,
    reviewer_id: int,
    approved: bool,
    admin_role: Optional[str] = None,
) -> AdminApplication:
    """审批管理员申请（SUPER_ADMIN 专用）。

    Args:
        db: 异步数据库会话。
        application_id: 申请 ID。
        reviewer_id: 审批人（SUPER_ADMIN）ID。
        approved: 是否通过。
        admin_role: 若通过，指定的权限级别（ADMIN_L1 / ADMIN_L2 / ADMIN_L3）。

    Returns:
        更新后的 AdminApplication 对象。
    """
    result = await db.execute(
        select(AdminApplication).where(AdminApplication.id == application_id)
    )
    application = result.scalar_one_or_none()
    if application is None:
        raise ValueError("申请不存在")
    if application.status != ApplicationStatus.PENDING:
        raise ValueError("该申请已被处理")

    now = datetime.now()
    if approved:
        if admin_role is None:
            raise ValueError("通过申请时必须指定 admin_role")
        application.status = ApplicationStatus.APPROVED

        # 检查是否已有 Administrator 记录
        admin_result = await db.execute(
            select(Administrator).where(Administrator.user_id == application.user_id)
        )
        administrator = admin_result.scalar_one_or_none()

        if administrator is None:
            administrator = Administrator(
                user_id=application.user_id,
                admin_role=AdminRole(admin_role),
                is_approved=True,
                approved_by=reviewer_id,
                approved_at=now,
            )
            db.add(administrator)
        else:
            administrator.admin_role = AdminRole(admin_role)
            administrator.is_approved = True
            administrator.approved_by = reviewer_id
            administrator.approved_at = now
    else:
        application.status = ApplicationStatus.REJECTED

    application.reviewed_by = reviewer_id
    application.reviewed_at = now

    await db.commit()
    await db.refresh(application)
    return application
