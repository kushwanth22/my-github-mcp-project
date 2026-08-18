import contextvars
import logging
import time
from abc import ABC, abstractmethod
from contextlib import AsyncExitStack, asynccontextmanager

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from gateway.tools.base import BaseTool, ToolContext

logger = logging.getLogger(__name__)


class MCPConnector(ABC):
    endpoint: str
    server_params: StdioServerParameters
    scopes: list[str]
    default_clients: dict
    webhook_path: str | None = None

    def __init__(self):
        self._session: ClientSession | None = None
        self._session_manager: StreamableHTTPSessionManager | None = None
        self._token_var: contextvars.ContextVar = contextvars.ContextVar(
            f"token_{self.__class__.__name__}", default=None
        )
        self._mcp_server = Server(f"proxy-{self.__class__.__name__.lower()}")
        self._register_handlers()

    def custom_tools(self) -> list[BaseTool]:
        return []

    def _register_handlers(self):
        @self._mcp_server.list_tools()
        async def _list_tools() -> list[types.Tool]:
            scopes = self._current_scopes()
            result = await self._session.list_tools()
            upstream = [t for t in result.tools if self.tool_allowed(t.name, scopes)]
            return upstream + [t.to_mcp_tool() for t in self.custom_tools()]

        @self._mcp_server.call_tool()
        async def _call_tool(name: str, arguments: dict):
            custom_map = {t.name: t for t in self.custom_tools()}
            if name in custom_map:
                ctx = ToolContext(session=self._session)
                return await custom_map[name](arguments, ctx)
            scopes = self._current_scopes()
            if not self.tool_allowed(name, scopes):
                raise ValueError(f"Token not scoped for '{name}' (has: {sorted(scopes)})")
            result = await self._session.call_tool(name, arguments)
            return result.content

    def _current_scopes(self) -> set:
        entry = self._token_var.get()
        return set(entry["scopes"]) if entry else set()

    @abstractmethod
    def tool_allowed(self, tool_name: str, scopes: set) -> bool: ...

    def verify_webhook(self, body: bytes, headers: dict) -> bool:
        return True

    async def handle_webhook(self, payload: dict) -> None:
        pass

    @asynccontextmanager
    async def lifespan(self):
        async with AsyncExitStack() as stack:
            read, write = await stack.enter_async_context(stdio_client(self.server_params))
            self._session = await stack.enter_async_context(ClientSession(read, write))
            await self._session.initialize()
            self._session_manager = StreamableHTTPSessionManager(
                app=self._mcp_server, stateless=True
            )
            async with self._session_manager.run():
                logger.info(f"[{self.__class__.__name__}] started → {self.endpoint}")
                yield
        logger.info(f"[{self.__class__.__name__}] stopped")

    def make_asgi_app(self, access_tokens: dict):
        async def _asgi(scope, receive, send):
            headers = dict(scope.get("headers", []))
            auth = headers.get(b"authorization", b"").decode()
            token = auth.split(" ", 1)[1] if auth.lower().startswith("bearer ") else None
            entry = access_tokens.get(token) if token else None

            if not entry or entry["expires_at"] < time.time():
                await _send_401(send)
                return

            logger.info(
                f"[{self.endpoint}] client_id={entry['client_id']} scopes={entry['scopes']}"
            )
            self._token_var.set(entry)
            await self._session_manager.handle_request(scope, receive, send)

        return _RawASGIEndpoint(_asgi)


class _RawASGIEndpoint:
    def __init__(self, app):
        self._app = app

    async def __call__(self, scope, receive, send):
        await self._app(scope, receive, send)


async def _send_401(send):
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": b'{"detail":"Missing or invalid bearer token"}',
        }
    )
