# ruff: noqa: I001
import os
from typing import Annotated, TypedDict

from src.server import mcp
from .remote_executor import RemoteExecutor


class BaseResult(TypedDict):
    status: str
    stdout: str
    stderr: str
    return_code: int


class CreateFileResult(BaseResult):
    filename: str


class RunCommandResult(BaseResult):
    command: str


def _get_env_creds() -> tuple[str, str, int, str | None]:
    host = os.getenv("HOST")
    user = os.getenv("USER")
    key_filename = os.getenv("KEY_FILENAME")
    port = int(os.getenv("PORT", "22"))
    if not host or not user:
        raise ValueError(
            "Missing HOST or USER environment variables for SSH connection"
        )
    return host, user, port, key_filename


@mcp.tool(
    name="ssh_create_file",
    description="Create an empty file on the remote host using 'touch'.",
    # tags={"ssh", "filesystem", "remote"},
)
def create_file(
    filename: Annotated[str, "Remote filename to create"],
) -> CreateFileResult:
    host, user, port, key_filename = _get_env_creds()
    with RemoteExecutor(host, user, key_filename=key_filename, port=port) as rx:
        stdout, stderr, rc = rx.run(f"touch {filename}")
        if rc != 0:
            raise ValueError(f"Error creating file: {stderr}")
        return {
            "filename": filename,
            "status": "created",
            "stdout": stdout.strip(),
            "stderr": stderr.strip(),
            "return_code": rc,
        }


@mcp.tool(
    name="ssh_run_command",
    description="Run an arbitrary command on the remote host and return stdout/stderr/rc.",
    # tags={"ssh", "remote", "exec"},
)
def run_command(
    command: Annotated[str, "Shell command to execute remotely"],
) -> RunCommandResult:
    host, user, port, key_filename = _get_env_creds()
    with RemoteExecutor(host, user, key_filename=key_filename, port=port) as rx:
        stdout, stderr, rc = rx.run(command)
        if rc != 0:
            raise ValueError(f"Error running command: {stderr}")
        return {
            "command": command,
            "status": "executed",
            "stdout": stdout.strip(),
            "stderr": stderr.strip(),
            "return_code": rc,
        }
