from mcp.server.fastmcp import FastMCP
import weave

weave.init('mcp-ssh')

# Create the MCP server
mcp = FastMCP("SSH_MCP", port=3000, debug=True, stateless_http=True)

# ruff: noqa: F401, E402
import src.SSH
