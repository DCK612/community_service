"""
社区服务平台 - 全局配置模块
所有业务阈值通过环境变量可配置，支持不同 AI 厂商动态切换。
"""

import os
from dotenv import load_dotenv

# 加载 .env 文件（如果存在）
load_dotenv()


# ==================== 数据库配置 ====================

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./community_service.db"
)


# ==================== AI 厂商配置 ====================

AI_PROVIDER: str = os.getenv("AI_PROVIDER", "mock")

# OpenAI
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# DeepSeek
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# 腾讯混元
HUNYUAN_SECRET_ID: str = os.getenv("HUNYUAN_SECRET_ID", "")
HUNYUAN_SECRET_KEY: str = os.getenv("HUNYUAN_SECRET_KEY", "")
HUNYUAN_MODEL: str = os.getenv("HUNYUAN_MODEL", "hunyuan-lite")

# 小米 MiMo（兼容 OpenAI 协议）
MIMO_API_KEY: str = os.getenv("MIMO_API_KEY", "")
MIMO_BASE_URL: str = os.getenv("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1")
MIMO_MODEL: str = os.getenv("MIMO_MODEL", "mimo-v2.5-pro")


# ==================== 业务阈值配置 ====================

# 信用分阈值：低于此分数触发黑名单审查
CREDIT_SCORE_THRESHOLD: int = int(os.getenv("CREDIT_SCORE_THRESHOLD", "30"))

# 投诉次数阈值：累计投诉超过此次数自动拉黑
COMPLAINT_COUNT_THRESHOLD: int = int(os.getenv("COMPLAINT_COUNT_THRESHOLD", "3"))

# 7天内超时订单次数阈值
TIMEOUT_COUNT_THRESHOLD: int = int(os.getenv("TIMEOUT_COUNT_THRESHOLD", "3"))

# 超时检测窗口（天）
TIMEOUT_WINDOW_DAYS: int = int(os.getenv("TIMEOUT_WINDOW_DAYS", "7"))

# 订单各阶段超时阈值（分钟）
ORDER_ACCEPT_TIMEOUT_MINUTES: int = int(os.getenv("ORDER_ACCEPT_TIMEOUT_MINUTES", "30"))
ORDER_START_TIMEOUT_MINUTES: int = int(os.getenv("ORDER_START_TIMEOUT_MINUTES", "60"))
ORDER_FINISH_TIMEOUT_MINUTES: int = int(os.getenv("ORDER_FINISH_TIMEOUT_MINUTES", "480"))
ORDER_CONFIRM_TIMEOUT_MINUTES: int = int(os.getenv("ORDER_CONFIRM_TIMEOUT_MINUTES", "1440"))


# ==================== 派单引擎权重 ====================

DISPATCH_WEIGHT_CREDIT_SCORE: float = float(
    os.getenv("DISPATCH_WEIGHT_CREDIT_SCORE", "0.5")
)
DISPATCH_WEIGHT_ONGOING_ORDERS: float = float(
    os.getenv("DISPATCH_WEIGHT_ONGOING_ORDERS", "5.0")
)
DISPATCH_WEIGHT_DISTANCE_MAX: float = float(
    os.getenv("DISPATCH_WEIGHT_DISTANCE_MAX", "20.0")
)
DISPATCH_WEIGHT_SKILL_MATCH: float = float(
    os.getenv("DISPATCH_WEIGHT_SKILL_MATCH", "10.0")
)
DISPATCH_WEIGHT_TIMEOUT_PENALTY: float = float(
    os.getenv("DISPATCH_WEIGHT_TIMEOUT_PENALTY", "5.0")
)


# ==================== 信用分加减分规则 ====================

SCORE_QUICK_ACCEPT_BONUS: int = int(os.getenv("SCORE_QUICK_ACCEPT_BONUS", "3"))
SCORE_COMPLAINT_PENALTY: int = int(os.getenv("SCORE_COMPLAINT_PENALTY", "-20"))
SCORE_TIMEOUT_PENALTY: int = int(os.getenv("SCORE_TIMEOUT_PENALTY", "-10"))
SCORE_GOOD_REVIEW_BONUS: int = int(os.getenv("SCORE_GOOD_REVIEW_BONUS", "5"))

# 评价权重
REVIEW_WEIGHT_RESIDENT: float = float(os.getenv("REVIEW_WEIGHT_RESIDENT", "0.7"))
REVIEW_WEIGHT_PROVIDER: float = float(os.getenv("REVIEW_WEIGHT_PROVIDER", "0.3"))
