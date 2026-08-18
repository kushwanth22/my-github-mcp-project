import asyncio
import hashlib
import hmac
import logging
import os

from mcp import StdioServerParameters

from agents.orchestrator import start_orchestrator
from gateway.connectors.base import MCPConnector
from gateway.tools.base import BaseTool
from gateway.tools.github.summarize_issue import SummarizeIssueTool

logger = logging.getLogger(__name__)

READ_ONLY_TOOLS = {
    "search_repositories",
    "get_file_contents",
    "list_issues",
    "get_issue",
    "search_issues",
    "list_commits",
    "list_pull_requests",
    "get_pull_request",
    "get_pull_request_files",
    "get_pull_request_comments",
    "get_pull_request_reviews",
    "get_pull_request_status",
    "search_code",
    "search_users",
}
ISSUE_WRITE_TOOLS = {"create_issue", "update_issue", "add_issue_comment"}


class GitHubConnector(MCPConnector):
    endpoint = "/github/mcp"
    scopes = ["github:read", "github:write", "github:issues:write"]
    webhook_path = "/webhook/github"

    def __init__(self):
        github_token = os.environ.get("GITHUB_TOKEN", "")
        self.server_params = StdioServerParameters(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={
                **os.environ,
                "GITHUB_TOKEN": github_token,
                "GITHUB_PERSONAL_ACCESS_TOKEN": github_token,
            },
        )
        self.default_clients = {
            "agent-nightly-report": {
                "client_secret": os.environ.get("AGENT_NIGHTLY_REPORT_SECRET", ""),
                "scopes": ["github:read"],
                "kind": "agent",
            },
            "agent-issue-triager": {
                "client_secret": os.environ.get("AGENT_ISSUE_TRIAGER_SECRET", ""),
                "scopes": ["github:read", "github:issues:write", "github:write"],
                "kind": "agent",
            },
        }
        self._tools: list[BaseTool] = [SummarizeIssueTool()]
        super().__init__()

    def custom_tools(self) -> list[BaseTool]:
        return self._tools

    def tool_allowed(self, tool_name: str, scopes: set) -> bool:
        has_write = "github:write" in scopes
        has_issue_write = "github:issues:write" in scopes or has_write
        if tool_name in READ_ONLY_TOOLS:
            return True
        if tool_name in ISSUE_WRITE_TOOLS:
            return has_issue_write
        return has_write

    def verify_webhook(self, body: bytes, headers: dict) -> bool:
        secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
        signature = headers.get("x-hub-signature-256", "")
        expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    async def handle_webhook(self, payload: dict) -> None:
        if payload.get("action") == "opened" and "issue" in payload:

            async def _run():
                try:
                    await start_orchestrator(
                        owner=payload["repository"]["owner"]["login"],
                        repo=payload["repository"]["name"],
                        issue_number=payload["issue"]["number"],
                    )
                except Exception:
                    logger.exception("[handle_webhook] orchestrator failed")

            asyncio.create_task(_run())
