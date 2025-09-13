"""MCP server bootstrap and global state.

Initializes the FastMCP server, configures Weave tracing, and loads the
configuration manager and SSH tools package.
"""

import os

import weave
from mcp.server.fastmcp import FastMCP

from src.config import ConfigManager

weave.init("mcp-ssh")

# Create the MCP server
mcp: FastMCP = FastMCP("SSH_MCP", port=3000, debug=True, stateless_http=True)
config_manager: ConfigManager = ConfigManager(os.getenv("CONFIG"))

# ruff: noqa: F401, E402
import src.SSH
