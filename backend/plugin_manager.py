import json
from typing import Dict, List, Optional

from backend.database import Plugin as PluginModel, get_db_session


DEFAULT_PLUGINS = [
    {
        "name": "calculator",
        "display_name": "计算器",
        "version": "1.0.0",
        "description": "数学表达式计算工具，支持基本算术运算和常见数学函数",
        "author": "Jarvis",
        "icon": "🔢",
        "is_default": True,
    },
    {
        "name": "search",
        "display_name": "搜索引擎",
        "version": "1.0.0",
        "description": "互联网信息检索工具，支持百度必应搜狗等搜索引擎",
        "author": "Jarvis",
        "icon": "🔍",
        "is_default": True,
    },
    {
        "name": "weather",
        "display_name": "天气预报",
        "version": "1.0.0",
        "description": "城市天气查询工具，支持查询国内主要城市的实时天气信息",
        "author": "Jarvis",
        "icon": "🌤️",
        "is_default": True,
    },
    {
        "name": "file",
        "display_name": "文件操作",
        "version": "1.0.0",
        "description": "文件读写操作工具，支持读取和写入本地文件",
        "author": "Jarvis",
        "icon": "📁",
        "is_default": True,
    },
    {
        "name": "datetime",
        "display_name": "日期时间",
        "version": "1.0.0",
        "description": "日期时间工具，支持获取当前时间和设置定时器",
        "author": "Jarvis",
        "icon": "⏰",
        "is_default": True,
    },
]


def seed_default_plugins():
    db = get_db_session()
    try:
        for plugin_data in DEFAULT_PLUGINS:
            existing = db.query(PluginModel).filter(
                PluginModel.name == plugin_data["name"]
            ).first()
            if not existing:
                db.add(PluginModel(**plugin_data))
        db.commit()
    finally:
        db.close()


def get_all_plugins() -> List[Dict]:
    db = get_db_session()
    try:
        plugins = db.query(PluginModel).order_by(PluginModel.id).all()
        return [
            {
                "id": p.id,
                "name": p.name,
                "display_name": p.display_name,
                "version": p.version,
                "description": p.description,
                "author": p.author,
                "icon": p.icon,
                "is_enabled": p.is_enabled,
                "is_default": p.is_default,
                "config": json.loads(p.config) if p.config else {},
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in plugins
        ]
    finally:
        db.close()


def get_enabled_plugins() -> List[Dict]:
    db = get_db_session()
    try:
        plugins = db.query(PluginModel).filter(
            PluginModel.is_enabled == True
        ).order_by(PluginModel.id).all()
        return [
            {
                "id": p.id,
                "name": p.name,
                "display_name": p.display_name,
                "icon": p.icon,
            }
            for p in plugins
        ]
    finally:
        db.close()


def toggle_plugin(plugin_id: int, enabled: bool) -> bool:
    db = get_db_session()
    try:
        plugin = db.query(PluginModel).filter(PluginModel.id == plugin_id).first()
        if not plugin:
            return False
        plugin.is_enabled = enabled
        db.commit()
        return True
    finally:
        db.close()


def update_plugin_config(plugin_id: int, config: Dict) -> bool:
    db = get_db_session()
    try:
        plugin = db.query(PluginModel).filter(PluginModel.id == plugin_id).first()
        if not plugin:
            return False
        plugin.config = json.dumps(config, ensure_ascii=False)
        db.commit()
        return True
    finally:
        db.close()


def remove_plugin(plugin_id: int) -> bool:
    db = get_db_session()
    try:
        plugin = db.query(PluginModel).filter(PluginModel.id == plugin_id).first()
        if not plugin:
            return False
        if plugin.is_default:
            return False
        db.delete(plugin)
        db.commit()
        return True
    finally:
        db.close()


def install_plugin(name: str, display_name: str, description: str = "",
                   version: str = "1.0.0", author: str = "", icon: str = "🧩",
                   config: Optional[Dict] = None) -> Optional[int]:
    db = get_db_session()
    try:
        existing = db.query(PluginModel).filter(
            PluginModel.name == name
        ).first()
        if existing:
            return None

        plugin = PluginModel(
            name=name,
            display_name=display_name,
            version=version,
            description=description,
            author=author,
            icon=icon,
            is_default=False,
            config=json.dumps(config or {}, ensure_ascii=False),
        )
        db.add(plugin)
        db.commit()
        return plugin.id
    finally:
        db.close()
