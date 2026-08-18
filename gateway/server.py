import json
import logging
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, Form, HTTPException, Request

from agents.orchestrator import get_pending, resume_orchestrator
from gateway import oauth
from gateway.connectors.github import GitHubConnector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("server")

CONNECTORS = [
    GitHubConnector(),
    # JiraConnector(),  ← add future connectors here
]

for connector in CONNECTORS:
    oauth.REGISTERED_CLIENTS.update(connector.default_clients)
    oauth.SUPPORTED_SCOPES.update(connector.scopes)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncExitStack() as stack:
        for connector in CONNECTORS:
            await stack.enter_async_context(connector.lifespan())
        yield


app = FastAPI(title="MCP Gateway", lifespan=lifespan)
app.include_router(oauth.router)

for connector in CONNECTORS:
    app.add_route(
        connector.endpoint,
        connector.make_asgi_app(oauth.ACCESS_TOKENS),
        methods=["GET", "POST", "DELETE"],
    )

    if connector.webhook_path:

        def _make_webhook_handler(conn):
            async def _handler(request: Request):
                body = await request.body()
                if not conn.verify_webhook(body, dict(request.headers)):
                    raise HTTPException(status_code=401, detail="Invalid webhook signature")
                payload = json.loads(body)
                await conn.handle_webhook(payload)
                return {"status": "accepted"}

            return _handler

        app.add_api_route(
            connector.webhook_path,
            _make_webhook_handler(connector),
            methods=["POST"],
        )


@app.get("/pending")
async def list_pending():
    return get_pending()


@app.post("/approve/{thread_id}")
async def approve_endpoint(thread_id: str, decision: str = Form(...)):
    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'reject'")
    if thread_id not in get_pending():
        raise HTTPException(
            status_code=404, detail=f"No pending approval for thread_id={thread_id}"
        )
    result = await resume_orchestrator(thread_id, decision)
    return {"status": "done", "context": result.get("context", "")}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
