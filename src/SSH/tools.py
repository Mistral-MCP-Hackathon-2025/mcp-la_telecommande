"""MCP tools that expose SSH actions.

This module registers MCP tools for listing accessible VMs and running commands
remotely via the `RemoteExecutor`. Helpers and TypedDicts are organized in
`src/SSH/utils/` for clarity and reuse.

Tools provided:
- `ssh_list_vms()`: Return only the VM names the caller may access.
- `ssh_run_command(command, vm_name)`: Run a command on a permitted VM.
- `ssh_is_vm_up(vm_name)`: Quick reachability check (TCP connect to SSH).
- `ssh_vm_distro_info(vm_name)`: Collect distro/platform debug info.
"""

# ruff: noqa: I001
from typing import Annotated

import paramiko
import weave
import uuid

from src.qdrant.log_manager import log_ssh_operation
from src.server import mcp, config_manager
from src.config import VMCredentials
from src.config.permissions import permissions_enabled, find_user_by_api_key

from .remote_executor import RemoteExecutor
from mcp.server.fastmcp import Context

from src.SSH.utils.auth import extract_api_key_from_headers
from src.SSH.utils.masking import mask_value
from src.SSH.utils.network import tcp_reachable
from src.SSH.utils.osinfo import parse_os_release, detect_pkg_manager
from src.SSH.utils.types import (
    ListVMsResult,
    RunCommandResult,
    VMUpResult,
    VMInfoResult,
)


# -----------------------
# Helper utilities (local)
# -----------------------


# Local helpers moved to utils: extract_api_key_from_headers, mask_value,
# tcp_reachable, parse_os_release, detect_pkg_manager


@mcp.tool(
    name="ssh_list_vms",
    description=(
        "List VM names the caller is allowed to access. Authorization is derived from the HTTP Authorization header "
        "present in the MCP request context. Expected formats: 'Bearer <API_KEY>' or a raw API key string. "
        "When permissions are disabled in the YAML (no users/groups), this tool returns all configured VMs.\n\n"
        "Returns: { vms: string[] } — list of VM names that are accessible for the provided API key.\n\n"
        "Errors: Raises ValueError if permissions are enabled and the Authorization header is missing/invalid.\n\n"
        "Important: Clients MUST call this first to discover allowed VMs, and MUST NOT attempt to run commands on VMs "
        "not present in the returned list."
    ),
)
@weave.op()
def ssh_list_vms(ctx: Context) -> ListVMsResult:
    """Return only the VM names accessible to the caller.

    Authorization:
        - If permissions are enabled in the YAML, an API key MUST be provided via the Authorization header.
        - If disabled (no users/groups defined), all VMs are returned.
    """
    if permissions_enabled(config_manager.raw):
        api_key = extract_api_key_from_headers(ctx)
        if not api_key:
            raise ValueError("API key invalid or VM not permitted")
        return {"vms": config_manager.authorized_vms_for_key(api_key)}
    return {"vms": config_manager.list_vms()}


