from fastmcp import FastMCP

# Create the MCP server
mcp = FastMCP(
    name="SampleProject",
    instructions="A playground MCP server showcasing all advanced features.",
    version="1.0.0",
    port=3000,
    stateless_http=True,
    debug=True,
)

# ruff: noqa: F401, E402
import src.SSH
