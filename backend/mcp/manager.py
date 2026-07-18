"""
MCP (Model Context Protocol) 管理器

手动实现 MCP 客户端协议（JSON-RPC 2.0 over stdio/SSE）。
无需 MCP SDK，兼容 Python 3.9+。
"""
import asyncio
import concurrent.futures
import json
import logging
import os
import subprocess
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MCP_CONFIG_PATH = os.environ.get(
    "MCP_CONFIG_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "mcp_servers.json"),
)
MCP_CONNECT_TIMEOUT = int(os.environ.get("MCP_CONNECT_TIMEOUT", "60"))  # 单服务器连接超时（秒）


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 辅助
# ---------------------------------------------------------------------------

def _make_request(method: str, params: Any = None) -> Dict:
    return {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": method,
        "params": params or {},
    }


def _check_response(response: Dict) -> Any:
    """从 JSON-RPC 响应中提取 result，有 error 则抛异常。"""
    if "error" in response:
        err = response["error"]
        raise RuntimeError(f"MCP error: {err.get('message', err)} (code={err.get('code')})")
    return response.get("result")


# ---------------------------------------------------------------------------
# Stdio 传输
# ---------------------------------------------------------------------------

class StdioTransport:
    """通过子进程 stdin/stdout 进行 JSON-RPC 通信。"""

    def __init__(self, command: str, args: List[str], env: Optional[Dict[str, str]] = None):
        self._command = command
        self._args = args or []
        self._env = env
        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._buffer = b""
        self._read_timeout = 20  # 读取响应超时（秒）

    def connect(self):
        """启动子进程。"""
        merged_env = os.environ.copy()
        if self._env:
            merged_env.update(self._env)
        self._process = subprocess.Popen(
            [self._command] + self._args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=merged_env,
        )
        # 后台持续排空 stderr，避免管道塞满导致子进程卡死
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()
        logger.info(f"MCP stdio 子进程已启动: {self._command} {' '.join(self._args)}")

    def _drain_stderr(self):
        """持续读取 stderr，防止管道阻塞。"""
        try:
            while self._process and self._process.stderr:
                line = self._process.stderr.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    logger.debug(f"MCP stderr: {text}")
        except Exception:
            pass

    def disconnect(self):
        """关闭子进程。"""
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
            logger.info("MCP stdio 子进程已关闭")

    def send_notification(self, notification: Dict):
        """发送 JSON-RPC 通知（只写不读，不等待响应）。"""
        if not self._process or not self._process.stdin:
            raise RuntimeError("MCP stdio 传输未连接")
        payload = json.dumps(notification, ensure_ascii=False) + "\n"
        with self._lock:
            self._process.stdin.write(payload.encode("utf-8"))
            self._process.stdin.flush()

    def send_request(self, request: Dict) -> Dict:
        """发送 JSON-RPC 请求，返回响应。"""
        if not self._process or not self._process.stdin:
            raise RuntimeError("MCP stdio 传输未连接")

        payload = json.dumps(request, ensure_ascii=False) + "\n"
        with self._lock:
            self._process.stdin.write(payload.encode("utf-8"))
            self._process.stdin.flush()
            return self._read_response()

    def _read_response(self) -> Dict:
        """从 stdout 读取一行 JSON-RPC 响应（带超时）。"""
        import select

        while self._process and self._process.stdout:
            ready, _, _ = select.select([self._process.stdout], [], [], self._read_timeout)
            if not ready:
                stderr_output = self._read_stderr()
                raise TimeoutError(
                    f"MCP 子进程响应超时（{self._read_timeout}s）"
                    + (f"\nstderr: {stderr_output}" if stderr_output else "")
                )
            line = self._process.stdout.readline()
            if not line:
                stderr_output = self._read_stderr()
                if stderr_output:
                    logger.warning(f"MCP stderr: {stderr_output}")
                raise RuntimeError("MCP 子进程已退出，stdout 关闭")
            try:
                return json.loads(line.decode("utf-8").strip())
            except json.JSONDecodeError:
                logger.warning(f"MCP 非 JSON 输出（忽略）: {line.decode('utf-8').strip()}")
                continue

    def _read_stderr(self) -> str:
        """读取 stderr 中的内容（非阻塞）。"""
        if not self._process or not self._process.stderr:
            return ""
        import select
        try:
            if select.select([self._process.stderr], [], [], 0.1)[0]:
                return self._process.stderr.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return ""

    @property
    def is_connected(self) -> bool:
        return self._process is not None and self._process.poll() is None


