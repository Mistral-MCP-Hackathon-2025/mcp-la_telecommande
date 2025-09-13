from mcp.server.fastmcp import FastMCP

# Create the MCP server
mcp = FastMCP("SSH_MCP", port=3000, debug=True)

# ruff: noqa: F401, E402
import src.SSH
import src.qdrant
