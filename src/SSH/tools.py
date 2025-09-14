"""MCP tools that expose SSH actions.

This module registers MCP tools for listing accessible VMs and running commands
remotely via the `RemoteExecutor`. Return values are strongly typed for
predictability. All tools document authorization expectations and error modes
to avoid misuse by MCP clients.

Tools provided:
- `ssh_list_vms()`: Return only the VM names the caller may access.
- `ssh_run_command(command, vm_name)`: Run a command on a permitted VM.
- `ssh_is_vm_up(vm_name)`: Quick reachability check (TCP connect to SSH).
- `ssh_vm_distro_info(vm_name)`: Collect distro/platform debug info.
"""

# ruff: noqa: I001
from typing import Annotated, TypedDict
import socket
import time
import re

import paramiko
import weave
import uuid

from src.qdrant.log_manager import log_ssh_operation
from src.server import mcp, config_manager
from src.config import VMCredentials
from src.config.permissions import permissions_enabled

from .remote_executor import RemoteExecutor
from mcp.server.fastmcp import Context


def mask_value(value: str | None) -> str:
    """Mask a value for logging by replacing every other character with "*".

    Args:
        value: A string to mask, or None.

    Returns:
        A masked representation; empty string if value is falsy.
    """
    if not value:
        return ""
    return "".join("*" if i % 2 else c for i, c in enumerate(value))


def _extract_api_key_from_headers(ctx: Context) -> str | None:
    """Retrieve API key from the Authorization header in request context.

    Accepts either `Authorization: Bearer <API_KEY>` or a raw value.
    Returns the extracted API key string or None if not found.
    """
    # Best-effort: headers may be on request_context.request.headers in HTTP mode
    hdrs = None
    try:
        req = getattr(ctx.request_context, "request", None)
        if req is not None:
            hdrs = getattr(req, "headers", None)
        if hdrs is None:
            hdrs = getattr(ctx.request_context, "headers", None)
        if hdrs is None:
            meta = getattr(ctx.request_context, "meta", None)
            if isinstance(meta, dict):
                hdrs = meta.get("headers")
    except Exception:
        hdrs = None

    auth = None
    if hdrs:
        # support dict-like headers
        auth = hdrs.get("Authorization") or hdrs.get("authorization")
    if not auth:
        return None
    auth = str(auth).strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return auth or None


class BaseResult(TypedDict):
    """Base shape for SSH tool results."""

    status: str
    stdout: str
    stderr: str
    return_code: int


class RunCommandResult(BaseResult):
    """Result shape for the `run_command` tool."""

    command: str


class ListVMsResult(TypedDict):
    """Shape for VM listing results.

    Attributes:
        vms: The list of VM names the caller can access.
    """
    vms: list[str]


# -----------------------
# Helper utilities (local)
# -----------------------


def _tcp_reachable(
    host: str, port: int, timeout: float = 3.0
) -> tuple[bool, float | None, str | None]:
    """Attempt a TCP connection and measure latency.

    Returns:
        (reachable, latency_ms, reason)
    """
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            elapsed_ms = (time.monotonic() - start) * 1000.0
            return True, round(elapsed_ms, 2), None
    except Exception as e:
        return False, None, str(e)


def _parse_os_release(text: str) -> dict[str, str | None]:
    """Parse /etc/os-release content into a small dict.

    Extract common fields and strip optional quotes.
    """
    fields = {k: None for k in ("ID", "VERSION_ID", "NAME", "PRETTY_NAME")}
    line_re = re.compile(r"^([A-Z_]+)=(.*)$")
    for line in text.splitlines():
        m = line_re.match(line.strip())
        if not m:
            continue
        k, v = m.group(1), m.group(2)
        if k not in fields:
            continue
        # Remove optional surrounding quotes
        if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
            v = v[1:-1]
        fields[k] = v
    return {
        "id": fields["ID"],
        "version_id": fields["VERSION_ID"],
        "name": fields["NAME"],
        "pretty_name": fields["PRETTY_NAME"],
    }


def _detect_pkg_manager(out_which: str) -> str | None:
    """Given a combined output of several `command -v` checks, infer a package manager."""
    for mgr in ("apt", "dnf", "yum", "zypper", "pacman", "apk"):
        if re.search(rf"\b{mgr}\b", out_which):
            return mgr
    return None


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
        api_key = _extract_api_key_from_headers(ctx)
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
        api_key = _extract_api_key_from_headers(ctx)
        if not api_key:
            raise ValueError("API key invalid or VM not permitted")
        config_manager.ensure_can_access(api_key, vm_name)

    creds: VMCredentials = config_manager.get_vm_creds(vm_name=vm_name)
    job_id = str(uuid.uuid4())
    try:
        with RemoteExecutor(
            creds.host, creds.user, port=creds.port, key=creds.key
        ) as rx:
            stdout, stderr, rc = rx.run(command)

            if rc != 0:
                raise ValueError(f"Error running command: {stderr}")

            log_ssh_operation(
                job_id=job_id,
                host=creds.host,
                user=creds.user,
                command=command,
                result={"stdout": stdout, "stderr": stderr, "return_code": rc},
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
            host=creds.host,
            user=creds.user,
            command=command,
            result={
                "stdout": stdout,
                "stderr": f"Authentication failed: {stderr}",
                "return_code": rc,
            },
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
            host=creds.host,
            user=creds.user,
            command=command,
            result={
                "stdout": "",
                "stderr": f"SSH connection failed: {e}",
                "return_code": rc,
            },
        )
        raise ValueError(f"SSH connection failed: {e}")
    except Exception as e:
        print(
            f"Unexpected error during SSH operation: {e}. Debug: HOST={mask_value(creds.host)}, USERNAME={mask_value(creds.user)}, PORT={creds.port}, KEY_FILENAME={mask_value(creds.key)}"
        )
        log_ssh_operation(
            job_id=job_id,
            host=creds.host,
            user=creds.user,
            command=command,
            result={"stdout": "", "stderr": str(e), "return_code": rc},
        )
        raise ValueError(f"Unexpected error during SSH operation: {e}")


# ---------------------------------
# New tool: quick VM reachability
# ---------------------------------


class VMUpResult(TypedDict):
    vm: str
    host: str
    port: int
    reachable: bool
    latency_ms: float | None
    reason: str | None


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
        api_key = _extract_api_key_from_headers(ctx)
        if not api_key:
            raise ValueError("API key invalid or VM not permitted")
        config_manager.ensure_can_access(api_key, vm_name)
    creds: VMCredentials = config_manager.get_vm_creds(vm_name=vm_name)
    reachable, latency_ms, reason = _tcp_reachable(creds.host, creds.port)
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


class DistroInfo(TypedDict, total=False):
    id: str | None
    version_id: str | None
    name: str | None
    pretty_name: str | None


class PlatformInfo(TypedDict, total=False):
    kernel_release: str | None
    machine: str | None
    init: str | None
    pkg_manager: str | None


class NetworkInfo(TypedDict, total=False):
    hostname: str | None
    fqdn: str | None
    addresses: list[str]


class VMInfoResult(TypedDict, total=False):
    vm: str
    host: str
    port: int
    status: str
    distro: DistroInfo
    platform: PlatformInfo
    network: NetworkInfo
    user: dict[str, str | None]
    notes: list[str]


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
        api_key = _extract_api_key_from_headers(ctx)
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
                result["distro"] = _parse_os_release(out)
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
            result["platform"]["pkg_manager"] = _detect_pkg_manager(out)

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
