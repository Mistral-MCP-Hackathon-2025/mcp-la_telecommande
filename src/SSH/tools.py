# ruff: noqa: I001
import os
from typing import Annotated, TypedDict

import paramiko
import weave

from src.server import mcp, config_manager
from src.config import VMCredentials
from .remote_executor import RemoteExecutor


def mask_value(value: str | None) -> str:
    if not value:
        return ""
    return "".join("*" if i % 2 else c for i, c in enumerate(value))


class BaseResult(TypedDict):
    status: str
    stdout: str
    stderr: str
    return_code: int


class RunCommandResult(BaseResult):
    command: str


@mcp.tool(
    name="list_vms",
    description="Give a list of available virtual machines.",
)
@weave.op()
def list_vms() -> dict[str, list[str]]:
    return {"vms": config_manager.list_vms()}


@mcp.tool(
    name="ssh_run_command",
    description="Run an arbitrary command on the given remote Virtual Machine and return stdout/stderr/rc.",
)
@weave.op()
def run_command(
    command: Annotated[str, "Shell command to execute remotely"],
    vm_name: str,
) -> RunCommandResult:
    creds: VMCredentials = config_manager.get_vm_creds(vm_name=vm_name)
    try:
        with RemoteExecutor(
            creds.host, creds.user, port=creds.port, key=creds.key
        ) as rx:
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
        print(
            f"SSH authentication failed. Debug: HOST={mask_value(creds.host)}, USERNAME={mask_value(creds.user)}, PORT={creds.port}, KEY_FILENAME={mask_value(creds.key)}"
        )
        raise ValueError(
            "SSH authentication failed. Check your USERNAME and KEY_FILENAME environment variables."
        )
    except paramiko.SSHException as e:
        print(
            f"SSH connection failed: {e}. Debug: HOST={mask_value(creds.host)}, USERNAME={mask_value(creds.user)}, PORT={creds.port}, KEY_FILENAME={mask_value(creds.key)}"
        )
        raise ValueError(f"SSH connection failed: {e}")
    except Exception as e:
        print(
            f"Unexpected error during SSH operation: {e}. Debug: HOST={mask_value(creds.host)}, USERNAME={mask_value(creds.user)}, PORT={creds.port}, KEY_FILENAME={mask_value(creds.key)}"
        )
        raise ValueError(f"Unexpected error during SSH operation: {e}")
