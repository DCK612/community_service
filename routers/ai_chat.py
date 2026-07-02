"""
AI 聊天路由 — 智能问答助手。

POST /ai/chat
"""

from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel, Field

from service import ai_chat_service

router = APIRouter(prefix="/ai", tags=["AI助手"])


class ChatRequest(BaseModel):
    """聊天请求体。"""
    messages: List[Dict[str, str]] = Field(
        ..., description="对话消息列表，[{'role':'user/assistant','content':'...'}]"
    )
    temperature: float = Field(default=0.7, description="温度参数 (0-2)")


@router.post("/chat")
async def ai_chat(body: ChatRequest) -> dict[str, Any]:
    """发送消息给 AI 助手，获取回复。

    示例请求：
    ```json
    {
      "messages": [
        {"role": "user", "content": "水管漏水大概多少钱？"}
      ]
    }
    ```

    返回：
    ```json
    {
      "code": 200,
      "data": {"reply": "水管漏水维修参考价格在 ¥80~200/次..."}
    }
    ```
    """
    return await ai_chat_service.chat(
        messages=body.messages,
        temperature=body.temperature,
    )
