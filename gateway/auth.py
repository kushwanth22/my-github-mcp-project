import asyncio
import os
import time

import requests

GATEWAY = os.environ.get("MCP_GATEWAY_URL", "https://jockey-drum-sloped.ngrok-free.dev")
MCP_PATH = "/github/mcp"

INTERNAL_GATEWAY = os.environ.get("MCP_INTERNAL_GATEWAY_URL", "http://localhost:8000")


# gateway_auth.py
def get_gateway_token(
    client_id: str, client_secret_env: str, scope: str, base_url: str = None
) -> str:
    base = base_url or GATEWAY
    cache_key = f"_token_cache_{client_id}_{scope}_{base}"
    cache = getattr(get_gateway_token, cache_key, None)

    if cache and time.time() < cache["expires_at"] - 30:
        return cache["access_token"]

    secret = os.environ[client_secret_env]
    resp = requests.post(
        f"{base}/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": secret,
            "scope": scope,
        },
    )
    resp.raise_for_status()
    data = resp.json()

    setattr(
        get_gateway_token,
        cache_key,
        {
            "access_token": data["access_token"],
            "expires_at": time.time() + data["expires_in"],
        },
    )
    return data["access_token"]


async def get_gateway_token_async(
    client_id: str, client_secret_env: str, scope: str, base_url: str = None
) -> str:
    return await asyncio.to_thread(get_gateway_token, client_id, client_secret_env, scope, base_url)
