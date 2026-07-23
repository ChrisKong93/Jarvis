import asyncio
import json
import time
from typing import Any, AsyncGenerator, Dict, Generator, List, Optional

import httpx

from .registry import (
    get_provider,
    is_api_key_configured,
    resolve_api_key,
    resolve_base_url,
    resolve_model,
)


class LLMError(Exception):
    def __init__(self, message: str, status_code: int = 500, provider: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.provider = provider


class LLMClient:
    def __init__(self, timeout: float = 300.0):
        self.timeout = timeout
        self._async_client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------
    # Shared client (connection pooling)
    # ------------------------------------------------------------------

    @property
    def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                timeout=self.timeout,
                limits=httpx.Limits(
                    max_keepalive_connections=5,
                    max_connections=20,
                ),
            )
        return self._async_client

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate(provider_id: str, api_key: Optional[str]) -> Dict[str, Any]:
        provider = get_provider(provider_id)
        if not provider:
            raise LLMError(f"未知 Provider: {provider_id}", provider=provider_id)
        if not is_api_key_configured(provider_id, api_key):
            env_name = provider.get("api_key_env") or "API Key"
            raise LLMError(
                f"{provider['name']} 未配置 API Key，请设置环境变量 {env_name} 或在设置中填写",
                status_code=401,
                provider=provider_id,
            )
        return provider

    @staticmethod
    def _build_headers(resolved_key: Optional[str]) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if resolved_key:
            headers["Authorization"] = f"Bearer {resolved_key}"
        return headers

    @staticmethod
    def _parse_response(result: Dict, resolved_model: Optional[str],
                        provider_id: str, elapsed: float) -> Dict[str, Any]:
        content = ""
        tool_calls = []

        if result.get("choices"):
            message = result["choices"][0].get("message", {})
            content = message.get("content", "")
            tool_calls = message.get("tool_calls", [])

        usage = result.get("usage", {})
        completion_tokens = usage.get("completion_tokens", 0)
        prompt_tokens = usage.get("prompt_tokens", 0)
        total_tokens = usage.get("total_tokens", completion_tokens + prompt_tokens)

        return {
            "content": content,
            "tool_calls": tool_calls,
            "completion_tokens": completion_tokens,
            "prompt_tokens": prompt_tokens,
            "total_tokens": total_tokens,
            "model": result.get("model") or resolved_model,
            "provider": provider_id,
            "response_time": round(elapsed, 2),
            "tokens_per_second": round(completion_tokens / elapsed, 2) if elapsed > 0 else 0,
            "raw": result,
        }

    @staticmethod
    def _extract_error(response: httpx.Response) -> str:
        try:
            data = response.json()
            if isinstance(data, dict):
                err = data.get("error", data)
                if isinstance(err, dict):
                    return err.get("message", str(err))
                return str(err)
        except Exception:
            pass
        text = response.text.strip()
        return text[:300] if text else f"HTTP {response.status_code}"

    # ------------------------------------------------------------------
    # Sync methods (kept for LangGraph compatibility)
    # ------------------------------------------------------------------

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        provider_id: str = "llama_cpp",
        model: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 0.9,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        stop: Optional[List[str]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._validate(provider_id, api_key)

        resolved_base = resolve_base_url(provider_id, base_url)
        resolved_model = resolve_model(provider_id, model)
        resolved_key = resolve_api_key(provider_id, api_key)

        payload: Dict[str, Any] = {
            "messages": messages,
            "stream": False,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }
        if resolved_model:
            payload["model"] = resolved_model
        if stop:
            payload["stop"] = stop
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice

        headers = self._build_headers(resolved_key)
        url = f"{resolved_base}/v1/chat/completions"
        start = time.time()

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException:
            raise LLMError(f"{provider_id} 请求超时", status_code=504, provider=provider_id)
        except httpx.RequestError as exc:
            raise LLMError(f"无法连接 {provider_id}: {exc}", status_code=502, provider=provider_id)

        elapsed = time.time() - start

        if response.status_code >= 400:
            detail = self._extract_error(response)
            raise LLMError(
                f"{provider_id} 调用失败: {detail}",
                status_code=response.status_code,
                provider=provider_id,
            )

        return self._parse_response(response.json(), resolved_model, provider_id, elapsed)

    def chat_completion_stream(
        self,
        messages: List[Dict[str, str]],
        provider_id: str = "llama_cpp",
        model: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 0.9,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        stop: Optional[List[str]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        provider = get_provider(provider_id)
        if not provider:
            yield {"type": "error", "content": f"未知 Provider: {provider_id}"}
            return

        if not is_api_key_configured(provider_id, api_key):
            yield {"type": "error", "content": f"{provider['name']} 未配置 API Key"}
            return

        resolved_base = resolve_base_url(provider_id, base_url)
        resolved_model = resolve_model(provider_id, model)
        resolved_key = resolve_api_key(provider_id, api_key)

        payload: Dict[str, Any] = {
            "messages": messages,
            "stream": True,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }
        if resolved_model:
            payload["model"] = resolved_model
        if stop:
            payload["stop"] = stop
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice

        headers = self._build_headers(resolved_key)
        url = f"{resolved_base}/v1/chat/completions"
        start = time.time()

        try:
            with httpx.Client(timeout=self.timeout) as client:
                with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code >= 400:
                        response.read()
                        detail = self._extract_error(response)
                        yield {"type": "error", "content": detail, "status_code": response.status_code}
                        return

                    content_parts: List[str] = []
                    tool_calls_accum: Dict[int, Dict] = {}
                    finish_reason = None
                    usage: Optional[Dict[str, int]] = None

                    for line in response.iter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue

                        # 部分 API 在最后 chunk 中返回 usage（无 choices）
                        if chunk.get("usage"):
                            usage = chunk["usage"]

                        choices = chunk.get("choices", [])
                        if not choices:
                            continue

                        delta = choices[0].get("delta", {})
                        finish_reason = choices[0].get("finish_reason")

                        if delta.get("content"):
                            content_parts.append(delta["content"])
                            yield {"type": "token", "content": delta["content"]}

                        if delta.get("tool_calls"):
                            for tc in delta["tool_calls"]:
                                idx = tc.get("index", 0)
                                if idx not in tool_calls_accum:
                                    tool_calls_accum[idx] = {
                                        "id": tc.get("id", ""),
                                        "type": "function",
                                        "function": {"name": "", "arguments": ""},
                                    }
                                acc = tool_calls_accum[idx]
                                if tc.get("id"):
                                    acc["id"] = tc["id"]
                                if tc.get("type"):
                                    acc["type"] = tc["type"]
                                if tc.get("function"):
                                    if tc["function"].get("name"):
                                        acc["function"]["name"] += tc["function"]["name"]
                                    if tc["function"].get("arguments"):
                                        acc["function"]["arguments"] += tc["function"]["arguments"]

                        if finish_reason:
                            break

                    elapsed = time.time() - start
                    content = "".join(content_parts)

                    tool_calls = []
                    if tool_calls_accum:
                        sorted_keys = sorted(tool_calls_accum.keys())
                        tool_calls = [tool_calls_accum[k] for k in sorted_keys]

                    yield {
                        "type": "done",
                        "content": content,
                        "tool_calls": tool_calls,
                        "finish_reason": finish_reason or "stop",
                        "response_time": round(elapsed, 2),
                        "model": resolved_model,
                        "provider": provider_id,
                        "usage": usage or {},
                    }

        except httpx.TimeoutException:
            yield {"type": "error", "content": f"{provider['name']} 请求超时", "status_code": 504}
        except httpx.RequestError as exc:
            yield {"type": "error", "content": f"无法连接 {provider['name']}: {exc}", "status_code": 502}

    # ------------------------------------------------------------------
    # Async methods (for direct API routes)
    # ------------------------------------------------------------------

    async def async_chat_completion(
        self,
        messages: List[Dict[str, str]],
        provider_id: str = "llama_cpp",
        model: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 0.9,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        stop: Optional[List[str]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._validate(provider_id, api_key)

        resolved_base = resolve_base_url(provider_id, base_url)
        resolved_model = resolve_model(provider_id, model)
        resolved_key = resolve_api_key(provider_id, api_key)

        payload: Dict[str, Any] = {
            "messages": messages,
            "stream": False,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }
        if resolved_model:
            payload["model"] = resolved_model
        if stop:
            payload["stop"] = stop
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice

        headers = self._build_headers(resolved_key)
        url = f"{resolved_base}/v1/chat/completions"
        start = time.time()

        client = self._get_async_client
        try:
            response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException:
            raise LLMError(f"{provider_id} 请求超时", status_code=504, provider=provider_id)
        except httpx.RequestError as exc:
            raise LLMError(f"无法连接 {provider_id}: {exc}", status_code=502, provider=provider_id)

        elapsed = time.time() - start

        if response.status_code >= 400:
            detail = self._extract_error(response)
            raise LLMError(
                f"{provider_id} 调用失败: {detail}",
                status_code=response.status_code,
                provider=provider_id,
            )

        return self._parse_response(response.json(), resolved_model, provider_id, elapsed)

    async def async_chat_completion_stream(
        self,
        messages: List[Dict[str, str]],
        provider_id: str = "llama_cpp",
        model: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 0.9,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        stop: Optional[List[str]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        provider = get_provider(provider_id)
        if not provider:
            yield {"type": "error", "content": f"未知 Provider: {provider_id}"}
            return

        if not is_api_key_configured(provider_id, api_key):
            yield {"type": "error", "content": f"{provider['name']} 未配置 API Key"}
            return

        resolved_base = resolve_base_url(provider_id, base_url)
        resolved_model = resolve_model(provider_id, model)
        resolved_key = resolve_api_key(provider_id, api_key)

        payload: Dict[str, Any] = {
            "messages": messages,
            "stream": True,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }
        if resolved_model:
            payload["model"] = resolved_model
        if stop:
            payload["stop"] = stop
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice

        headers = self._build_headers(resolved_key)
        url = f"{resolved_base}/v1/chat/completions"
        start = time.time()

        client = self._get_async_client
        try:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code >= 400:
                    await response.aread()
                    detail = self._extract_error(response)
                    yield {"type": "error", "content": detail, "status_code": response.status_code}
                    return

                content_parts: List[str] = []
                tool_calls_accum: Dict[int, Dict] = {}
                finish_reason = None
                usage: Optional[Dict[str, int]] = None

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    # 部分 API 在最后 chunk 中返回 usage（无 choices）
                    if chunk.get("usage"):
                        usage = chunk["usage"]

                    choices = chunk.get("choices", [])
                    if not choices:
                        continue

                    delta = choices[0].get("delta", {})
                    finish_reason = choices[0].get("finish_reason")

                    if delta.get("content"):
                        content_parts.append(delta["content"])
                        yield {"type": "token", "content": delta["content"]}

                    if delta.get("tool_calls"):
                        for tc in delta["tool_calls"]:
                            idx = tc.get("index", 0)
                            if idx not in tool_calls_accum:
                                tool_calls_accum[idx] = {
                                    "id": tc.get("id", ""),
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                }
                            acc = tool_calls_accum[idx]
                            if tc.get("id"):
                                acc["id"] = tc["id"]
                            if tc.get("type"):
                                acc["type"] = tc["type"]
                            if tc.get("function"):
                                if tc["function"].get("name"):
                                    acc["function"]["name"] += tc["function"]["name"]
                                if tc["function"].get("arguments"):
                                    acc["function"]["arguments"] += tc["function"]["arguments"]

                    if finish_reason:
                        break

                elapsed = time.time() - start
                content = "".join(content_parts)

                tool_calls = []
                if tool_calls_accum:
                    sorted_keys = sorted(tool_calls_accum.keys())
                    tool_calls = [tool_calls_accum[k] for k in sorted_keys]

                yield {
                    "type": "done",
                    "content": content,
                    "tool_calls": tool_calls,
                    "finish_reason": finish_reason or "stop",
                    "response_time": round(elapsed, 2),
                    "model": resolved_model,
                    "provider": provider_id,
                    "usage": usage or {},
                }

        except httpx.TimeoutException:
            yield {"type": "error", "content": f"{provider['name']} 请求超时", "status_code": 504}
        except httpx.RequestError as exc:
            yield {"type": "error", "content": f"无法连接 {provider['name']}: {exc}", "status_code": 502}

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    def list_models(
        self,
        provider_id: str = "llama_cpp",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        provider = get_provider(provider_id)
        if not provider:
            return []

        if not provider.get("dynamic_models"):
            return [{"id": m, "name": m} for m in provider.get("models", [])]

        resolved_base = resolve_base_url(provider_id, base_url)
        resolved_key = resolve_api_key(provider_id, api_key)
        headers = self._build_headers(resolved_key)
        url = f"{resolved_base}/v1/models"

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, headers=headers)
            if response.status_code >= 400:
                return []
            data = response.json()
            models = data.get("data", data.get("models", []))
            if models:
                return [
                    {"id": m.get("id", m.get("name", "")), "name": m.get("id", m.get("name", ""))}
                    for m in models if m.get("id") or m.get("name")
                ]
            return []
        except Exception:
            return []

    def health_check(
        self,
        provider_id: str = "llama_cpp",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        provider = get_provider(provider_id)
        if not provider:
            return {"status": "error", "message": f"未知 Provider: {provider_id}"}

        if not is_api_key_configured(provider_id, api_key) and provider.get("api_key_env"):
            return {
                "status": "error",
                "message": f"{provider['name']} API Key 未配置",
                "provider": provider_id,
            }

        resolved_base = resolve_base_url(provider_id, base_url)
        resolved_key = resolve_api_key(provider_id, api_key)
        headers = self._build_headers(resolved_key)

        for path in ("/health", "/v1/models"):
            try:
                with httpx.Client(timeout=10.0) as client:
                    response = client.get(f"{resolved_base}{path}", headers=headers)
                if response.status_code < 400:
                    return {"status": "ok", "provider": provider_id, "endpoint": f"{resolved_base}{path}"}
            except Exception:
                continue

        return {"status": "error", "message": f"无法连接 {provider['name']}", "provider": provider_id}

    async def close(self):
        """关闭 async client 释放连接池。"""
        if self._async_client is not None:
            await self._async_client.aclose()
            self._async_client = None


llm_client = LLMClient()
