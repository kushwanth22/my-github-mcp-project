# GitHub MCP Gateway

An OAuth 2.0 gateway that exposes the GitHub MCP server over Streamable HTTP, with scope-based access control and a LangGraph orchestrator for automated issue triage with human-in-the-loop approval.

## How it works

```
GitHub webhook → POST /webhook/github
                        ↓
              LangGraph orchestrator
                        ↓
     gather_context → draft_fix → [approval] → commit_fix
            ↑                           ↑
    agent-nightly-report       agent-issue-triager
       (github:read)           (github:read + write)
                        ↓
             POST /github/mcp  ← OAuth bearer token
                        ↓
         npx @modelcontextprotocol/server-github
```

The gateway handles OAuth 2.0 (authorization code + client credentials + PKCE + dynamic client registration), forwards scoped tool calls to the upstream GitHub MCP subprocess, and exposes custom tools alongside the built-in ones.

## Project structure

```
gateway/
  server.py              # app assembly
  oauth.py               # Authorization Server
  auth.py                # client-side token helper
  connectors/
    base.py              # MCPConnector ABC
    github.py            # GitHubConnector
  tools/
    base.py              # BaseTool ABC + ToolContext
    github/
      summarize_issue.py # custom tool example

agents/
  orchestrator.py        # LangGraph workflow
  nightly_report_agent.py
  issue_triager_agent.py

scripts/
  nightly_report.py      # raw JSON-RPC client
  issue_triager.py
  approve.py             # approve/reject pending fixes
```

## Quick start

**Prerequisites:** Python 3.11+, Node.js 20+, [uv](https://docs.astral.sh/uv/), [ngrok](https://ngrok.com)

```bash
# 1. Install dependencies
make install

# 2. Copy and fill in environment variables
cp .env.example .env

# 3. Start gateway + ngrok
make dev
```

## Environment variables

| Variable | Description |
|---|---|
| `GITHUB_TOKEN` | GitHub PAT for the upstream MCP server |
| `GITHUB_WEBHOOK_SECRET` | HMAC secret for webhook payload validation |
| `AGENT_NIGHTLY_REPORT_SECRET` | Client secret for the read-only agent |
| `AGENT_ISSUE_TRIAGER_SECRET` | Client secret for the issue triage agent |
| `ANTHROPIC_API_KEY` | For the orchestrator and custom tools |
| `MY_SERVER_DOMAIN` | Your public ngrok URL (used in OAuth discovery) |
| `MCP_GATEWAY_URL` | Same as `MY_SERVER_DOMAIN` (used by client scripts) |
| `MCP_INTERNAL_GATEWAY_URL` | Internal URL for orchestrator → gateway calls (default: `http://localhost:8000`) |

## Make targets

| Target | Description |
|---|---|
| `make install` | Install dependencies via uv |
| `make run` | Start gateway on `:8000` |
| `make ngrok` | Expose `:8000` via ngrok |
| `make dev` | Start gateway + ngrok together |
| `make lint` | Check code with ruff |
| `make format` | Auto-format with ruff |
| `make pre-commit` | Run all checks before committing |
| `make install-hooks` | Wire `pre-commit` to every `git commit` |
| `make pr` | Check + create GitHub PR |
| `make pr-merge` | Squash merge + delete branch |
| `make build` | Build Docker image |
| `make up / down / logs` | Docker lifecycle |
| `make pending` | List orchestrator approvals waiting |
| `make approve THREAD=<id> DECISION=approve\|reject` | Approve or reject a fix |

## OAuth scopes

| Scope | Permitted tools |
|---|---|
| `github:read` | All read/list/search operations |
| `github:issues:write` | `create_issue`, `update_issue`, `add_issue_comment` |
| `github:write` | All tools |

## Connecting via Claude.ai

The gateway is a fully compliant OAuth 2.0 MCP server — Claude.ai can connect to it directly.

1. Open **Claude.ai → Settings → Integrations**
2. Click **Add MCP server** and enter your public gateway URL:
   ```
   https://your-domain.ngrok-free.app
   ```
3. Claude.ai auto-discovers the OAuth endpoints via `/.well-known/oauth-authorization-server`, registers itself as a client (RFC 7591), and walks through the authorization code + PKCE flow
4. After authorizing, all GitHub MCP tools **and your custom tools** are available in every Claude.ai conversation

Claude.ai clients are automatically granted full scopes (`github:read`, `github:write`, `github:issues:write`) by the dynamic client registration handler.

> **Note:** `make dev` must be running so the ngrok tunnel is live when Claude.ai tries to connect.

## Adding a connector

Create `gateway/connectors/your_connector.py` subclassing `MCPConnector`, then add it to `CONNECTORS` in `gateway/server.py`. See `gateway/connectors/github.py` for a complete example.

## Adding a custom tool

Create `gateway/tools/<connector>/your_tool.py` with Pydantic `Input`/`Output` models and a `run()` method, then add it to `self._tools` in the connector's `__init__`. The base class handles schema generation, input validation, and output serialisation automatically.

## Human-in-the-loop approval

When the orchestrator proposes a fix, it pauses and waits for approval:

```bash
make pending                                      # see what's waiting
make approve THREAD=<id> DECISION=approve         # approve
make approve THREAD=<id> DECISION=reject          # reject
```