@mcp.tool(
    name="ssh_run_command",
    description=(
        "Execute a shell command on a permitted VM over SSH and return results. Authorization is derived from the HTTP "
        "Authorization header in the MCP request context.\n\n"
        "Parameters:\n"
        "- command (string): Shell command to execute remotely. The command runs under '/bin/bash -lc' with a login-like shell.\n"
        "- vm_name (string): Name of the target VM as defined in the YAML configuration.\n"
        "Returns: { command: string, status: 'executed', stdout: string, stderr: string, return_code: number }.\n\n"
        "Errors: Raises ValueError on authorization failure, SSH connection/authentication failures, or non-zero return codes.\n\n"
        "Important: Clients MUST ensure vm_name is present in the list returned by 'ssh_list_vms' before invoking this tool."
    ),
)
@weave.op()
def run_command(
    command: Annotated[str, "Shell command to execute remotely (bash -lc)."],
    vm_name: Annotated[str, "Name of a permitted VM from ssh_list_vms"],
    ctx: Context,
) -> RunCommandResult:
    """Execute a shell command on the specified VM via SSH.

    Args:
        command: The shell command to execute remotely.
        vm_name: Name of the VM defined in the YAML configuration.

    Returns:
        A dictionary including the command, status, stdout, stderr, and return code.

    Raises:
        ValueError: When authentication fails, the connection fails, or the
            remote command exits non-zero.
    """
    # Enforce authorization if permissions are enabled
    if permissions_enabled(config_manager.raw):
        api_key = extract_api_key_from_headers(ctx)
        if not api_key:
            raise ValueError("API key invalid or VM not permitted")
        config_manager.ensure_can_access(api_key, vm_name)
        user_obj = find_user_by_api_key(config_manager.raw, api_key)
        requested_by = user_obj.get("name") if user_obj else None
    else:
        requested_by = None

    creds: VMCredentials = config_manager.get_vm_creds(vm_name=vm_name)
    job_id = str(uuid.uuid4())
    stdout, stderr, rc = "", "", 0
    try:
        with RemoteExecutor(
            creds.host, creds.user, port=creds.port, key=creds.key
        ) as rx:
            stdout, stderr, rc = rx.run(command)

            if rc != 0:
                raise ValueError(f"Error running command: {stderr}")

            log_ssh_operation(
                job_id=job_id,
                vm_name=vm_name,
                command=command,
                result={"stdout": stdout, "stderr": stderr, "return_code": rc},
                requested_by=requested_by,
            )

            return {
                "status": "executed",
                "stdout": stdout.strip(),
                "stderr": stderr.strip(),
                "return_code": rc,
                "command": command,
            }
    except paramiko.AuthenticationException:
        print(
            f"SSH authentication failed. Debug: HOST={mask_value(creds.host)}, USERNAME={mask_value(creds.user)}, PORT={creds.port}, KEY_FILENAME={mask_value(creds.key)}"
        )
        log_ssh_operation(
            job_id=job_id,
            vm_name=vm_name,
            command=command,
            result={
                "stdout": stdout,
                "stderr": f"Authentication failed: {stderr}",
                "return_code": rc,
            },
            requested_by=requested_by,
        )
        raise ValueError(
            "SSH authentication failed. Check your USERNAME and KEY_FILENAME environment variables."
        )
    except paramiko.SSHException as e:
        print(
            f"SSH connection failed: {e}. Debug: HOST={mask_value(creds.host)}, USERNAME={mask_value(creds.user)}, PORT={creds.port}, KEY_FILENAME={mask_value(creds.key)}"
        )
        log_ssh_operation(
            job_id=job_id,
            vm_name=vm_name,
            command=command,
            result={
                "stdout": "",
                "stderr": f"SSH connection failed: {e}",
                "return_code": rc,
            },
            requested_by=requested_by,
        )
        raise ValueError(f"SSH connection failed: {e}")
    except Exception as e:
        print(
            f"Unexpected error during SSH operation: {e}. Debug: HOST={mask_value(creds.host)}, USERNAME={mask_value(creds.user)}, PORT={creds.port}, KEY_FILENAME={mask_value(creds.key)}"
        )
        log_ssh_operation(
            job_id=job_id,
            vm_name=vm_name,
            command=command,
            result={"stdout": "", "stderr": str(e), "return_code": rc},
            requested_by=requested_by,
        )
        raise ValueError(f"Unexpected error during SSH operation: {e}")


# ---------------------------------
# New tool: quick VM reachability
# ---------------------------------


@mcp.tool(
    name="ssh_is_vm_up",
    description=(
        "Check if the VM's SSH port is reachable (simple TCP connect) and measure approximate latency.\n\n"
        "Parameters:\n"
        "- vm_name (string): Name of the target VM as defined in the YAML configuration.\n"
        "Returns: { vm, host, port, reachable, latency_ms, reason }. 'latency_ms' is a rough client-side measurement.\n\n"
        "Errors: Raises ValueError if authorization fails when permissions are enabled.\n\n"
        "Important: Use this as a lightweight pre-check before attempting SSH commands."
    ),
)
@weave.op()
def ssh_is_vm_up(vm_name: str, ctx: Context) -> VMUpResult:
    """Return whether the VM's SSH port is reachable along with latency."""
    if permissions_enabled(config_manager.raw):
        api_key = extract_api_key_from_headers(ctx)
        if not api_key:
            raise ValueError("API key invalid or VM not permitted")
        config_manager.ensure_can_access(api_key, vm_name)
    creds: VMCredentials = config_manager.get_vm_creds(vm_name=vm_name)
    reachable, latency_ms, reason = tcp_reachable(creds.host, creds.port)
    return {
        "vm": vm_name,
        "host": creds.host,
        "port": creds.port,
        "reachable": reachable,
        "latency_ms": latency_ms,
        "reason": reason,
    }


