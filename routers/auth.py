"""
统一认证路由 — 登录、注册、JWT 验证、管理员申请审批。
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

import jwt
from models.database import get_db
from models.admin_application import AdminApplication, ApplicationStatus
from models.user import AdminRole, Administrator
from service.auth_service import (
    authenticate_user,
    create_access_token,
    register_resident,
    register_provider,
    init_super_admin,
    apply_admin,
    approve_admin_application,
    SECRET_KEY,
    ALGORITHM,
)

router = APIRouter(prefix="/auth", tags=["认证"])
security = HTTPBearer()


class LoginRequest(BaseModel):
    """登录请求。"""
    phone: str = Field(..., min_length=3, max_length=20, description="手机号")
    password: str = Field(..., min_length=3, description="密码")


class ResidentRegisterRequest(BaseModel):
    """居民注册请求。"""
    phone: str = Field(..., min_length=11, max_length=11, description="手机号")
    nickname: str = Field(..., min_length=1, max_length=50, description="昵称")
    password: str = Field(..., min_length=6, description="密码")
    address: Optional[str] = Field(default=None, description="地址")
    latitude: Optional[float] = Field(default=None, description="纬度")
    longitude: Optional[float] = Field(default=None, description="经度")


class ProviderRegisterRequest(BaseModel):
    """服务者注册请求。"""
    phone: str = Field(..., min_length=11, max_length=11, description="手机号")
    nickname: str = Field(..., min_length=1, max_length=50, description="昵称")
    password: str = Field(..., min_length=6, description="密码")
    skills: Optional[str] = Field(default=None, description="技能标签，逗号分隔")
    address: Optional[str] = Field(default=None, description="服务地址")
    latitude: Optional[float] = Field(default=None, description="纬度")
    longitude: Optional[float] = Field(default=None, description="经度")


class ApiResponse(BaseModel):
    """统一 API 响应。"""
    code: int = Field(default=200)
    message: str = Field(default="成功")
    data: Optional[object] = Field(default=None)


@router.post("/login", response_model=ApiResponse)
async def login(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """登录接口，返回 JWT token。"""
    user = await authenticate_user(db, req.phone, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="手机号或密码错误")

    token = create_access_token(data={"sub": str(user.id), "role": user.role.value})
    return ApiResponse(
        code=200,
        message="登录成功",
        data={
            "user_id": user.id,
            "nickname": user.nickname,
            "role": user.role.value,
            "access_token": token,
            "token_type": "bearer",
        },
    )


@router.post("/login/resident", response_model=ApiResponse)
async def login_resident(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """居民登录接口。"""
    user = await authenticate_user(db, req.phone, req.password)
    if not user or user.role.value != "RESIDENT":
        raise HTTPException(status_code=401, detail="手机号或密码错误，或非居民账号")

    token = create_access_token(data={"sub": str(user.id), "role": user.role.value})
    return ApiResponse(
        code=200,
        message="登录成功",
        data={
            "user_id": user.id,
            "nickname": user.nickname,
            "role": user.role.value,
            "access_token": token,
            "token_type": "bearer",
        },
    )


@router.post("/login/provider", response_model=ApiResponse)
async def login_provider(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """服务者登录接口。"""
    user = await authenticate_user(db, req.phone, req.password)
    if not user or user.role.value != "PROVIDER":
        raise HTTPException(status_code=401, detail="手机号或密码错误，或非服务者账号")

    token = create_access_token(data={"sub": str(user.id), "role": user.role.value})
    return ApiResponse(
        code=200,
        message="登录成功",
        data={
            "user_id": user.id,
            "nickname": user.nickname,
            "role": user.role.value,
            "access_token": token,
            "token_type": "bearer",
        },
    )


@router.post("/register/resident", response_model=ApiResponse)
async def register_resident_endpoint(
    req: ResidentRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """居民注册。"""
    from repository.user_repo import user_repo
    existing = await user_repo.get_by_phone(db, req.phone)
    if existing:
        raise HTTPException(status_code=400, detail="手机号已注册")

    user = await register_resident(
        db,
        phone=req.phone,
        nickname=req.nickname,
        password=req.password,
        address=req.address,
        latitude=req.latitude,
        longitude=req.longitude,
    )

    token = create_access_token(data={"sub": str(user.id), "role": user.role.value})
    return ApiResponse(
        code=201,
        message="居民注册成功",
        data={
            "user_id": user.id,
            "nickname": user.nickname,
            "role": user.role.value,
            "access_token": token,
            "token_type": "bearer",
        },
    )


@router.post("/register/provider", response_model=ApiResponse)
async def register_provider_endpoint(
    req: ProviderRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """服务者注册。"""
    from repository.user_repo import user_repo
    existing = await user_repo.get_by_phone(db, req.phone)
    if existing:
        raise HTTPException(status_code=400, detail="手机号已注册")

    user = await register_provider(
        db,
        phone=req.phone,
        nickname=req.nickname,
        password=req.password,
        skills=req.skills,
        address=req.address,
        latitude=req.latitude,
        longitude=req.longitude,
    )

    token = create_access_token(data={"sub": str(user.id), "role": user.role.value})
    return ApiResponse(
        code=201,
        message="服务者注册成功",
        data={
            "user_id": user.id,
            "nickname": user.nickname,
            "role": user.role.value,
            "access_token": token,
            "token_type": "bearer",
        },
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    """JWT 验证依赖，返回当前用户。"""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
        from repository.user_repo import user_repo
        user = await user_repo.get_by_id(db, user_id)
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="令牌已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效令牌")


# ==================== 管理员申请 ====================

class AdminApplyRequest(BaseModel):
    """管理员申请请求。"""
    reason: str = Field(..., min_length=10, max_length=500, description="申请理由")


@router.post("/apply-admin", response_model=ApiResponse)
async def apply_admin_endpoint(
    req: AdminApplyRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """提交管理员申请。"""
    try:
        application = await apply_admin(db, current_user.id, req.reason)
        return ApiResponse(
            code=200,
            message="申请已提交，请等待超级管理员审批",
            data={
                "application_id": application.id,
                "status": application.status.value,
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== 超级管理员审批 ====================

class ApproveApplicationRequest(BaseModel):
    """审批申请请求（SUPER_ADMIN 专用）。"""
    approved: bool = Field(..., description="是否通过")
    admin_role: Optional[str] = Field(
        default=None,
        description="管理员级别: ADMIN_L1 / ADMIN_L2 / ADMIN_L3（通过时必填）",
    )


def _require_super_admin(current_user) -> None:
    """校验当前用户是否为已审批的 SUPER_ADMIN。"""
    if current_user.role.value != "ADMIN":
        raise HTTPException(status_code=403, detail="无管理员权限")

    # 注意：current_user 不一定加载了 administrator 关系
    # 此处简单通过 role 判断，admin_role 需要从 DB 查
    raise HTTPException(status_code=403, detail="需要超级管理员权限")


async def _get_admin_record(db, user_id: int) -> Optional[Administrator]:
    """获取管理员记录。"""
    result = await db.execute(
        select(Administrator).where(Administrator.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def require_super_admin(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """依赖注入：校验当前用户为已审批的 SUPER_ADMIN。"""
    admin = await _get_admin_record(db, current_user.id)
    if not admin or not admin.is_approved or admin.admin_role != AdminRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="需要超级管理员权限")
    return current_user


async def require_admin_l1(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """依赖注入：校验当前用户为 L1 及以上已审批管理员。"""
    admin = await _get_admin_record(db, current_user.id)
    if not admin or not admin.is_approved:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user


async def require_admin_l2(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """依赖注入：校验当前用户为 L2 及以上已审批管理员。"""
    admin = await _get_admin_record(db, current_user.id)
    if not admin or not admin.is_approved:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    if admin.admin_role not in (AdminRole.SUPER_ADMIN, AdminRole.ADMIN_L2, AdminRole.ADMIN_L3):
        raise HTTPException(status_code=403, detail="需要 L2 及以上管理员权限")
    return current_user


async def require_admin_l3(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """依赖注入：校验当前用户为 L3 及以上已审批管理员。"""
    admin = await _get_admin_record(db, current_user.id)
    if not admin or not admin.is_approved:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    if admin.admin_role not in (AdminRole.SUPER_ADMIN, AdminRole.ADMIN_L3):
        raise HTTPException(status_code=403, detail="需要 L3 及以上管理员权限")
    return current_user


@router.get("/admin/applications", response_model=ApiResponse)
async def get_applications(
    status: Optional[str] = None,
    current_user=Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """查看管理员申请列表（SUPER_ADMIN 专用）。"""
    stmt = select(AdminApplication)
    if status:
        stmt = stmt.where(AdminApplication.status == status)
    stmt = stmt.order_by(AdminApplication.created_at.desc())

    result = await db.execute(stmt)
    applications = result.scalars().all()

    return ApiResponse(
        code=200,
        message="查询成功",
        data={
            "total": len(applications),
            "applications": [
                {
                    "id": a.id,
                    "user_id": a.user_id,
                    "applicant_name": a.applicant.nickname if a.applicant else "",
                    "applicant_phone": a.applicant.phone if a.applicant else "",
                    "reason": a.reason,
                    "status": a.status.value,
                    "reviewed_by": a.reviewed_by,
                    "reviewed_at": a.reviewed_at.isoformat() if a.reviewed_at else None,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in applications
            ],
        },
    )


@router.post("/admin/applications/{application_id}/approve", response_model=ApiResponse)
async def approve_application(
    application_id: int,
    req: ApproveApplicationRequest,
    current_user=Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """审批管理员申请（SUPER_ADMIN 专用）。"""
    if req.approved and req.admin_role is None:
        raise HTTPException(status_code=400, detail="通过申请时必须指定 admin_role")

    if req.approved and req.admin_role not in ("ADMIN_L1", "ADMIN_L2", "ADMIN_L3"):
        raise HTTPException(status_code=400, detail="admin_role 必须为 ADMIN_L1 / ADMIN_L2 / ADMIN_L3")

    try:
        application = await approve_admin_application(
            db,
            application_id=application_id,
            reviewer_id=current_user.id,
            approved=req.approved,
            admin_role=req.admin_role if req.approved else None,
        )
        return ApiResponse(
            code=200,
            message="审批完成",
            data={
                "application_id": application.id,
                "status": application.status.value,
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
