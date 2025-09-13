"""MCP server bootstrap and global state.

Initializes the FastMCP server, configures Weave tracing, and loads the
configuration manager and SSH tools package. The global `mcp` and
`config_manager` objects are imported by `main.py` and tool modules.
"""

import os

import weave
from mcp.server.fastmcp import FastMCP

from src.config import ConfigManager
from src.config.permissions import validate_config_schema

weave.init("mcp-ssh")

# Create the MCP server
mcp: FastMCP = FastMCP("SSH_MCP", port=3000, debug=True, stateless_http=True)
config_manager: ConfigManager = ConfigManager(os.getenv("CONFIG"))

# Validate the loaded configuration schema on startup for early feedback
try:
	validate_config_schema(config_manager.raw)
except Exception as e:
	# Surface clear startup error; FastMCP will log the exception
	raise RuntimeError(f"Invalid configuration schema: {e}")

# ruff: noqa: F401, E402
import src.SSH
