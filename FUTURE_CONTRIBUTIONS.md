# Future Contributions

Deferred improvements to pick up in future sessions.

## 1. Migrate to official GitHub MCP server
`@modelcontextprotocol/server-github` is deprecated. Switch to the official GitHub MCP server.
- Package: `@github/mcp-server`
- Uses `GITHUB_TOKEN` env var (already passed)
- One-line change in `gateway/connectors/github.py` args

## 2. Bake npm package into Docker image
Instead of `npx -y` downloading at runtime, install at build time:
```dockerfile
RUN npm install -g @github/mcp-server
```
No runtime download, no supply chain risk, auditable at build time. Do this together with item 1.

## 3. Enterprise SSO for consent layer
Replace the basic `/authorize` HTML page with Auth0 / ScaleKit / WorkOS so users can log in via Gmail, Okta, Azure AD etc. Gateway still owns token issuance and scope enforcement — identity provider handles authentication only.

## 4. Token hardening
Current tokens are in-memory with a fixed TTL — no rotation, no revocation, lost on restart.
- Shorten `expires_in` (e.g. 15 minutes)
- Add `POST /revoke` endpoint to invalidate live tokens
- Persist `ACCESS_TOKENS` to Redis or SQLite so gateway restarts don't force all clients to re-auth
- Add automatic token rotation mid-session for long-lived agent workflows

## 5. Langfuse tracing
Add full agent observability — which tools each node called, in what order, with inputs and outputs. Langfuse is open-source, self-hostable, and works with LangChain/LangGraph via a callback handler.
```env
LANGFUSE_PUBLIC_KEY=<your key>
LANGFUSE_SECRET_KEY=<your key>
LANGFUSE_HOST=https://cloud.langfuse.com  # or self-hosted
```
Then view traces at cloud.langfuse.com or your self-hosted instance.