# ---------------------------------------------------------------------------
# SSE / Streamable HTTP 传输
# ---------------------------------------------------------------------------

class SSETransport:
    """通过 HTTP POST + SSE 进行 JSON-RPC 通信（Streamable HTTP）。"""

    def __init__(self, url: str):
        self._url = url.rstrip("/")
        self._session = None

    def connect(self):
        """初始化 HTTP 会话。"""
        import httpx
        self._session = httpx.Client(timeout=120.0)
        logger.info(f"MCP SSE 传输已连接: {self._url}")

    def disconnect(self):
        if self._session:
            self._session.close()
            self._session = None
            logger.info("MCP SSE 传输已关闭")

    def send_notification(self, notification: Dict):
        """发送 JSON-RPC 通知（不等待响应）。"""
        if not self._session:
            raise RuntimeError("MCP SSE 传输未连接")
        try:
            self._session.post(
                self._url,
                json=notification,
                headers={"Content-Type": "application/json"},
                timeout=5.0,
            )
        except Exception:
            pass

    def send_request(self, request: Dict) -> Dict:
        """发送 JSON-RPC 请求，返回响应。"""
        if not self._session:
            raise RuntimeError("MCP SSE 传输未连接")

        response = self._session.post(
            self._url,
            json=request,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()

        # 检查 Content-Type 以判断是否为 SSE 流
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            return self._parse_sse_response(response)
        
        # 普通 JSON 响应
        return response.json()

    def _parse_sse_response(self, response) -> Dict:
        """从 SSE 响应中提取最后一个事件的数据。"""
        last_data = None
        for line in response.iter_lines():
            line = line.decode("utf-8") if isinstance(line, bytes) else line
            if line.startswith("data: "):
                last_data = line[6:].strip()
        
        if last_data:
            try:
                return json.loads(last_data)
            except json.JSONDecodeError:
                pass
        raise RuntimeError("无法从 SSE 流中解析 JSON-RPC 响应")

    @property
    def is_connected(self) -> bool:
        return self._session is not None


# ---------------------------------------------------------------------------
# MCP 服务器连接（单个）
# ---------------------------------------------------------------------------

class MCPServerConnection:
    """管理单个 MCP 服务器连接。"""

    def __init__(self, config: Dict[str, Any]):
        self.name = config["name"]
        self.config = config
        self._transport: Optional[Any] = None
        self._capabilities: Dict[str, Any] = {}
        self._connected = False
        self._tools_cache: List[Dict[str, Any]] = []
        self._tool_cache_time = 0
        self._cache_ttl = 30  # 工具列表缓存 30 秒

    def connect(self):
        """连接到 MCP 服务器并初始化。"""
        transport_type = self.config.get("transport", "stdio")

        if transport_type == "stdio":
            self._transport = StdioTransport(
                command=self.config["command"],
                args=self.config.get("args", []),
                env=self.config.get("env"),
            )
        elif transport_type == "sse":
            self._transport = SSETransport(url=self.config["url"])
        else:
            raise ValueError(f"不支持的 MCP 传输类型: {transport_type}")

        self._transport.connect()

        # MCP 初始化握手
        init_result = self._send_request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {
                "tools": {},
                "resources": {},
                "prompts": {},
            },
            "clientInfo": {
                "name": "Jarvis",
                "version": "1.0.0",
            },
        })
        self._capabilities = init_result.get("capabilities", {})
        logger.info(f"MCP 服务器 '{self.name}' 已初始化, 能力: {list(self._capabilities.keys())}")

        # 发送 initialized 通知
        self._send_notification("notifications/initialized")

        # 预获取工具列表
        self._refresh_tools()
        self._connected = True
        logger.info(f"MCP 服务器 '{self.name}' 连接完成, 发现 {len(self._tools_cache)} 个工具")

    def disconnect(self):
        self._connected = False
        if self._transport:
            self._transport.disconnect()
        self._tools_cache = []

    def _send_request(self, method: str, params: Any = None) -> Any:
        request = _make_request(method, params)
        response = self._transport.send_request(request)
        return _check_response(response)

    def _send_notification(self, method: str, params: Any = None):
        """发送 JSON-RPC 通知（无响应期望，只写不读）。"""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }
        try:
            if hasattr(self._transport, "send_notification"):
                self._transport.send_notification(notification)
            else:
                # 兼容旧传输：发完不等待
                pass
        except Exception as e:
            logger.debug(f"MCP 通知发送失败（可忽略）: {e}")

    def _refresh_tools(self):
        """刷新工具缓存。"""
        try:
            result = self._send_request("tools/list")
            self._tools_cache = result.get("tools", [])
            self._tool_cache_time = time.time()
        except Exception as e:
            logger.error(f"获取 MCP 工具列表失败 '{self.name}': {e}")
            self._tools_cache = []

    def list_tools(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """获取工具列表（带缓存）。"""
        if force_refresh or (time.time() - self._tool_cache_time > self._cache_ttl):
            self._refresh_tools()
        return [
            {
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": t.get("inputSchema", {}),
                "server": self.name,
            }
            for t in self._tools_cache
        ]

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """调用工具并返回结果文本。"""
        if not self._connected:
            raise RuntimeError(f"MCP 服务器 '{self.name}' 未连接")

        result = self._send_request("tools/call", {
            "name": name,
            "arguments": arguments,
        })

        # 解析 MCP 工具结果
        content = result.get("content", [])
        parts = []
        for item in content:
            if item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif item.get("type") == "resource":
                resource = item.get("resource", {})
                if resource.get("text"):
                    parts.append(resource["text"])
                elif resource.get("blob"):
                    parts.append(f"[二进制数据: {resource.get('mimeType', 'application/octet-stream')}]")
            else:
                parts.append(str(item))

        # 检查是否有 isError 标记
        if result.get("isError"):
            error_text = "\n".join(parts) if parts else "未知错误"
            return f"MCP 工具执行错误: {error_text}"

        return "\n".join(parts) if parts else "(空结果)"

    @property
    def is_connected(self) -> bool:
        return self._connected and self._transport is not None and self._transport.is_connected


# ---------------------------------------------------------------------------
# MCP 服务器管理器（全局单例）
# ---------------------------------------------------------------------------

class MCPServerManager:
    """管理多个 MCP 服务器连接，提供统一的工具发现和执行接口。"""

    def __init__(self):
        self.connections: Dict[str, MCPServerConnection] = {}
        self._tool_index: Dict[str, Dict[str, Any]] = {}
        self._config_path = MCP_CONFIG_PATH
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None

    # ---- 生命周期 ----------------------------------------------------------

    def _ensure_loop(self):
        """确保事件循环和后台线程已创建（无服务器时也保持存活）。"""
        if self._loop is not None and self._loop.is_running():
            return
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._loop_thread.start()
        logger.debug("MCP 事件循环已启动")

    def start(self):
        """在后台线程中初始化所有 MCP 服务器连接（非阻塞）。"""
        self._ensure_loop()
        configs = self._load_config()
        if not configs:
            logger.info("没有配置 MCP 服务器，跳过")
            return

        future = asyncio.run_coroutine_threadsafe(self._connect_all(configs), self._loop)
        future.add_done_callback(self._on_connect_done)

    def _on_connect_done(self, future: concurrent.futures.Future):
        """连接完成的回调（logging only）。"""
        try:
            future.result(timeout=0)
        except concurrent.futures.TimeoutError:
            logger.warning("MCP 连接超时（某些服务器可能耗时较长，服务仍会启动）")
        except Exception as e:
            logger.error(f"MCP 连接异常: {e}", exc_info=True)

    def stop(self):
        """断开所有 MCP 服务器连接并关闭事件循环。"""
        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self._disconnect_all(), self._loop)
            try:
                future.result(timeout=15)
            except Exception as e:
                logger.error(f"MCP 关闭失败: {e}")
            self._loop.call_soon_threadsafe(self._loop.stop)

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    # ---- 配置加载 ----------------------------------------------------------

    def _load_config(self) -> List[Dict[str, Any]]:
        """从 JSON 文件加载 MCP 服务器配置。"""
        if not os.path.exists(self._config_path):
            logger.info(f"MCP 配置文件不存在: {self._config_path}")
            return []
        try:
            with open(self._config_path, "r") as f:
                data = json.load(f)
            servers = data.get("servers", [])
            logger.info(f"从 {self._config_path} 加载了 {len(servers)} 个 MCP 服务器配置")
            return servers
        except Exception as e:
            logger.error(f"加载 MCP 配置失败: {e}")
            return []

    def reload_config(self):
        """重新加载配置并重连（使用已有事件循环，异步）。"""
        self._ensure_loop()

        for name, conn in list(self.connections.items()):
            try:
                conn.disconnect()
            except Exception as e:
                logger.warning(f"MCP 断开 '{name}' 失败: {e}")
        self.connections.clear()
        self._tool_index.clear()

        configs = self._load_config()
        if not configs:
            logger.info("没有配置 MCP 服务器")
            return

        future = asyncio.run_coroutine_threadsafe(self._connect_all(configs), self._loop)
        future.add_done_callback(self._on_connect_done)

    def reload_config_sync(self):
        """重新加载配置并重连（同步，等待所有连接完成后再返回）。

        每个服务器连接有独立超时（MCP_CONNECT_TIMEOUT），超时则跳过，
        确保不会因某个 MCP 服务器卡住而阻塞主服务。
        """
        for name, conn in list(self.connections.items()):
            try:
                conn.disconnect()
            except Exception as e:
                logger.warning(f"MCP 断开 '{name}' 失败: {e}")
        self.connections.clear()
        self._tool_index.clear()

        configs = self._load_config()
        if not configs:
            logger.info("没有配置 MCP 服务器")
            return

        for config in configs:
            name = config.get("name", "unknown")
            conn = MCPServerConnection(config)

            result_container = {"exception": None, "conn": None}

            def _connect():
                try:
                    conn.connect()
                    result_container["conn"] = conn
                except Exception as e:
                    result_container["exception"] = e

            t = threading.Thread(target=_connect, daemon=True)
            t.start()
            t.join(timeout=MCP_CONNECT_TIMEOUT)

            if t.is_alive():
                logger.warning(f"MCP 服务器连接超时 '{name}'（{MCP_CONNECT_TIMEOUT}s），已跳过")
                try:
                    conn.disconnect()
                except Exception:
                    pass
            elif result_container["exception"]:
                logger.error(f"MCP 服务器连接失败 '{name}': {result_container['exception']}")
            else:
                self.connections[name] = result_container["conn"]
                logger.info(f"MCP 服务器已连接: '{name}'")

        self._rebuild_tool_index()

    # ---- 连接管理（异步） --------------------------------------------------

    async def _connect_all(self, configs: List[Dict[str, Any]]):
        """连接所有配置的 MCP 服务器。"""
        for config in configs:
            try:
                conn = MCPServerConnection(config)
                await asyncio.get_event_loop().run_in_executor(None, conn.connect)
                self.connections[config["name"]] = conn
                logger.info(f"MCP 服务器已连接: '{config['name']}'")
            except Exception as e:
                logger.error(f"MCP 服务器连接失败 '{config['name']}': {e}")
        self._rebuild_tool_index()

    async def _disconnect_all(self):
        """断开所有 MCP 服务器。"""
        for name, conn in list(self.connections.items()):
            try:
                await asyncio.get_event_loop().run_in_executor(None, conn.disconnect)
                logger.info(f"MCP 服务器已断开: '{name}'")
            except Exception as e:
                logger.error(f"MCP 断开失败 '{name}': {e}")
        self.connections.clear()
        self._tool_index.clear()

    @staticmethod
    def _get_connection_configs_from_dict(servers: List[Dict]) -> List[Dict]:
        """从字典列表获取配置（用于 API 动态添加）。"""
        return servers

    # ---- 工具管理 ----------------------------------------------------------

    def _rebuild_tool_index(self):
        """重建工具名称 → 服务器映射。"""
        self._tool_index = {}
        for server_name, conn in self.connections.items():
            if not conn.is_connected:
                continue
            try:
                tools = conn.list_tools()
                for tool in tools:
                    tool_name = tool["name"]
                    existing = self._tool_index.get(tool_name)
                    if existing:
                        logger.warning(
                            f"工具 '{tool_name}' 已被 '{existing['server']}' 注册,"
                            f" 将被 '{server_name}' 覆盖"
                        )
                    self._tool_index[tool_name] = {
                        "server": server_name,
                        "description": tool["description"],
                        "input_schema": tool["input_schema"],
                    }
            except Exception as e:
                logger.error(f"获取服务器 '{server_name}' 工具列表失败: {e}")
        logger.info(f"MCP 工具索引: {len(self._tool_index)} 个工具来自 {len(self.connections)} 个服务器")

    def get_all_tools(self) -> List[Dict[str, Any]]:
        """获取所有可用的 MCP 工具。"""
        return [
            {
                "name": name,
                "description": info["description"],
                "input_schema": info["input_schema"],
                "server": info["server"],
            }
            for name, info in self._tool_index.items()
        ]

    def get_tool_info(self, name: str) -> Optional[Dict[str, Any]]:
        """获取特定工具的信息。"""
        return self._tool_index.get(name)

    def get_server_info(self) -> List[Dict[str, Any]]:
        """获取所有服务器连接状态。"""
        result = []
        for name, conn in self.connections.items():
            result.append({
                "name": name,
                "transport": conn.config.get("transport", "stdio"),
                "connected": conn.is_connected,
                "tools_count": len(conn.list_tools()),
            })
        return result

    # ---- 工具执行 ----------------------------------------------------------

    def call_tool_sync(self, name: str, arguments: Dict[str, Any]) -> str:
        """同步调用 MCP 工具（从 Agent 线程调用）。"""
        info = self._tool_index.get(name)
        if not info:
            raise ValueError(f"未知 MCP 工具: {name}")

        server_name = info["server"]
        conn = self.connections.get(server_name)
        if not conn or not conn.is_connected:
            raise RuntimeError(f"MCP 服务器 '{server_name}' 未连接")

        return conn.call_tool(name, arguments)

    # ---- API 接口辅助 ------------------------------------------------------

    def get_config_snapshot(self) -> List[Dict]:
        """获取当前配置快照（用于 API 返回）。"""
        return [self._serialize_conn(name, conn) for name, conn in self.connections.items()]

    @staticmethod
    def _serialize_conn(name: str, conn: MCPServerConnection) -> Dict:
        return {
            "name": name,
            "transport": conn.config.get("transport", "stdio"),
            "connected": conn.is_connected,
            "tools_count": len(conn.list_tools()),
            "tools": [
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                }
                for t in conn.list_tools()
            ],
        }


# 全局单例
mcp_manager = MCPServerManager()
