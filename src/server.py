"""MCP server bootstrap and global state.

Initializes the FastMCP server, configures Weave tracing, and prepares the
configuration file before loading it. If a local config file is missing, the
server will fetch it from a remote endpoint based on environment variables.

Environment variables supported:
- CONFIG (optional): absolute/relative path to YAML config (legacy override)
- CONFIG_FILENAME: filename to use at repo root when CONFIG is not set
- VERSION: version segment to include in the remote config URL
- URL: base URL to fetch the config from
- API_KEY: API key to send as `X-API-Key` header when fetching

When CONFIG is not set and `<repo-root>/<CONFIG_FILENAME>` does not exist, the
server will GET `${URL}/${VERSION}/${CONFIG_FILENAME}` with header
`X-API-Key: ${API_KEY}`, then save it to `<repo-root>/<CONFIG_FILENAME>`.
"""

import logging
import os
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP
import wandb
import weave

from src.config import ConfigManager
from src.config.permissions import validate_config_schema

wandb.login(key=os.getenv("WANDB_API_KEY"))
weave.init("mcp-ssh")

# Create the MCP server
mcp: FastMCP = FastMCP("SSH_MCP", port=3000, debug=True, stateless_http=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-ssh")


def _project_root() -> Path:
    """Return the project root directory (one level above `src/`)."""
    return Path(__file__).resolve().parent.parent


def _mask_api_key(value: str, keep_start: int = 3, keep_end: int = 2) -> str:
    """Return a masked representation of an API key for logging.

    Examples:
        ABCDEFG -> ABC***FG
        ab -> **
    """
    if not value:
        return ""
    n = len(value)
    if n <= keep_start + keep_end:
        return "*" * n
    return f"{value[:keep_start]}***{value[-keep_end:]}"


def _ensure_config_file() -> Path:
    """Ensure the YAML config file exists locally and return its path.

    Priority:
    1) If CONFIG is set, use it directly (no remote fetch performed).
    2) Else, use <repo-root>/<CONFIG_FILENAME>. If missing, fetch from
       `${URL}/${VERSION}/${CONFIG_FILENAME}` with header `X-API-Key: ${API_KEY}`
       and write it locally, then return the local path.
    """

    # 1) Legacy explicit path override via CONFIG
    explicit_config = os.getenv("CONFIG")
    if explicit_config:
        logger.info("Using local config at %s (CONFIG env)", explicit_config)
        return Path(explicit_config)

    # 2) Use CONFIG_FILENAME at project root
    root = _project_root()
    config_filename = os.getenv("CONFIG_FILENAME", "config.yaml")
    config_path = root / config_filename

    if config_path.exists():
        logger.info("Using local config at %s", str(config_path))
        return config_path

    # File missing -> attempt remote fetch
    base_url = os.getenv("URL")
    version = os.getenv("VERSION")
    api_key = os.getenv("API_KEY")

    if not base_url or not version or not api_key:
        missing = [
            name
            for name, val in [("URL", base_url), ("VERSION", version), ("API_KEY", api_key)]
            if not val
        ]
        raise RuntimeError(
            "Config file not found locally and missing env variables: "
            + ", ".join(missing)
            + ". Required to fetch remote config."
        )

    fetch_url = f"{base_url.rstrip('/')}/{version}/{config_filename}"
    logger.info(
        "Retrieving online config at %s (X-API-Key: %s)",
        fetch_url,
        _mask_api_key(api_key),
    )
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(fetch_url, headers={"X-API-Key": api_key})
            resp.raise_for_status()
            # Write bytes as-is to preserve YAML formatting
            config_path.write_bytes(resp.content)
            logger.info("Saved config to %s", str(config_path))
    except httpx.HTTPError as e:
        raise RuntimeError(
            f"Failed to fetch config from {fetch_url}: {e}"
        ) from e

    return config_path


# Ensure config is present before creating the manager
_CONFIG_PATH = _ensure_config_file()
config_manager: ConfigManager = ConfigManager(_CONFIG_PATH)

# Validate the loaded configuration schema on startup for early feedback
try:
    validate_config_schema(config_manager.raw)
except Exception as e:
    # Surface clear startup error; FastMCP will log the exception
    raise RuntimeError(f"Invalid configuration schema: {e}")

# ruff: noqa: F401, E402
import src.SSH
