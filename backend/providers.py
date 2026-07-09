import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


@dataclass
class ProviderConfig:
    id: str
    name: str
    type: str  # local | cloud
    base_url: str
    api_key_env: Optional[str] = None
    models: List[str] = field(default_factory=list)
    default_model: Optional[str] = None
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "base_url": self.base_url,
            "api_key_env": self.api_key_env,
            "models": self.models,
            "default_model": self.default_model,
            "description": self.description,
            "configured": self.is_configured(),
        }

    def is_configured(self) -> bool:
        if self.type == "local":
            return True
        if not self.api_key_env:
            return False
        return bool(os.getenv(self.api_key_env, "").strip())


PROVIDERS: Dict[str, ProviderConfig] = {
    "llama_cpp": ProviderConfig(
        id="llama_cpp",
        name="llama.cpp (本地)",
        type="local",
        base_url="http://192.168.0.201:8081",
        models=[],
        description="本地 GGUF 模型推理服务",
    ),
    "deepseek": ProviderConfig(
        id="deepseek",
        name="DeepSeek",
        type="cloud",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
        models=["deepseek-chat", "deepseek-reasoner"],
        default_model="deepseek-chat",
        description="DeepSeek 大模型",
    ),
    "openai": ProviderConfig(
        id="openai",
        name="OpenAI",
        type="cloud",
        base_url="https://api.openai.com",
        api_key_env="OPENAI_API_KEY",
        models=["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        default_model="gpt-4o-mini",
        description="OpenAI GPT 系列",
    ),
    "moonshot": ProviderConfig(
        id="moonshot",
        name="Moonshot (Kimi)",
        type="cloud",
        base_url="https://api.moonshot.cn",
        api_key_env="MOONSHOT_API_KEY",
        models=["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        default_model="moonshot-v1-8k",
        description="月之暗面 Kimi",
    ),
    "zhipu": ProviderConfig(
        id="zhipu",
        name="智谱 GLM",
        type="cloud",
        base_url="https://open.bigmodel.cn/api/paas",
        api_key_env="ZHIPU_API_KEY",
        models=["glm-4-flash", "glm-4", "glm-4-plus"],
        default_model="glm-4-flash",
        description="智谱 AI GLM 系列",
    ),
    "qwen": ProviderConfig(
        id="qwen",
        name="通义千问",
        type="cloud",
        base_url="https://dashscope.aliyuncs.com/compatible-mode",
        api_key_env="DASHSCOPE_API_KEY",
        models=["qwen-turbo", "qwen-plus", "qwen-max"],
        default_model="qwen-turbo",
        description="阿里云通义千问",
    ),
    "custom": ProviderConfig(
        id="custom",
        name="自定义 OpenAI 兼容",
        type="cloud",
        base_url="",
        api_key_env="CUSTOM_API_KEY",
        models=[],
        description="任意 OpenAI 兼容 API 端点",
    ),
}


class ProviderManager:
    def __init__(self, config_path: Path = CONFIG_PATH):
        self.config_path = config_path
        self._config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {
            "active_provider": "llama_cpp",
            "active_model": None,
            "providers": {},
        }

    def save_config(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self._config, f, ensure_ascii=False, indent=2)

    def get_active_provider_id(self) -> str:
        return self._config.get("active_provider", "llama_cpp")

    def get_active_model(self) -> Optional[str]:
        return self._config.get("active_model")

    def set_active(self, provider_id: str, model: Optional[str] = None) -> None:
        if provider_id not in PROVIDERS:
            raise ValueError(f"未知 Provider: {provider_id}")
        self._config["active_provider"] = provider_id
        self._config["active_model"] = model
        self.save_config()

    def get_provider(self, provider_id: Optional[str] = None) -> ProviderConfig:
        pid = provider_id or self.get_active_provider_id()
        provider = PROVIDERS.get(pid)
        if not provider:
            raise ValueError(f"未知 Provider: {pid}")
        return self._merge_overrides(provider)

    def _merge_overrides(self, provider: ProviderConfig) -> ProviderConfig:
        overrides = self._config.get("providers", {}).get(provider.id, {})
        if not overrides:
            return provider
        return ProviderConfig(
            id=provider.id,
            name=overrides.get("name", provider.name),
            type=provider.type,
            base_url=overrides.get("base_url", provider.base_url),
            api_key_env=provider.api_key_env,
            models=overrides.get("models", provider.models),
            default_model=overrides.get("default_model", provider.default_model),
            description=provider.description,
        )

    def get_api_key(self, provider: ProviderConfig) -> str:
        if provider.type == "local":
            return ""
        if not provider.api_key_env:
            return ""
        return os.getenv(provider.api_key_env, "").strip()

    def list_providers(self) -> List[Dict[str, Any]]:
        return [self.get_provider(pid).to_dict() for pid in PROVIDERS]

    def update_provider_settings(
        self,
        provider_id: str,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        models: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if provider_id not in PROVIDERS:
            raise ValueError(f"未知 Provider: {provider_id}")

        providers_cfg = self._config.setdefault("providers", {})
        entry = providers_cfg.setdefault(provider_id, {})

        if base_url is not None:
            entry["base_url"] = base_url
        if default_model is not None:
            entry["default_model"] = default_model
        if models is not None:
            entry["models"] = models

        self.save_config()
        return self.get_provider(provider_id).to_dict()

    def resolve_model(self, provider: ProviderConfig, model: Optional[str] = None) -> Optional[str]:
        if provider.type == "local":
            return None
        return model or self.get_active_model() or provider.default_model


provider_manager = ProviderManager()
