"""
Mock Provider — 开发环境使用的模拟 AI 实现。

所有方法返回模拟数据，无需 API Key，方便本地开发和测试。
"""

from typing import Any, Dict, List, Optional

from ai.base import BaseASREngine, BaseLLMProvider, BaseOCREngine


class MockLLMProvider(BaseLLMProvider):
    """模拟大语言模型 — 返回预设回复。"""

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        """模拟对话：返回最后一条用户消息的回显。

        Args:
            messages: 对话消息列表。
            temperature: 温度参数（mock 忽略）。
            max_tokens: 最大 token 数（mock 忽略）。

        Returns:
            模拟回复文本。
        """
        last_msg = messages[-1]["content"] if messages else ""
        return f"[Mock LLM] 收到您的消息: {last_msg[:100]}...（模拟回复）"

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """模拟向量化：返回固定维度随机向量。

        Args:
            texts: 文本列表。

        Returns:
            模拟向量列表（维度 768）。
        """
        import random
        return [[random.random() for _ in range(768)] for _ in texts]


class MockOCREngine(BaseOCREngine):
    """模拟 OCR — 返回固定识别结果。"""

    async def recognize(
        self,
        image_path: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """模拟 OCR 识别。

        Args:
            image_path: 图片路径。
            options: 可选配置（mock 忽略）。

        Returns:
            模拟识别结果。
        """
        return {
            "text": f"[Mock OCR] 从 {image_path} 中识别到的模拟文字内容",
            "confidence": 0.95,
            "language": "zh",
        }


class MockASREngine(BaseASREngine):
    """模拟 ASR — 返回固定转录结果。"""

    async def transcribe(
        self,
        audio_path: str,
        language: str = "zh",
    ) -> Dict[str, Any]:
        """模拟语音转录。

        Args:
            audio_path: 音频路径。
            language: 语言代码（mock 忽略）。

        Returns:
            模拟转录结果。
        """
        return {
            "text": f"[Mock ASR] 从 {audio_path} 转录的模拟文字内容",
            "language": language,
            "duration_seconds": 30.0,
        }
