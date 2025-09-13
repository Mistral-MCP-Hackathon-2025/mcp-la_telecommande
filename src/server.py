from mcp.server.fastmcp import FastMCP

# Create the MCP server
mcp = FastMCP("SSH_MCP", port=3000, stateless_http=True, debug=True)

# ruff: noqa: F401, E402
import src.SSH
