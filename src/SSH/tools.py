# ruff: noqa: I001
import os
from typing import Annotated, TypedDict

import paramiko

from src.server import mcp
from .remote_executor import RemoteExecutor


def mask_value(value: str | None) -> str:
    if not value:
        return ""
    return ''.join('*' if i % 2 else c for i, c in enumerate(value))


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
    user = os.getenv("USERNAME")
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
    try:
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
    except paramiko.AuthenticationException:
        print(f"SSH authentication failed. Debug: HOST={mask_value(host)}, USERNAME={mask_value(user)}, PORT={port}, KEY_FILENAME={mask_value(key_filename)}")
        raise ValueError("SSH authentication failed. Check your USERNAME and KEY_FILENAME environment variables.")
    except paramiko.SSHException as e:
        print(f"SSH connection failed: {e}. Debug: HOST={mask_value(host)}, USERNAME={mask_value(user)}, PORT={port}, KEY_FILENAME={mask_value(key_filename)}")
        raise ValueError(f"SSH connection failed: {e}")
    except Exception as e:
        print(f"Unexpected error during SSH operation: {e}. Debug: HOST={mask_value(host)}, USERNAME={mask_value(user)}, PORT={port}, KEY_FILENAME={mask_value(key_filename)}")
        raise ValueError(f"Unexpected error during SSH operation: {e}")


@mcp.tool(
    name="ssh_run_command",
    description="Run an arbitrary command on the remote host and return stdout/stderr/rc.",
    # tags={"ssh", "remote", "exec"},
)
def run_command(
    command: Annotated[str, "Shell command to execute remotely"],
) -> RunCommandResult:
    host, user, port, key_filename = _get_env_creds()
    try:
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
    except paramiko.AuthenticationException:
        print(f"SSH authentication failed. Debug: HOST={mask_value(host)}, USERNAME={mask_value(user)}, PORT={port}, KEY_FILENAME={mask_value(key_filename)}")
        raise ValueError("SSH authentication failed. Check your USERNAME and KEY_FILENAME environment variables.")
    except paramiko.SSHException as e:
        print(f"SSH connection failed: {e}. Debug: HOST={mask_value(host)}, USERNAME={mask_value(user)}, PORT={port}, KEY_FILENAME={mask_value(key_filename)}")
        raise ValueError(f"SSH connection failed: {e}")
    except Exception as e:
        print(f"Unexpected error during SSH operation: {e}. Debug: HOST={mask_value(host)}, USERNAME={mask_value(user)}, PORT={port}, KEY_FILENAME={mask_value(key_filename)}")
        raise ValueError(f"Unexpected error during SSH operation: {e}")
