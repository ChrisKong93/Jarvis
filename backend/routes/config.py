from typing import Any, Dict, Optional

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.crypto_utils import encrypt_api_key, decrypt_api_key
from backend.database import ModelConfig, get_db
from backend.providers import list_providers, llm_client
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
        ).order_by(ModelConfig.created_at.desc()).all()

        result = []
        for config in configs:
            result.append({
                "id": config.id,
                "name": config.name or "",
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
        name = data.get("name", "")
        api_key = data.get("api_key")
        base_url = data.get("base_url")
        default_model = data.get("default_model")
        max_tokens = data.get("max_tokens", 2048)
        agent_mode = data.get("agent_mode", "graph")

        if not provider_id or not provider_name:
            return {"error": "Provider ID 和名称不能为空"}, 400

        encrypted_api_key = encrypt_api_key(api_key) if api_key else ""

        new_config = ModelConfig(
            user_id=user["id"],
            name=name,
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

        return {
            "success": True,
            "message": "配置已添加",
            "config": {
                "id": new_config.id,
                "name": new_config.name or "",
                "provider_id": new_config.provider_id,
                "provider_name": new_config.provider_name,
                "api_key": "",
                "base_url": new_config.base_url,
                "default_model": new_config.default_model,
                "max_tokens": new_config.max_tokens,
                "agent_mode": new_config.agent_mode,
            },
        }

    @app.put("/api/user/config/{config_id}")
    async def update_user_config(config_id: int,
                                 request: Request,
                                 user: Dict = Depends(get_current_user),
                                 db: Session = Depends(get_db)):
        if not user:
            return {"error": "未登录"}, 401

        config = db.query(ModelConfig).filter(
            ModelConfig.id == config_id,
            ModelConfig.user_id == user["id"],
            ModelConfig.is_active == True,
        ).first()

        if not config:
            return {"error": "配置不存在"}, 404

        data = await request.json()
        config.provider_id = data.get("provider_id", config.provider_id)
        config.provider_name = data.get("provider_name", config.provider_name)
        config.name = data.get("name", config.name or "")
        config.base_url = data.get("base_url", config.base_url)
        config.default_model = data.get("default_model", config.default_model)
        config.max_tokens = data.get("max_tokens", config.max_tokens)
        config.agent_mode = data.get("agent_mode", config.agent_mode)

        api_key = data.get("api_key")
        if api_key:
            config.api_key = encrypt_api_key(api_key)

        db.commit()

        return {
            "success": True,
            "message": "配置已更新",
            "config": {
                "id": config.id,
                "name": config.name or "",
                "provider_id": config.provider_id,
                "provider_name": config.provider_name,
                "api_key": "",
                "base_url": config.base_url,
                "default_model": config.default_model,
                "max_tokens": config.max_tokens,
                "agent_mode": config.agent_mode,
            },
        }

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

    def _get_config_by_id(config_id: int, user_id: int,
                          db: Session) -> Optional[ModelConfig]:
        return db.query(ModelConfig).filter(
            ModelConfig.id == config_id,
            ModelConfig.user_id == user_id,
            ModelConfig.is_active == True,
        ).first()

    @app.get("/api/models")
    async def models(
        provider: str = DEFAULT_PROVIDER,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        config_id: Optional[int] = None,
        user: Dict = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        # 如果传了 config_id，优先从中读取 api_key/base_url
        if user and config_id:
            cfg = _get_config_by_id(config_id, user["id"], db)
            if cfg:
                if cfg.api_key:
                    api_key = decrypt_api_key(cfg.api_key)
                if cfg.base_url:
                    base_url = cfg.base_url
                provider = cfg.provider_id
        elif user and db and not api_key:
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
        config_id: Optional[int] = None,
        user: Dict = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        # 如果传了 config_id，优先从中读取 api_key/base_url
        if user and config_id:
            cfg = _get_config_by_id(config_id, user["id"], db)
            if cfg:
                if cfg.api_key:
                    api_key = decrypt_api_key(cfg.api_key)
                if cfg.base_url:
                    base_url = cfg.base_url
                provider = cfg.provider_id
        elif user and db and not api_key:
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
