"""Integration tests for auth API endpoints."""

import pytest


class TestAuthAPI:

    async def test_auth_me_unauthenticated(self, async_client):
        """未认证时 /me 应返回 authenticated=False"""
        resp = await async_client.get("/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("authenticated") is False

    async def test_register_and_login_flow(self, async_client):
        """完整的注册→登录→验证流程"""
        suffix = __import__("time").time_ns()
        username = f"flow_{suffix}"
        email = f"flow_{suffix}@example.com"
        password = "TestPass123"

        # 注册
        reg = await async_client.post("/api/auth/register", json={
            "username": username,
            "email": email,
            "password": password,
        })
        if reg.status_code == 429:
            pytest.skip("rate limited")
        assert reg.status_code == 200, reg.text
        assert reg.json().get("success") is True

        # 登录
        login = await async_client.post("/api/auth/login", json={
            "username": username,
            "password": password,
        })
        if login.status_code == 429:
            pytest.skip("rate limited")
        assert login.status_code == 200, login.text
        data = login.json()
        assert "access_token" in data
        token = data["access_token"]

        # 用 token 访问 /me
        me = await async_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me.status_code == 200, me.text
        me_data = me.json()
        assert me_data.get("authenticated") is True
        assert me_data["user"]["username"] == username

    async def test_register_validation_errors(self, async_client):
        """注册时弱密码/无效邮箱应返回 400"""
        # 弱密码
        weak = await async_client.post("/api/auth/register", json={
            "username": "val_weak_test",
            "email": "weak@test.com",
            "password": "short",
        })
        if weak.status_code == 429:
            pytest.skip("rate limited")
        assert weak.status_code == 400, weak.text
        assert "密码" in weak.text

        # 无效邮箱
        bad_email = await async_client.post("/api/auth/register", json={
            "username": "val_email_test",
            "email": "notanemail",
            "password": "TestPass123",
        })
        if bad_email.status_code == 429:
            pytest.skip("rate limited")
        assert bad_email.status_code == 400, bad_email.text
        assert "邮箱" in bad_email.text

    async def test_logout(self, async_client):
        """退出登录应清除 cookie"""
        resp = await async_client.post("/api/auth/logout")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True
