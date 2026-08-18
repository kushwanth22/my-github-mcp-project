# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

A GitHub MCP gateway with OAuth 2.0 and an AI orchestrator for automated issue triage. The gateway wraps the `@modelcontextprotocol/server-github` Node.js process and exposes it over Streamable HTTP with scope-based access control. LangGraph orchestrates multi-agent workflows with human-in-the-loop approval before committing changes.

## Common Commands

```bash
make install            # uv sync
make run                # start gateway on :8000
make ngrok              # expose :8000 via ngrok (static domain)
make dev                # run gateway + ngrok together (Ctrl+C stops both)
make build              # docker build
make up                 # docker run with .env
make down               # stop + remove container
make logs               # tail container logs
make pre-commit         # lint + format check (safe to commit?)
make install-hooks      # wire pre-commit to run on every git commit
make pr                 # run checks then gh pr create --fill
make pr-list            # list open PRs
make pr-view            # open current PR in browser
make pr-merge           # squash merge + delete branch
make pending            # list pending approvals
make approve THREAD=<id> DECISION=approve|reject
make nightly-report     # raw JSON-RPC script
make nightly-report-agent
make issue-triager      # raw JSON-RPC script
make issue-triager-agent
```

The ngrok domain is set to `jockey-drum-sloped.ngrok-free.dev` by default (matches `MY_SERVER_DOMAIN` in `.env`). Override with `make ngrok NGROK_DOMAIN=your-domain`.

## Required Environment Variables (.env)

| Variable | Purpose |
|---|---|
| `GITHUB_TOKEN` | PAT used by the upstream `@modelcontextprotocol/server-github` subprocess |
| `AGENT_NIGHTLY_REPORT_SECRET` | Client secret for the `agent-nightly-report` client (read-only) |
| `AGENT_ISSUE_TRIAGER_SECRET` | Client secret for the `agent-issue-triager` client (read + issues:write) |
| `GITHUB_WEBHOOK_SECRET` | HMAC secret for validating incoming GitHub webhook payloads |
| `MY_SERVER_DOMAIN` | Public base URL of this server (for OAuth discovery endpoints) |
| `MCP_GATEWAY_URL` | External gateway URL used by standalone client scripts (default: ngrok URL in code) |
| `MCP_INTERNAL_GATEWAY_URL` | Internal URL used by orchestrator agents (default: `http://localhost:8000`) |
| `ANTHROPIC_API_KEY` | Required by LangChain/Anthropic calls in orchestrator and agent scripts |

## Running Standalone Clients

These scripts talk to the running gateway:

```bash
uv run python3 scripts/nightly_report.py         # raw JSON-RPC: list repos
uv run python3 agents/nightly_report_agent.py    # LangChain agent: natural language summary
uv run python3 scripts/issue_triager.py          # raw JSON-RPC: label an issue + scope boundary test
uv run python3 agents/issue_triager_agent.py     # LangChain agent: auto-label unlabeled issues

# Approve or reject a pending orchestrator fix (server must be running)
uv run python3 scripts/approve.py <thread_id> approve|reject
```

## Architecture

### Request Flow

```
GitHub webhook → POST /webhook/github
                        ↓
                 orchestrator.py (LangGraph)
                        ↓
         gather_context → draft_fix → [interrupt] → commit_fix
                ↑                          ↑
         agent-nightly-report     agent-issue-triager
         (github:read)            (github:read + write)
                        ↓
                 POST /github/mcp  ← bearer token validated against ACCESS_TOKENS
                        ↓
                 mcp_server (Server) proxies to node_session
                        ↓
          stdio subprocess: npx @modelcontextprotocol/server-github
```

### Key Files

- **`gateway/server.py`** — App assembly: registers connectors, mounts OAuth router, webhook routes, and approval API (`/pending`, `/approve/{thread_id}`)
- **`gateway/oauth.py`** — Authorization Server: client store, `REGISTERED_CLIENTS`, `ACCESS_TOKENS`, all OAuth routes (`/well-known`, `/register`, `/authorize`, `/token`)
- **`gateway/connectors/base.py`** — `MCPConnector` ABC: manages the MCP subprocess lifecycle, merges upstream + custom tools, scope-filtered proxy, bearer token validation per request
- **`gateway/connectors/github.py`** — `GitHubConnector`: GitHub-specific tool permissions, webhook HMAC verification, triggers orchestrator on new issues, registers custom tools
- **`gateway/tools/base.py`** — `BaseTool` ABC + `ToolContext` dataclass; Pydantic input/output models auto-generate MCP JSON schema; `__call__` validates input and serialises output
- **`gateway/tools/github/`** — Custom tools for the GitHub connector (e.g. `summarize_issue.py`)
- **`gateway/auth.py`** — Client-side token helper used by agents; caches bearer tokens from `/token`; `INTERNAL_GATEWAY` vs `GATEWAY` distinguishes in-container vs external
- **`agents/orchestrator.py`** — LangGraph `StateGraph` with 4 nodes; uses `MemorySaver` (in-memory, lost on restart); `interrupt()` pauses for human approval
- **`agents/`** — LangChain agent scripts (`nightly_report_agent.py`, `issue_triager_agent.py`)
- **`scripts/`** — raw JSON-RPC client scripts (`nightly_report.py`, `issue_triager.py`) and `approve.py`

### Adding a Custom Tool

1. Create `gateway/tools/<connector>/your_tool.py` with Pydantic `Input` and `Output` models and a `run()` method:
   ```python
   class YourToolInput(BaseModel):
       field: str


   class YourToolOutput(BaseModel):
       result: str


   class YourTool(BaseTool):
       name = "your_tool"
       description = "..."
       input_model = YourToolInput
       output_model = YourToolOutput

       async def run(self, args: YourToolInput, ctx: ToolContext) -> YourToolOutput:
           # ctx.session gives access to the upstream MCP session
           ...
   ```
2. Add it to `self._tools` in the connector's `__init__`. That's it — `list_tools` and `call_tool` are handled automatically by the base class.

### Scope Enforcement

`GitHubConnector.tool_allowed()` maps bearer token scopes to permitted MCP tool names:
- `github:read` — all `READ_ONLY_TOOLS` (search, get, list operations)
- `github:issues:write` — additionally `create_issue`, `update_issue`, `add_issue_comment`
- `github:write` — all tools

Custom tools bypass scope enforcement and are always available to any authenticated token.

### OAuth Clients

Two pre-registered machine clients are seeded from `GitHubConnector.default_clients`. Dynamic client registration (RFC 7591) via `POST /register` allows Claude.ai to register at runtime; redirect URIs are restricted to `claude.ai`.

### Human-in-the-Loop Approval

When the orchestrator reaches `request_consent_node`, it calls `interrupt()` which pauses the LangGraph run and stores the thread in `_pending` (in-memory dict). Resume via:
- `POST /approve/{thread_id}` with `decision=approve|reject`
- `python3 approve.py <thread_id> approve|reject` (calls `localhost:8000`)

## RocketRide

This project includes RocketRide AI pipeline tooling. See `.rocketride/docs/` and the rules in `.claude/rules/rocketride.md` before writing any pipeline code.
