from mcp.server.fastmcp import FastMCP
from remoteExecutor import RemoteExecutor
import os
from dotenv import load_dotenv

load_dotenv()

mcp = FastMCP("RemoteExecutor", host="0.0.0.0")

@mcp.tool()
def create_file(filename: str) -> dict:
    with RemoteExecutor(os.getenv('HOST'), os.getenv('USER'), key_filename=os.getenv('KEY_FILENAME'), port=int(os.getenv('PORT'))) as rx:
        stdout, stderr, rc = rx.run(f"touch {filename}")
        if rc != 0:
            raise ValueError(f"Error creating file: {stderr}")
        return {
            "filename": filename,
            "status": "created",
            "stdout": stdout.strip(),
            "stderr": stderr.strip(),
            "return_code": rc
        }

@mcp.tool()
def run_command(command: str) -> dict:
    with RemoteExecutor(os.getenv('HOST'), os.getenv('USER'), key_filename=os.getenv('KEY_FILENAME'), port=int(os.getenv('PORT'))) as rx:
        stdout, stderr, rc = rx.run(command)
        if rc != 0:
            raise ValueError(f"Error running command: {stderr}")
        return {
            "command": command,
            "status": "executed",
            "stdout": stdout.strip(),
            "stderr": stderr.strip(),
            "return_code": rc
        }

if __name__ == "__main__":
    mcp.run(transport="stdio")
