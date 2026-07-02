"""
AI 工厂 — 根据 config.AI_PROVIDER 动态加载对应实现。

支持厂商：mock / openai / deepseek / hunyuan
新增厂商只需在 providers/ 下新增实现类，并在本文件注册即可。
"""

import importlib
from typing import Optional, Type

from ai.base import BaseASREngine, BaseLLMProvider, BaseOCREngine
from config import AI_PROVIDER


# ==================== 厂商注册表 ====================

# LLM 厂商映射：provider_name -> (module_path, class_name)
LLM_PROVIDERS = {
    "mock": ("ai.providers.mock_provider", "MockLLMProvider"),
    "openai": ("ai.providers.openai_provider", "OpenAILLMProvider"),
    "deepseek": ("ai.providers.deepseek_provider", "DeepSeekLLMProvider"),
    "hunyuan": ("ai.providers.hunyuan_provider", "HunyuanLLMProvider"),
    "mimo": ("ai.providers.mimo_provider", "MiMoLLMProvider"),
}

# OCR 厂商映射
OCR_PROVIDERS = {
    "mock": ("ai.providers.mock_provider", "MockOCREngine"),
    "openai": ("ai.providers.openai_provider", "OpenAIOCREngine"),
    "mimo": ("ai.providers.mimo_provider", "MiMoOCREngine"),
}

# ASR 厂商映射
ASR_PROVIDERS = {
    "mock": ("ai.providers.mock_provider", "MockASREngine"),
    "openai": ("ai.providers.openai_provider", "OpenAIASREngine"),
    "mimo": ("ai.providers.mimo_provider", "MiMoASREngine"),
}


# ==================== 动态加载 ====================

def _load_class(module_path: str, class_name: str) -> Type:
    """动态导入模块并获取类。

    Args:
        module_path: 模块路径（如 "ai.providers.mock_provider"）。
        class_name: 类名（如 "MockLLMProvider"）。

    Returns:
        类对象。

    Raises:
        ImportError: 模块或类不存在。
    """
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def get_llm_provider() -> BaseLLMProvider:
    """获取当前配置的 LLM 提供商实例。

    Returns:
        BaseLLMProvider 实例。

    Raises:
        ValueError: 未配置的 AI_PROVIDER。
    """
    provider_name = AI_PROVIDER.lower()

    if provider_name not in LLM_PROVIDERS:
        raise ValueError(
            f"不支持的 AI 厂商: {provider_name}，"
            f"可选: {list(LLM_PROVIDERS.keys())}"
        )

    module_path, class_name = LLM_PROVIDERS[provider_name]
    cls = _load_class(module_path, class_name)
    return cls()


def get_ocr_engine() -> BaseOCREngine:
    """获取当前配置的 OCR 引擎实例。

    Returns:
        BaseOCREngine 实例。
    """
    provider_name = AI_PROVIDER.lower()

    if provider_name not in OCR_PROVIDERS:
        # 回退到 mock
        module_path, class_name = OCR_PROVIDERS["mock"]
    else:
        module_path, class_name = OCR_PROVIDERS[provider_name]

    cls = _load_class(module_path, class_name)
    return cls()


def get_asr_engine() -> BaseASREngine:
    """获取当前配置的 ASR 引擎实例。

    Returns:
        BaseASREngine 实例。
    """
    provider_name = AI_PROVIDER.lower()

    if provider_name not in ASR_PROVIDERS:
        module_path, class_name = ASR_PROVIDERS["mock"]
    else:
        module_path, class_name = ASR_PROVIDERS[provider_name]

    cls = _load_class(module_path, class_name)
    return cls()
