"""
AI 抽象基类 — 定义 LLM / OCR / ASR 三大接口。

所有 AI 厂商实现必须继承这些基类，实现对应抽象方法。
通过工厂模式（factory.py）动态加载，支持运行时切换。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseLLMProvider(ABC):
    """大语言模型抽象基类。

    提供 chat（对话）和 embed（向量化）两个核心接口。
    """

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        """发送对话请求并返回模型回复文本。

        Args:
            messages: 对话消息列表，格式 [{"role": "user", "content": "..."}].
            temperature: 温度参数，控制随机性 (0-2)。
            max_tokens: 最大输出 token 数。

        Returns:
            模型生成的回复文本。
        """
        ...

    @abstractmethod
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """对文本列表进行向量化。

        Args:
            texts: 要向量化的文本列表。

        Returns:
            向量列表，每个向量为 float 列表。
        """
        ...


class BaseOCREngine(ABC):
    """OCR 文字识别抽象基类。

    用于身份证、发票、合同等场景的文字提取。
    """

    @abstractmethod
    async def recognize(
        self,
        image_path: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """识别图片中的文字。

        Args:
            image_path: 图片文件路径。
            options: 可选配置（语言、区域等）。

        Returns:
            识别结果字典，包含 text 和 confidence 等字段。
        """
        ...


class BaseASREngine(ABC):
    """语音识别抽象基类。

    用于语音转文字场景，如服务过程中的语音记录转录。
    """

    @abstractmethod
    async def transcribe(
        self,
        audio_path: str,
        language: str = "zh",
    ) -> Dict[str, Any]:
        """将音频文件转录为文字。

        Args:
            audio_path: 音频文件路径。
            language: 语言代码，默认 zh（中文）。

        Returns:
            转录结果字典，包含 text 字段。
        """
        ...
