import os
from typing import Any, Dict, List, Optional


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


PROVIDER_REGISTRY: Dict[str, Dict[str, Any]] = {
    "llama_cpp": {
        "id": "llama_cpp",
        "name": "本地 llama.cpp",
        "description": "本地部署的 GGUF 模型服务",
        "type": "openai_compatible",
        "base_url": _env("LLAMA_CPP_URL", "http://192.168.0.201:8081"),
        "api_key_env": None,
        "models": [],
        "default_model": None,
        "dynamic_models": True,
    },
    "deepseek": {
        "id": "deepseek",
        "name": "DeepSeek",
        "description": "DeepSeek 云端大模型",
        "type": "openai_compatible",
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "default_model": "deepseek-chat",
        "dynamic_models": False,
    },
    "openai": {
        "id": "openai",
        "name": "OpenAI",
        "description": "OpenAI GPT 系列",
        "type": "openai_compatible",
        "base_url": "https://api.openai.com",
        "api_key_env": "OPENAI_API_KEY",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1-mini"],
        "default_model": "gpt-4o-mini",
        "dynamic_models": True,
    },
    "moonshot": {
        "id": "moonshot",
        "name": "Moonshot (Kimi)",
        "description": "月之暗面 Kimi 大模型",
        "type": "openai_compatible",
        "base_url": "https://api.moonshot.cn",
        "api_key_env": "MOONSHOT_API_KEY",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        "default_model": "moonshot-v1-8k",
        "dynamic_models": False,
    },
    "zhipu": {
        "id": "zhipu",
        "name": "智谱 GLM",
        "description": "智谱 AI GLM 系列",
        "type": "openai_compatible",
        "base_url": "https://open.bigmodel.cn/api/paas",
        "api_key_env": "ZHIPU_API_KEY",
        "models": ["glm-4-flash", "glm-4", "glm-4-plus"],
        "default_model": "glm-4-flash",
        "dynamic_models": False,
    },
    "dashscope": {
        "id": "dashscope",
        "name": "通义千问",
        "description": "阿里云通义千问",
        "type": "openai_compatible",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode",
        "api_key_env": "DASHSCOPE_API_KEY",
        "models": ["qwen-turbo", "qwen-plus", "qwen-max"],
        "default_model": "qwen-turbo",
        "dynamic_models": False,
    },
    "siliconflow": {
        "id": "siliconflow",
        "name": "SiliconFlow",
        "description": "硅基流动模型聚合平台",
        "type": "openai_compatible",
        "base_url": "https://api.siliconflow.cn",
        "api_key_env": "SILICONFLOW_API_KEY",
        "models": [
            "deepseek-ai/DeepSeek-V3",
            "Qwen/Qwen2.5-72B-Instruct",
            "meta-llama/Meta-Llama-3.1-8B-Instruct",
        ],
        "default_model": "deepseek-ai/DeepSeek-V3",
        "dynamic_models": True,
    },
    "custom": {
        "id": "custom",
        "name": "自定义 OpenAI 兼容",
        "description": "任意 OpenAI 兼容 API 端点",
        "type": "openai_compatible",
        "base_url": _env("CUSTOM_LLM_BASE_URL", ""),
        "api_key_env": "CUSTOM_LLM_API_KEY",
        "models": [],
        "default_model": _env("CUSTOM_LLM_MODEL", ""),
        "dynamic_models": True,
    },
}


def get_provider(provider_id: str) -> Optional[Dict[str, Any]]:
    return PROVIDER_REGISTRY.get(provider_id)


def list_providers(include_status: bool = True) -> List[Dict[str, Any]]:
    result = []
    for provider in PROVIDER_REGISTRY.values():
        item = {
            "id": provider["id"],
            "name": provider["name"],
            "description": provider["description"],
            "models": provider["models"],
            "default_model": provider["default_model"],
            "dynamic_models": provider.get("dynamic_models", False),
        }
        if include_status:
            item["api_key_configured"] = is_api_key_configured(provider["id"])
            item["base_url"] = provider["base_url"] if provider["id"] == "custom" else None
        result.append(item)
    return result


def is_api_key_configured(provider_id: str, override_key: Optional[str] = None) -> bool:
    if override_key:
        return True
    provider = get_provider(provider_id)
    if not provider:
        return False
    if not provider.get("api_key_env"):
        return True
    return bool(_env(provider["api_key_env"]))


def resolve_api_key(provider_id: str, override_key: Optional[str] = None) -> Optional[str]:
    if override_key:
        return override_key
    provider = get_provider(provider_id)
    if not provider:
        return None
    env_name = provider.get("api_key_env")
    if not env_name:
        return None
    return _env(env_name) or None


def resolve_base_url(provider_id: str, override_url: Optional[str] = None) -> str:
    if override_url:
        return override_url.rstrip("/")
    provider = get_provider(provider_id)
    if not provider:
        raise ValueError(f"未知 Provider: {provider_id}")
    return provider["base_url"].rstrip("/")


def resolve_model(provider_id: str, model: Optional[str] = None) -> Optional[str]:
    provider = get_provider(provider_id)
    if not provider:
        return model
    if model:
        return model
    return provider.get("default_model")
