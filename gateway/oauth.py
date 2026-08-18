import base64
import hashlib
import hmac
import os
import secrets
import time
from urllib.parse import urlparse

from fastapi import APIRouter, Form, Header, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

ALLOWED_REDIRECT_HOSTS = {"claude.ai"}

REGISTERED_CLIENTS: dict = {}
AUTH_CODES: dict = {}
ACCESS_TOKENS: dict = {}
SUPPORTED_SCOPES: set[str] = set()

router = APIRouter()


def get_domain() -> str:
    return os.environ.get("MY_SERVER_DOMAIN", "https://jockey-drum-sloped.ngrok-free.dev")


@router.get("/.well-known/oauth-authorization-server")
async def oauth_discovery():
    domain = get_domain()
    return {
        "issuer": domain,
        "authorization_endpoint": f"{domain}/authorize",
        "token_endpoint": f"{domain}/token",
        "registration_endpoint": f"{domain}/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "client_credentials"],
        "code_challenge_methods_supported": ["S256", "plain"],
        "token_endpoint_auth_methods_supported": [
            "client_secret_post",
            "client_secret_basic",
            "none",
        ],
        "scopes_supported": sorted(SUPPORTED_SCOPES),
    }


@router.post("/register")
async def register_client(request: Request):
    body = await request.json()
    redirect_uris = body.get("redirect_uris", [])

    for uri in redirect_uris:
        host = urlparse(uri).hostname
        if host not in ALLOWED_REDIRECT_HOSTS:
            raise HTTPException(status_code=400, detail=f"redirect_uri host not allowed: {host}")

    client_id = secrets.token_urlsafe(16)
    client_secret = secrets.token_urlsafe(32)

    is_claude = any(urlparse(uri).hostname == "claude.ai" for uri in redirect_uris)
    scopes = (
        sorted(SUPPORTED_SCOPES)
        if is_claude
        else [s for s in sorted(SUPPORTED_SCOPES) if s.endswith(":read")]
    )

    REGISTERED_CLIENTS[client_id] = {
        "client_secret": client_secret,
        "redirect_uris": redirect_uris,
        "scopes": scopes,
        "kind": "dcr",
    }

    return JSONResponse(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "client_id_issued_at": int(time.time()),
            "client_secret_expires_at": 0,
            "redirect_uris": redirect_uris,
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "client_secret_post",
        }
    )


@router.get("/authorize")
async def oauth_authorize(
    client_id: str,
    redirect_uri: str,
    state: str,
    response_type: str = "code",
    code_challenge: str = None,
    code_challenge_method: str = "S256",
):
    if client_id not in REGISTERED_CLIENTS:
        raise HTTPException(status_code=400, detail="Invalid Client ID")
    if response_type != "code":
        raise HTTPException(status_code=400, detail="Only 'code' response_type supported")

    code = secrets.token_urlsafe(24)
    AUTH_CODES[code] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "expires_at": time.time() + 600,
    }
    return RedirectResponse(f"{redirect_uri}?code={code}&state={state}")


def _verify_pkce(code_verifier: str, code_challenge: str, method: str) -> bool:
    if not code_challenge:
        return True
    if not code_verifier:
        return False
    if method == "plain":
        return code_verifier == code_challenge
    digest = hashlib.sha256(code_verifier.encode()).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return computed == code_challenge


@router.post("/token")
async def oauth_token(
    request: Request,
    grant_type: str = Form(None),
    code: str = Form(None),
    redirect_uri: str = Form(None),
    client_id: str = Form(None),
    client_secret: str = Form(None),
    code_verifier: str = Form(None),
    scope: str = Form(None),
    authorization: str = Header(None),
):
    if (
        (not client_id or not client_secret)
        and authorization
        and authorization.lower().startswith("basic ")
    ):
        try:
            decoded = base64.b64decode(authorization.split(" ", 1)[1]).decode()
            client_id, client_secret = decoded.split(":", 1)
        except Exception:
            raise HTTPException(status_code=401, detail="Malformed Authorization header")

    client = REGISTERED_CLIENTS.get(client_id)
    if not client or not hmac.compare_digest(client["client_secret"], client_secret or ""):
        raise HTTPException(status_code=401, detail="Invalid client credentials")

    if grant_type == "client_credentials":
        requested = set((scope or "").split()) or set(client["scopes"])
        granted = requested & set(client["scopes"])
        if not granted:
            raise HTTPException(status_code=403, detail="No permitted scopes for this client")

        token = secrets.token_urlsafe(32)
        ACCESS_TOKENS[token] = {
            "client_id": client_id,
            "scopes": list(granted),
            "expires_at": time.time() + 3600,
        }
        return {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": " ".join(granted),
        }

    if grant_type != "authorization_code":
        raise HTTPException(status_code=400, detail="Unsupported grant_type")

    entry = AUTH_CODES.pop(code, None)
    if not entry or entry["expires_at"] < time.time():
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    if entry["client_id"] != client_id:
        raise HTTPException(status_code=400, detail="Client mismatch")
    if entry["redirect_uri"] != redirect_uri:
        raise HTTPException(status_code=400, detail="redirect_uri mismatch")
    if not _verify_pkce(code_verifier, entry["code_challenge"], entry["code_challenge_method"]):
        raise HTTPException(status_code=400, detail="PKCE verification failed")

    token = secrets.token_urlsafe(32)
    ACCESS_TOKENS[token] = {
        "client_id": client_id,
        "scopes": client["scopes"],
        "expires_at": time.time() + 3600,
    }

    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": " ".join(client["scopes"]),
    }
