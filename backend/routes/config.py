from typing import Any, Dict, Optional

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.crypto_utils import encrypt_api_key, decrypt_api_key
from backend.database import ModelConfig, get_db
from backend.providers import LLMError, list_providers, llm_client
from backend.routes.helpers import DEFAULT_PROVIDER, extract_llm_options


def register_config_routes(app, get_current_user):
    """注册 Provider / 模型 / 用户配置路由。"""

    @app.get("/api/providers")
    async def get_providers(user: Dict = Depends(get_current_user)):
        return {"providers": list_providers(), "default_provider": DEFAULT_PROVIDER}

    @app.get("/api/user/config")
    async def get_user_config(user: Dict = Depends(get_current_user),
                              db: Session = Depends(get_db)):
        if not user:
            return {"config": None}

        configs = db.query(ModelConfig).filter(
            ModelConfig.user_id == user["id"],
            ModelConfig.is_active == True
        ).all()

        result = []
        for config in configs:
            result.append({
                "id": config.id,
                "provider_id": config.provider_id,
                "provider_name": config.provider_name,
                "api_key": "",
                "base_url": config.base_url,
                "default_model": config.default_model,
                "max_tokens": config.max_tokens,
                "agent_mode": config.agent_mode,
            })

        return {"configs": result}

    @app.post("/api/user/config")
    async def save_user_config(request: Request,
                               user: Dict = Depends(get_current_user),
                               db: Session = Depends(get_db)):
        if not user:
            return {"error": "未登录"}, 401

        data = await request.json()
        provider_id = data.get("provider_id")
        provider_name = data.get("provider_name")
        api_key = data.get("api_key")
        base_url = data.get("base_url")
        default_model = data.get("default_model")
        max_tokens = data.get("max_tokens", 2048)
        agent_mode = data.get("agent_mode", "graph")

        if not provider_id or not provider_name:
            return {"error": "Provider ID 和名称不能为空"}, 400

        existing_config = db.query(ModelConfig).filter(
            ModelConfig.user_id == user["id"],
            ModelConfig.provider_id == provider_id,
            ModelConfig.is_active == True
        ).first()

        encrypted_api_key = encrypt_api_key(api_key) if api_key else ""

        if existing_config:
            existing_config.provider_name = provider_name
            if api_key:
                existing_config.api_key = encrypted_api_key
            existing_config.base_url = base_url
            existing_config.default_model = default_model
            existing_config.max_tokens = max_tokens
            existing_config.agent_mode = agent_mode
        else:
            new_config = ModelConfig(
                user_id=user["id"],
                provider_id=provider_id,
                provider_name=provider_name,
                api_key=encrypted_api_key,
                base_url=base_url,
                default_model=default_model,
                max_tokens=max_tokens,
                agent_mode=agent_mode,
            )
            db.add(new_config)

        db.commit()
        return {"success": True, "message": "配置已保存"}

    @app.delete("/api/user/config/{config_id}")
    async def delete_user_config(config_id: int,
                                 user: Dict = Depends(get_current_user),
                                 db: Session = Depends(get_db)):
        if not user:
            return {"error": "未登录"}, 401

        config = db.query(ModelConfig).filter(
            ModelConfig.id == config_id,
            ModelConfig.user_id == user["id"]
        ).first()

        if not config:
            return {"error": "配置不存在"}, 404

        config.is_active = False
        db.commit()
        return {"success": True, "message": "配置已删除"}

    @app.get("/api/models")
    async def models(
        provider: str = DEFAULT_PROVIDER,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        user: Dict = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        if user and db and not api_key:
            config_data = db.query(ModelConfig).filter(
                ModelConfig.user_id == user["id"],
                ModelConfig.provider_id == provider,
                ModelConfig.is_active == True
            ).first()
            if config_data and config_data.api_key:
                api_key = decrypt_api_key(config_data.api_key)
            if config_data and config_data.base_url:
                base_url = config_data.base_url

        model_list = llm_client.list_models(
            provider_id=provider, api_key=api_key, base_url=base_url)
        return {"models": model_list, "provider": provider}

    @app.get("/api/health")
    async def health(
        provider: str = DEFAULT_PROVIDER,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        user: Dict = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        if user and db and not api_key:
            config_data = db.query(ModelConfig).filter(
                ModelConfig.user_id == user["id"],
                ModelConfig.provider_id == provider,
                ModelConfig.is_active == True
            ).first()
            if config_data and config_data.api_key:
                api_key = decrypt_api_key(config_data.api_key)
            if config_data and config_data.base_url:
                base_url = config_data.base_url

        result = llm_client.health_check(
            provider_id=provider, api_key=api_key, base_url=base_url)
        if result["status"] == "ok":
            return {"status": "ok", "provider": provider, "detail": result}
        return {"status": "error", "message": result.get("message", "连接失败"),
                "provider": provider}
