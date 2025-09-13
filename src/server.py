from fastmcp import FastMCP

# Create the MCP server
mcp = FastMCP(
    name="SampleProject",
    instructions="A playground MCP server showcasing all advanced features.",
    version="1.0.0"
)

# ruff: noqa: F401, E402
import src.SSH