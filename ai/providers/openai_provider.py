"""
OpenAI Provider — 基于 OpenAI API 的实现。

支持 GPT-4o / GPT-4o-mini 等模型。
需要设置环境变量 OPENAI_API_KEY 和 OPENAI_BASE_URL（可选）。
"""

import os
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from ai.base import BaseASREngine, BaseLLMProvider, BaseOCREngine

# 使用环境变量配置，从 config 获取默认值
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")


class OpenAILLMProvider(BaseLLMProvider):
    """OpenAI 大语言模型实现。"""

    def __init__(self) -> None:
        """初始化 OpenAI 客户端。"""
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY 未设置，请在 .env 中配置")

        self.client = AsyncOpenAI(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL,
        )

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        """调用 OpenAI Chat Completion。

        Args:
            messages: 对话消息列表。
            temperature: 温度参数。
            max_tokens: 最大输出 token。

        Returns:
            模型回复文本。
        """
        response = await self.client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """调用 OpenAI Embedding。

        Args:
            texts: 要向量化的文本列表。

        Returns:
            向量列表。
        """
        response = await self.client.embeddings.create(
            model=OPENAI_EMBED_MODEL,
            input=texts,
        )
        return [item.embedding for item in response.data]


class OpenAIOCREngine(BaseOCREngine):
    """OpenAI Vision OCR 实现 — 使用 GPT-4o 的视觉能力读取图片文字。"""

    def __init__(self) -> None:
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY 未设置")

        self.client = AsyncOpenAI(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL,
        )

    async def recognize(
        self,
        image_path: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """使用 GPT-4o Vision 识别图片中的文字。

        Args:
            image_path: 图片文件路径。
            options: 可选配置。

        Returns:
            识别结果字典。
        """
        import base64

        # 读取图片并 base64 编码
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        ext = os.path.splitext(image_path)[1].lower().replace(".", "")
        mime_map = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}
        mime_type = mime_map.get(ext, "jpeg")

        response = await self.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "请提取这张图片中的所有文字，保持原有格式和排版。只输出文字，不要添加任何解释。",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{mime_type};base64,{image_data}",
                            },
                        },
                    ],
                }
            ],
            max_tokens=4000,
        )
        text = response.choices[0].message.content or ""
        return {"text": text, "confidence": 0.95, "language": options.get("language", "auto") if options else "auto"}


class OpenAIASREngine(BaseASREngine):
    """OpenAI ASR 实现 — 使用 Whisper API。"""

    def __init__(self) -> None:
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY 未设置")

        self.client = AsyncOpenAI(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL,
        )

    async def transcribe(
        self,
        audio_path: str,
        language: str = "zh",
    ) -> Dict[str, Any]:
        """使用 Whisper API 转录音频。

        Args:
            audio_path: 音频文件路径。
            language: 语言代码。

        Returns:
            转录结果字典。
        """
        with open(audio_path, "rb") as f:
            response = await self.client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language=language,
            )
        return {
            "text": response.text,
            "language": language,
        }
