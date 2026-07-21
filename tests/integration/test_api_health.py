"""Integration tests for health / provider API endpoints."""

import pytest


class TestHealthAPI:

    async def test_health_endpoint_returns_json(self, async_client):
        resp = await async_client.get("/api/health")
        assert resp.status_code in (200, 503)
        data = resp.json()
        assert "status" in data

    async def test_health_without_auth(self, async_client):
        """Health should work even without authentication."""
        resp = await async_client.get("/api/health")
        assert resp.status_code in (200, 503)

    async def test_providers_list(self, async_client):
        resp = await async_client.get("/api/providers")
        assert resp.status_code in (200, 401)
        if resp.status_code == 200:
            data = resp.json()
            assert "providers" in data
            assert "default_provider" in data

    async def test_models_endpoint(self, async_client):
        resp = await async_client.get("/api/models")
        assert resp.status_code in (200, 401, 422)
