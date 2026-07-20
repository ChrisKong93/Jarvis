import re
from datetime import timedelta
from typing import Optional

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.auth import (
    authenticate_user,
    create_access_token,
    create_user,
    decode_access_token,
    get_user,
)
from backend.database import get_db

MIN_PASSWORD_LENGTH = 8


def _validate_password(password: str) -> Optional[str]:
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"密码长度不能少于 {MIN_PASSWORD_LENGTH} 位"
    if not re.search(r"[A-Za-z]", password):
        return "密码必须包含至少一个字母"
    if not re.search(r"\d", password):
        return "密码必须包含至少一个数字"
    return None


def register_auth_routes(app, limiter, get_current_user):
    """注册认证相关的路由（register / login / logout / me）。"""

    @app.post("/api/auth/register")
    @limiter.limit("5/minute")
    async def register(request: Request, db: Session = Depends(get_db)):
        data = await request.json()
        username = data.get("username")
        email = data.get("email")
        password = data.get("password")

        if not username or not email or not password:
            return {"error": "用户名、邮箱和密码不能为空"}, 400

        username = username.strip()
        email = email.strip()

        if len(username) < 2:
            return {"error": "用户名至少 2 个字符"}, 400

        if not re.match(r"^[a-zA-Z0-9_\u4e00-\u9fff]+$", username):
            return {"error": "用户名只能包含字母、数字、下划线和中文"}, 400

        if "@" not in email or "." not in email:
            return {"error": "邮箱格式不正确"}, 400

        password_error = _validate_password(password)
        if password_error:
            return {"error": password_error}, 400

        if get_user(db, username):
            return {"error": "用户名已存在"}, 400

        if get_user(db, email):
            return {"error": "邮箱已被注册"}, 400

        user = create_user(db, username, email, password)
        return {"success": True, "message": "注册成功", "username": user.username}

    @app.post("/api/auth/login")
    @limiter.limit("10/minute")
    async def login(request: Request, db: Session = Depends(get_db)):
        data = await request.json()
        username = data.get("username")
        password = data.get("password")

        user = authenticate_user(db, username, password)
        if not user:
            return {"error": "用户名或密码错误"}, 401

        access_token_expires = timedelta(minutes=30 * 24 * 60)
        access_token = create_access_token(
            data={"sub": user.username}, expires_delta=access_token_expires
        )

        response = JSONResponse({
            "success": True,
            "message": "登录成功",
            "access_token": access_token,
            "username": user.username,
        })
        response.set_cookie(key="access_token", value=access_token, httponly=True)
        return response

    @app.post("/api/auth/logout")
    async def logout():
        response = JSONResponse({"success": True, "message": "退出成功"})
        response.set_cookie(key="access_token", value="", expires=0)
        return response

    @app.get("/api/auth/me")
    async def get_current_user_info(user: dict = Depends(get_current_user)):
        if not user:
            return {"authenticated": False}
        return {"authenticated": True, "user": user}