# ---------------------------------
# New tool: distro + debug signals
# ---------------------------------


# Types imported at top: VMInfoResult


@mcp.tool(
    name="ssh_vm_distro_info",
    description=(
        "Retrieve Linux distro and platform debugging info by running safe discovery commands over SSH.\n\n"
        "Parameters:\n"
        "- vm_name (string): Name of the target VM as defined in the YAML configuration.\n"
        "Returns: { vm, host, port, status: 'ok'|'unknown', distro, platform, network, user, notes[] }.\n\n"
        "Errors: Raises ValueError on authorization failure or SSH errors.\n\n"
        "Important: This tool is read-only and intended for diagnostics (no configuration changes)."
    ),
)
@weave.op()
def ssh_vm_distro_info(vm_name: str, ctx: Context) -> VMInfoResult:
    if permissions_enabled(config_manager.raw):
        api_key = extract_api_key_from_headers(ctx)
        if not api_key:
            raise ValueError("API key invalid or VM not permitted")
        config_manager.ensure_can_access(api_key, vm_name)
    creds: VMCredentials = config_manager.get_vm_creds(vm_name=vm_name)
    result: VMInfoResult = {
        "vm": vm_name,
        "host": creds.host,
        "port": creds.port,
        "status": "unknown",
        "distro": {},
        "platform": {},
        "network": {"addresses": []},
        "user": {},
        "notes": [],
    }

    try:
        with RemoteExecutor(
            creds.host, creds.user, port=creds.port, key=creds.key
        ) as rx:
            # 1) Distro: /etc/os-release
            out, err, rc = rx.run("cat /etc/os-release 2>/dev/null || true")
            if out.strip():
                result["distro"] = parse_os_release(out)
            else:
                # Fallback: lsb_release -a
                out2, err2, rc2 = rx.run("lsb_release -a 2>/dev/null || true")
                if out2.strip():
                    # Heuristic parse
                    name = None
                    version = None
                    for line in out2.splitlines():
                        if ":" in line:
                            k, v = [s.strip() for s in line.split(":", 1)]
                            if k.lower() == "distributor id":
                                name = v
                            elif k.lower() == "release":
                                version = v
                    result["distro"] = {
                        "id": name.lower() if name else None,
                        "version_id": version,
                        "name": name,
                        "pretty_name": f"{name} {version}"
                        if name and version
                        else None,
                    }
                else:
                    result["notes"].append(
                        "Neither /etc/os-release nor lsb_release available"
                    )

            # 2) Kernel + arch
            out, _, _ = rx.run("uname -r")
            result.setdefault("platform", {})["kernel_release"] = out.strip() or None
            out, _, _ = rx.run("uname -m")
            result["platform"]["machine"] = out.strip() or None

            # 3) Init process
            out, _, _ = rx.run("ps -p 1 -o comm= 2>/dev/null || true")
            result["platform"]["init"] = out.strip() or None

            # 4) Package manager detection
            check_pm = "command -v apt dnf yum zypper pacman apk 2>/dev/null || true"
            out, _, _ = rx.run(check_pm)
            result["platform"]["pkg_manager"] = detect_pkg_manager(out)

            # 5) User and host basics
            out, _, _ = rx.run("whoami")
            result["user"]["username"] = out.strip() or None
            out, _, _ = rx.run("echo $SHELL")
            result["user"]["shell"] = out.strip() or None
            out, _, _ = rx.run("hostname")
            result.setdefault("network", {})["hostname"] = out.strip() or None
            out, _, _ = rx.run("hostname -f 2>/dev/null || hostname")
            result["network"]["fqdn"] = out.strip() or None
            out, _, _ = rx.run(
                "ip -o -4 addr show up scope global 2>/dev/null | awk -v COLON=':' '{print $2 COLON $4}' || true"
            )
            addrs = [line.strip() for line in out.splitlines() if line.strip()]
            result["network"]["addresses"] = addrs

            result["status"] = "ok"

            return result
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
