from typing import Any, Dict, List, Optional


PROVIDER_REGISTRY: Dict[str, Dict[str, Any]] = {
    "llama_cpp": {
        "id": "llama_cpp",
        "name": "本地 llama.cpp",
        "description": "本地部署的 GGUF 模型服务",
        "type": "openai_compatible",
        "base_url": "http://192.168.0.201:8081",
        "api_key": "",
        "requires_api_key": False,
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
        "api_key": "",
        "requires_api_key": True,
        "api_key_env": None,
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "default_model": "deepseek-chat",
        "dynamic_models": True,
    },
    "openai": {
        "id": "openai",
        "name": "OpenAI",
        "description": "OpenAI GPT 系列",
        "type": "openai_compatible",
        "base_url": "https://api.openai.com",
        "api_key": "",
        "requires_api_key": True,
        "api_key_env": None,
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
        "api_key": "",
        "requires_api_key": True,
        "api_key_env": None,
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        "default_model": "moonshot-v1-8k",
        "dynamic_models": True,
    },
    "zhipu": {
        "id": "zhipu",
        "name": "智谱 GLM",
        "description": "智谱 AI GLM 系列",
        "type": "openai_compatible",
        "base_url": "https://open.bigmodel.cn/api/paas",
        "api_key": "",
        "requires_api_key": True,
        "api_key_env": None,
        "models": ["glm-4-flash", "glm-4", "glm-4-plus"],
        "default_model": "glm-4-flash",
        "dynamic_models": True,
    },
    "dashscope": {
        "id": "dashscope",
        "name": "通义千问",
        "description": "阿里云通义千问",
        "type": "openai_compatible",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode",
        "api_key": "",
        "requires_api_key": True,
        "api_key_env": None,
        "models": ["qwen-turbo", "qwen-plus", "qwen-max"],
        "default_model": "qwen-turbo",
        "dynamic_models": True,
    },
    "siliconflow": {
        "id": "siliconflow",
        "name": "SiliconFlow",
        "description": "硅基流动模型聚合平台",
        "type": "openai_compatible",
        "base_url": "https://api.siliconflow.cn",
        "api_key": "",
        "requires_api_key": True,
        "api_key_env": None,
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
        "base_url": "",
        "api_key": "",
        "requires_api_key": False,
        "api_key_env": None,
        "models": [],
        "default_model": "",
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
            item["base_url"] = provider["base_url"]
            item["api_key"] = provider.get("api_key", "")
            item["requires_api_key"] = provider.get("requires_api_key", False)
        result.append(item)
    return result


def is_api_key_configured(provider_id: str, override_key: Optional[str] = None) -> bool:
    if override_key:
        return True
    provider = get_provider(provider_id)
    if not provider:
        return False
    if provider.get("requires_api_key", False):
        return bool(provider.get("api_key"))
    return True


def resolve_api_key(provider_id: str, override_key: Optional[str] = None) -> Optional[str]:
    if override_key:
        return override_key
    provider = get_provider(provider_id)
    if not provider:
        return None
    return provider.get("api_key") or None


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



