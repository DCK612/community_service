"""
小米 MiMo Provider — 基于 MiMo API 的实现。

MiMo 兼容 OpenAI API 格式，通过 AsyncOpenAI 客户端调用。
Base URL: https://api.xiaomimimo.com/v1
推荐模型: mimo-v2.5-pro
"""

import os
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from ai.base import BaseASREngine, BaseLLMProvider, BaseOCREngine

# 从环境变量获取 MiMo 配置
MIMO_API_KEY = os.getenv("MIMO_API_KEY", "")
MIMO_BASE_URL = os.getenv("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1")
MIMO_MODEL = os.getenv("MIMO_MODEL", "mimo-v2.5-pro")
MIMO_EMBED_MODEL = os.getenv("MIMO_EMBED_MODEL", "mimo-v2.5")


class MiMoLLMProvider(BaseLLMProvider):
    """小米 MiMo 大语言模型实现。

    MiMo v2.5 系列支持思考模式（thinking）和流式输出，
    默认 temperature=1.0，top_p=0.95（与 OpenAI 行为略有差异）。
    """

    def __init__(self) -> None:
        """初始化 MiMo 客户端。"""
        if not MIMO_API_KEY:
            raise ValueError(
                "MIMO_API_KEY 未设置，请在 .env 中配置。"
                "前往 https://mimo.mi.com 控制台获取 API Key（格式：sk-xxxxx）。"
            )

        self.client = AsyncOpenAI(
            api_key=MIMO_API_KEY,
            base_url=MIMO_BASE_URL,
        )

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 1.0,
        max_tokens: int = 2000,
    ) -> str:
        """调用 MiMo Chat Completion。

        MiMo v2.5 默认 temperature=1.0, top_p=0.95。
        思考模式下 temperature 和 top_p 不可自定义。

        Args:
            messages: 对话消息列表。
            temperature: 温度参数（MiMo 默认 1.0）。
            max_tokens: 最大输出 token（MiMo 默认 32768）。

        Returns:
            模型回复文本。
        """
        response = await self.client.chat.completions.create(
            model=MIMO_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=0.95,
        )
        return response.choices[0].message.content or ""

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """调用 MiMo Embedding。

        Args:
            texts: 要向量化的文本列表。

        Returns:
            向量列表。
        """
        response = await self.client.embeddings.create(
            model=MIMO_EMBED_MODEL,
            input=texts,
        )
        return [item.embedding for item in response.data]


class MiMoOCREngine(BaseOCREngine):
    """MiMo Vision OCR — 利用 MiMo 多模态能力识别图片文字。"""

    def __init__(self) -> None:
        if not MIMO_API_KEY:
            raise ValueError("MIMO_API_KEY 未设置")

        self.client = AsyncOpenAI(
            api_key=MIMO_API_KEY,
            base_url=MIMO_BASE_URL,
        )

    async def recognize(
        self,
        image_path: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """使用 MiMo 视觉能力识别图片中的文字。

        Args:
            image_path: 图片文件路径。
            options: 可选配置（language 等）。

        Returns:
            识别结果字典，包含 text 和 confidence。
        """
        import base64

        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        ext = os.path.splitext(image_path)[1].lower().replace(".", "")
        mime_map = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}
        mime_type = mime_map.get(ext, "jpeg")

        response = await self.client.chat.completions.create(
            model=MIMO_MODEL,
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
        lang = options.get("language", "auto") if options else "auto"
        return {"text": text, "confidence": 0.95, "language": lang}


class MiMoASREngine(BaseASREngine):
    """MiMo TTS/ASR — 语音识别实现。

    注意：mimo-v2-tts 已于 2026.6.30 下线，请使用 mimo-v2.5-tts。
    """

    def __init__(self) -> None:
        if not MIMO_API_KEY:
            raise ValueError("MIMO_API_KEY 未设置")

        self.client = AsyncOpenAI(
            api_key=MIMO_API_KEY,
            base_url=MIMO_BASE_URL,
        )

    async def transcribe(
        self,
        audio_path: str,
        language: str = "zh",
    ) -> Dict[str, Any]:
        """使用 MiMo 语音识别转录音频。

        Args:
            audio_path: 音频文件路径。
            language: 语言代码，默认 zh。

        Returns:
            转录结果字典。
        """
        with open(audio_path, "rb") as f:
            response = await self.client.audio.transcriptions.create(
                model="mimo-v2.5-tts",
                file=f,
                language=language,
            )
        return {"text": response.text, "language": language}
