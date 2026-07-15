import os
from typing import Any, Dict, List, Optional
import yaml


def _load_providers_config() -> Dict[str, Dict[str, Any]]:
    config_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")
    config_path = os.path.join(config_dir, "providers.yaml")
    
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    
    return {}


PROVIDER_CONFIG = _load_providers_config()


def _get_provider_config(provider_id: str, key: str, default: Any = None) -> Any:
    return PROVIDER_CONFIG.get(provider_id, {}).get(key, default)


PROVIDER_REGISTRY: Dict[str, Dict[str, Any]] = {
    "llama_cpp": {
        "id": "llama_cpp",
        "name": _get_provider_config("llama_cpp", "name", "本地 llama.cpp"),
        "description": _get_provider_config("llama_cpp", "description", "本地部署的 GGUF 模型服务"),
        "type": "openai_compatible",
        "base_url": _get_provider_config("llama_cpp", "base_url", "http://192.168.0.201:8081"),
        "api_key": _get_provider_config("llama_cpp", "api_key", ""),
        "requires_api_key": _get_provider_config("llama_cpp", "requires_api_key", False),
        "api_key_env": None,
        "models": _get_provider_config("llama_cpp", "models", []),
        "default_model": _get_provider_config("llama_cpp", "default_model"),
        "dynamic_models": _get_provider_config("llama_cpp", "dynamic_models", True),
    },
    "deepseek": {
        "id": "deepseek",
        "name": _get_provider_config("deepseek", "name", "DeepSeek"),
        "description": _get_provider_config("deepseek", "description", "DeepSeek 云端大模型"),
        "type": "openai_compatible",
        "base_url": _get_provider_config("deepseek", "base_url", "https://api.deepseek.com"),
        "api_key": _get_provider_config("deepseek", "api_key", ""),
        "requires_api_key": _get_provider_config("deepseek", "requires_api_key", True),
        "api_key_env": None,
        "models": _get_provider_config("deepseek", "models", ["deepseek-chat", "deepseek-reasoner"]),
        "default_model": _get_provider_config("deepseek", "default_model", "deepseek-chat"),
        "dynamic_models": _get_provider_config("deepseek", "dynamic_models", True),
    },
    "openai": {
        "id": "openai",
        "name": _get_provider_config("openai", "name", "OpenAI"),
        "description": _get_provider_config("openai", "description", "OpenAI GPT 系列"),
        "type": "openai_compatible",
        "base_url": _get_provider_config("openai", "base_url", "https://api.openai.com"),
        "api_key": _get_provider_config("openai", "api_key", ""),
        "requires_api_key": _get_provider_config("openai", "requires_api_key", True),
        "api_key_env": None,
        "models": _get_provider_config("openai", "models", ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1-mini"]),
        "default_model": _get_provider_config("openai", "default_model", "gpt-4o-mini"),
        "dynamic_models": _get_provider_config("openai", "dynamic_models", True),
    },
    "moonshot": {
        "id": "moonshot",
        "name": _get_provider_config("moonshot", "name", "Moonshot (Kimi)"),
        "description": _get_provider_config("moonshot", "description", "月之暗面 Kimi 大模型"),
        "type": "openai_compatible",
        "base_url": _get_provider_config("moonshot", "base_url", "https://api.moonshot.cn"),
        "api_key": _get_provider_config("moonshot", "api_key", ""),
        "requires_api_key": _get_provider_config("moonshot", "requires_api_key", True),
        "api_key_env": None,
        "models": _get_provider_config("moonshot", "models", ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"]),
        "default_model": _get_provider_config("moonshot", "default_model", "moonshot-v1-8k"),
        "dynamic_models": _get_provider_config("moonshot", "dynamic_models", True),
    },
    "zhipu": {
        "id": "zhipu",
        "name": _get_provider_config("zhipu", "name", "智谱 GLM"),
        "description": _get_provider_config("zhipu", "description", "智谱 AI GLM 系列"),
        "type": "openai_compatible",
        "base_url": _get_provider_config("zhipu", "base_url", "https://open.bigmodel.cn/api/paas"),
        "api_key": _get_provider_config("zhipu", "api_key", ""),
        "requires_api_key": _get_provider_config("zhipu", "requires_api_key", True),
        "api_key_env": None,
        "models": _get_provider_config("zhipu", "models", ["glm-4-flash", "glm-4", "glm-4-plus"]),
        "default_model": _get_provider_config("zhipu", "default_model", "glm-4-flash"),
        "dynamic_models": _get_provider_config("zhipu", "dynamic_models", True),
    },
    "dashscope": {
        "id": "dashscope",
        "name": _get_provider_config("dashscope", "name", "通义千问"),
        "description": _get_provider_config("dashscope", "description", "阿里云通义千问"),
        "type": "openai_compatible",
        "base_url": _get_provider_config("dashscope", "base_url", "https://dashscope.aliyuncs.com/compatible-mode"),
        "api_key": _get_provider_config("dashscope", "api_key", ""),
        "requires_api_key": _get_provider_config("dashscope", "requires_api_key", True),
        "api_key_env": None,
        "models": _get_provider_config("dashscope", "models", ["qwen-turbo", "qwen-plus", "qwen-max"]),
        "default_model": _get_provider_config("dashscope", "default_model", "qwen-turbo"),
        "dynamic_models": _get_provider_config("dashscope", "dynamic_models", True),
    },
    "siliconflow": {
        "id": "siliconflow",
        "name": _get_provider_config("siliconflow", "name", "SiliconFlow"),
        "description": _get_provider_config("siliconflow", "description", "硅基流动模型聚合平台"),
        "type": "openai_compatible",
        "base_url": _get_provider_config("siliconflow", "base_url", "https://api.siliconflow.cn"),
        "api_key": _get_provider_config("siliconflow", "api_key", ""),
        "requires_api_key": _get_provider_config("siliconflow", "requires_api_key", True),
        "api_key_env": None,
        "models": _get_provider_config("siliconflow", "models", [
            "deepseek-ai/DeepSeek-V3",
            "Qwen/Qwen2.5-72B-Instruct",
            "meta-llama/Meta-Llama-3.1-8B-Instruct",
        ]),
        "default_model": _get_provider_config("siliconflow", "default_model", "deepseek-ai/DeepSeek-V3"),
        "dynamic_models": _get_provider_config("siliconflow", "dynamic_models", True),
    },
    "custom": {
        "id": "custom",
        "name": _get_provider_config("custom", "name", "自定义 OpenAI 兼容"),
        "description": _get_provider_config("custom", "description", "任意 OpenAI 兼容 API 端点"),
        "type": "openai_compatible",
        "base_url": _get_provider_config("custom", "base_url", ""),
        "api_key": _get_provider_config("custom", "api_key", ""),
        "requires_api_key": _get_provider_config("custom", "requires_api_key", False),
        "api_key_env": None,
        "models": _get_provider_config("custom", "models", []),
        "default_model": _get_provider_config("custom", "default_model", ""),
        "dynamic_models": _get_provider_config("custom", "dynamic_models", True),
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



