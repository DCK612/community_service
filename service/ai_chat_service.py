"""
AI 聊天服务 — 社区服务智能问答助手。

使用现有 AI 抽象层（get_llm_provider），支持 mock/openai/deepseek/hunyuan/mimo。
系统提示词定位为社区服务平台的专业客服助手。
"""

from typing import Any, Dict, List

from ai.factory import get_llm_provider

# 系统提示词：定位为社区服务智能助手
SYSTEM_PROMPT = """你是「智邻社区」平台的智能助手。你的职责是帮助用户解决社区服务相关问题。

平台功能概要：
- 居民端：提交报修/保洁/搬家/家教/养老等服务需求，查看订单，确认完成，评价服务者
- 服务者端：在线接单，查看可接订单，开始/结束服务，评价居民
- 管理端：Dashboard 数据看板，黑名单管理，定价参考管理

定价参考标准（示例）：
- 水管漏水维修：¥80~200/次
- 日常保洁：¥40~80/小时
- 小型搬家：¥200~400/车
- 小学辅导：¥60~120/小时
- 日常陪护：¥30~60/小时

回答规则：
1. 用友好、专业的语气回复，提供准确信息
2. 涉及平台操作时，给出具体步骤
3. 涉及价格时，给出参考范围并说明以实际为准
4. 遇到无法处理的问题，建议联系人工客服
5. 回复简洁，控制在 200 字以内"""


async def chat(
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
) -> Dict[str, Any]:
    """AI 对话接口。

    Args:
        messages: 对话历史，格式 [{"role": "user/assistant", "content": "..."}]
        temperature: 温度参数。

    Returns:
        统一响应格式 {"code": 200, "data": {"reply": "..."}}
    """
    # 构造完整消息列表：系统提示词 + 历史对话
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    provider = get_llm_provider()
    reply = await provider.chat(full_messages, temperature=temperature, max_tokens=500)

    return {
        "code": 200,
        "message": "success",
        "data": {"reply": reply},
    }
