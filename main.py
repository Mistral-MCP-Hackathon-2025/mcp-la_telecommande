from dotenv import load_dotenv

load_dotenv()

# ruff: noqa: E402
from src.server import mcp  # noqa: F401

if __name__ == "__main__":
    mcp.run(
        transport="streamable-http"
    )  # Use "streamable-http" for Alpic compatibility
