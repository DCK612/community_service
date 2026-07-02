"""
社区服务平台 — FastAPI 入口。

启动命令：
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

API 文档：
    http://localhost:8000/docs    (Swagger)
    http://localhost:8000/redoc   (ReDoc)

路由分组：
    /resident   — 居民端
    /provider   — 服务者端
    /admin      — 管理端
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config
from models.database import engine, Base


# ==================== 生命周期 ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时的生命周期管理。

    启动时：创建所有数据库表（若不存在）。
    关闭时：释放数据库连接池。
    """
    # 启动：创建表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print(f"[启动] 数据库表已就绪，AI 厂商: {config.AI_PROVIDER}")

    yield

    # 关闭：释放连接
    await engine.dispose()
    print("[关闭] 数据库连接已释放")


# ==================== 应用实例 ====================

app = FastAPI(
    title="AI+社区服务平台",
    description="""
## 功能概览
- **双人群模型**：居民（RESIDENT）与服务者（PROVIDER）互斥
- **订单全生命周期**：PENDING → ACCEPTED → IN_PROGRESS → WAITING_CONFIRM → WAITING_REVIEW → COMPLETED
- **双端互评打分**：居民评服务者（5维度）+ 服务者评居民（3维度）
- **黑名单机制**：自动/手动拉黑，永久/临时冻结
- **派单引擎**：信用分+在途订单+距离+技能匹配+超时惩罚 加权排序
- **AI 抽象层**：支持 mock / openai 等厂商，通过环境变量切换
    """,
    version="1.0.0",
    lifespan=lifespan,
)


# ==================== 中间件 ====================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 路由注册 ====================

from routers.resident import router as resident_router
from routers.provider import router as provider_router
from routers.admin import router as admin_router
from routers.price_guide import router as price_guide_router
from routers.price_guide import admin_router as price_guide_admin_router

app.include_router(resident_router)
app.include_router(provider_router)
app.include_router(admin_router)
app.include_router(price_guide_router)
app.include_router(price_guide_admin_router)


# ==================== 健康检查 ====================

@app.get("/", tags=["系统"])
async def root():
    """根路径 — 健康检查。"""
    return {
        "code": 200,
        "message": "社区服务平台运行中",
        "data": {
            "version": "1.0.0",
            "ai_provider": config.AI_PROVIDER,
            "db_url": config.DATABASE_URL.replace(
                config.DATABASE_URL.split("@")[-2].split(":")[0],
                "***",
            ) if "@" in config.DATABASE_URL else config.DATABASE_URL,
        },
    }
