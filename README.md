# AI+社区服务平台

基于 FastAPI 的社区服务 O2O 平台，支持居民/服务者双人群模型、订单全生命周期管理、双端互评打分、智能派单引擎和 AI 抽象层。

## 项目架构

```
community_service/
├── ai/                        # AI 抽象层
│   ├── base.py                #   抽象基类 (LLM/OCR/ASR)
│   ├── factory.py             #   工厂：按 AI_PROVIDER 动态加载
│   └── providers/
│       ├── mock_provider.py   #   Mock 实现（开发用）
│       └── openai_provider.py #   OpenAI 实现
├── models/                    # 数据模型 (SQLAlchemy ORM)
│   ├── database.py            #   异步引擎 + Session
│   ├── user.py                #   用户模型（双人群）
│   ├── order.py               #   订单模型（全生命周期）
│   └── review.py              #   评价模型（双端互评）
├── repository/                # 数据访问层 (DAO)
│   ├── base.py                #   泛型 CRUD 基类
│   ├── user_repo.py           #   用户数据访问
│   ├── order_repo.py          #   订单数据访问
│   ├── review_repo.py         #   评价数据访问
│   └── blacklist_repo.py      #   黑名单数据访问
├── service/                   # 核心业务逻辑层
│   ├── order_service.py       #   订单创建与状态流转
│   ├── dispatch_service.py    #   派单引擎（加权评分）
│   ├── review_service.py      #   双端互评 + 信用分计算
│   ├── blacklist_service.py   #   自动/手动拉黑
│   └── timer_service.py       #   耗时计算与超时检测
├── routers/                   # API 路由层
│   ├── resident.py            #   居民端 /resident
│   ├── provider.py            #   服务者端 /provider
│   └── admin.py               #   管理端 /admin
├── config.py                  # 全局配置（环境变量）
├── main.py                    # FastAPI 入口
├── init_db.py                 # 建表 + 测试数据
├── requirements.txt           # Python 依赖
├── .env.example               # 环境变量模板
└── README.md                  # 本文件
```

## 架构分层

| 层 | 职责 | 依赖 |
|---|---|---|
| **routers** | 请求校验、路由分发、响应格式化 | service |
| **service** | 核心业务逻辑、事务编排 | repository |
| **repository** | 数据库 CRUD、查询封装 | SQLAlchemy |
| **models** | ORM 定义、类型约束 | SQLAlchemy |

## 快速启动

### 1. 环境准备

```bash
# Python 3.10+
python --version

# 克隆项目
git clone https://github.com/DCK612/community_service.git
cd community_service
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env（可选，默认值即可运行）
# AI_PROVIDER=mock    # 开发用 Mock
```

### 4. 初始化数据库

```bash
python init_db.py
```

### 5. 启动服务

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 6. 访问 API 文档

- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

## API 概览

### 居民端 `/resident`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/register` | 注册居民账号 |
| POST | `/orders` | 创建服务订单 |
| GET | `/orders` | 查询我的订单 |
| POST | `/orders/{id}/confirm` | 确认服务完成 |
| POST | `/reviews` | 评价服务者 |

### 服务者端 `/provider`

| 方法 | 路径 | 说明 |
|------|------|------|
| PUT | `/status` | 切换在线状态 |
| GET | `/orders/available` | 可接订单（按优先级排序） |
| POST | `/orders/{id}/accept` | 接单 |
| POST | `/orders/{id}/start` | 开始服务 |
| POST | `/orders/{id}/finish` | 完成服务 |
| GET | `/profile/score` | 信用分明细 |
| POST | `/reviews` | 评价居民 |

### 管理端 `/admin`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/dashboard` | 运营仪表盘 |
| GET | `/blacklist` | 黑名单列表 |
| POST | `/providers/{id}/blacklist` | 手动拉黑 |
| POST | `/scan-blacklist` | 全量自动拉黑扫描 |

## 核心机制

### 派单引擎

优先级评分公式：
```
score = credit_score × 0.5 + (5 - 在途订单数) × 5 + 距离分(最大20) + 技能匹配 × 10 - 超时次数 × 5
```

- 过滤：黑名单、OFFLINE、BUSY（在途 ≥ 5）
- 距离使用 Haversine 公式计算

### 信用分计算

```
final_score = 居民评价均分 × 0.7 + 被评均分 × 0.3 + 系统加减分
```

系统自动加减分：
- 30分钟内接单：+3
- 好评（均分 ≥ 4）：+5
- 被投诉：-20/次
- 超时：-10/次

### 黑名单机制

| 条件 | 动作 |
|------|------|
| 信用分 < 30 | 永久拉黑 |
| 投诉 ≥ 3 次 | 永久拉黑 |
| 7天超时 ≥ 3 次 | 临时冻结 7 天 |

## AI 厂商切换

通过 `.env` 中的 `AI_PROVIDER` 环境变量切换：

```bash
# 开发 Mock（默认，无需 API Key）
AI_PROVIDER=mock

# OpenAI
AI_PROVIDER=openai
OPENAI_API_KEY=sk-xxx
OPENAI_MODEL=gpt-4o-mini
```

新增厂商只需：
1. 在 `ai/providers/` 下创建实现类（继承 `BaseLLMProvider` 等基类）
2. 在 `ai/factory.py` 的映射表中注册即可

## 统一响应格式

```json
{
  "code": 200,
  "message": "成功",
  "data": { ... }
}
```

## 技术栈

- **框架**: FastAPI (Python)
- **ORM**: SQLAlchemy 2.0 (异步)
- **数据库**: SQLite (开发) / PostgreSQL (生产)
- **验证**: Pydantic v2
- **AI**: 可替换抽象层（Mock / OpenAI / DeepSeek / Hunyuan）
