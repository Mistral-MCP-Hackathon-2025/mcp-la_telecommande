from fastmcp import FastMCP

# Create the MCP server
mcp = FastMCP(
    name="MCP SSH",
    instructions="This MCP allows managing remote servers via SSH. Use the provided tools to execute commands and manage files on the remote host.",
    version="1.0.0"
)

# ruff: noqa: F401, E402
import src.SSH