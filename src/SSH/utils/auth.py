"""Authorization helpers for MCP tools.

Currently supports extracting API keys from the FastMCP Context headers.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context


def extract_api_key_from_headers(ctx: Context) -> str | None:
    """Retrieve API key from the Authorization header in request context.

    Accepts either `Authorization: Bearer <API_KEY>` or a raw value.
    Returns the extracted API key string or None if not found.
    """
    headers: dict[str, Any] | None = None
    try:
        req = getattr(ctx.request_context, "request", None)
        if req is not None:
            headers = getattr(req, "headers", None)
        if headers is None:
            headers = getattr(ctx.request_context, "headers", None)
        if headers is None:
            meta = getattr(ctx.request_context, "meta", None)
            if isinstance(meta, dict):
                headers = meta.get("headers")
    except Exception:
        headers = None

    auth: str | None = None
    if headers:
        # support dict-like headers
        auth = headers.get("Authorization") or headers.get("authorization")
    if not auth:
        return None
    auth = str(auth).strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return auth or None
