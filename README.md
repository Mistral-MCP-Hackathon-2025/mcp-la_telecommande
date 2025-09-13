<div align="center">

# SSH MCP Server

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![FastMCP](https://img.shields.io/badge/Framework-FastMCP-8A2BE2)](https://github.com/fastmcp/fastmcp)
[![Paramiko](https://img.shields.io/badge/SSH-Paramiko-2E8B57)](https://www.paramiko.org/)
[![Lint](https://img.shields.io/badge/Lint-Ruff-46A9E1)](https://github.com/astral-sh/ruff)
[![Lockfile](https://img.shields.io/badge/Deps-uv.lock-000000)](uv.lock)

<br/>

🚀 Built during the Mistral AI MCP Server Hackathon

<br/>

## Authors
[Lucas Duport](https://www.linkedin.com/in/lucas-duport/) • [Armand Blin](https://www.linkedin.com/in/armandblin/) • [Arthur Courselle](https://www.linkedin.com/in/arthur-courselle/) • [Samy Yacef](https://www.linkedin.com/in/samy-yacef-b88543146/) • [Flavien Goeffray](https://www.linkedin.com/in/flavien-geoffray/)

</div>

This project is an SSH-powered Model Context Protocol (MCP) server. It exposes safe, composable tools to list authorized VMs, probe reachability, inspect distro/platform details, and execute commands over SSH — all permissioned via simple API keys defined in YAML.

The goal is to make remote ops dead-simple for MCP clients while keeping access control transparent and configuration-first.

---

## Highlights
- SSH over Paramiko with typed results
- YAML-first config: VMs, users, groups
- Opt-in permission model (off by default if no users/groups)
- Clean FastMCP bootstrap with HTTP and stdio transports
- Strong, friendly error messages: “API key invalid or VM not permitted”

## Quick start

Prereqs
- Python 3.13+
- macOS/Linux with zsh/bash

1) Create a virtual env and install deps (via uv)

```bash
curl -sSL https://astral.sh/uv/install.sh | sh
uv venv
source .venv/bin/activate
uv pip install -r pyproject.toml
```

2) Configure VMs

- Copy `config_examples.yaml` to `config.yaml` and edit hosts/keys/users.
- Set the `CONFIG` environment variable to point to your YAML file if not using the default path.

3) Run

```bash
source .venv/bin/activate
fastmcp dev main.py
```

By default `fastmcp dev` uses stdio transport. Running `python main.py` (or `fastmcp run`) will use the streamable HTTP transport configured in `main.py`.

### Optional: HTTP transport

```bash
MCP_TRANSPORT=http MCP_HOST=127.0.0.1 MCP_PORT=8000 fastmcp dev main.py
```

Then hit the server with your client or with curl (path will depend on your MCP client).

## Configuration

Put your config in YAML. Minimum: a list of VMs. Optionally add groups and users to enable permissions.

Example (see `config_examples.yaml`):

```yaml
vms:
  - name: vm1
    host: 192.168.1.10
    user: ubuntu
    port: 22
    key: |
      -----BEGIN OPENSSH PRIVATE KEY-----
      ...
      -----END OPENSSH PRIVATE KEY-----

groups:
  - name: dev
    vms: [vm1]

users:
  - name: alice
    api_key: "alice-secret"
    groups: [dev]
```

Notes
- If `users` or `groups` are omitted entirely, permissions are disabled and all VMs are accessible.
- Keys are stored in plaintext per hackathon requirements; do not commit real secrets.

Environment
- `CONFIG`: absolute or relative path to your YAML file (defaults to `./config.yaml`).

## Authentication & permissions

When permissions are enabled (presence of `users` list):
- Clients must send an Authorization header. Supported formats:
  - `Authorization: Bearer <API_KEY>`
  - `Authorization: <API_KEY>` (raw value)
- Authorization determines which VMs you see and can access.
- Errors intentionally use a single message for clarity: `API key invalid or VM not permitted`.

When permissions are disabled (no `users` key):
- All VMs are visible and callable without any Authorization header.

## MCP tools

All tools are defined in `src/SSH/tools.py` and registered by `src/server.py`.

1) ssh_list_vms
- Purpose: List VM names the caller can access.
- Params: none
- Returns: `{ vms: string[] }`
- Errors: `ValueError` when permissions are enabled and the API key is missing/invalid.

2) ssh_is_vm_up
- Purpose: Quick TCP probe to the VM’s SSH port with rough latency.
- Params: `vm_name: string`
- Returns: `{ vm, host, port, reachable, latency_ms, reason }`
- Errors: `ValueError` on authorization failure when permissions are enabled.

3) ssh_vm_distro_info
- Purpose: Read-only diagnostics: distro, kernel, init, pkg manager, host/user basics.
- Params: `vm_name: string`
- Returns: `{ vm, host, port, status, distro, platform, network, user, notes[] }`
- Errors: `ValueError` on authorization failure or SSH errors.

4) ssh_run_command
- Purpose: Execute a shell command on a permitted VM (bash -lc).
- Params: `command: string`, `vm_name: string`
- Returns: `{ command, status: 'executed', stdout, stderr, return_code }`
- Errors: `ValueError` on authorization failure, SSH/auth issues, or non-zero exit (includes stderr).

Usage flow (recommended)
- Call `ssh_list_vms` first to discover allowed VMs.
- Optionally call `ssh_is_vm_up` to preflight connectivity.
- Use `ssh_vm_distro_info` for diagnostics.
- Use `ssh_run_command` for actual remote execution.

## Examples

Reachability
```
tool: ssh_is_vm_up
args: { "vm_name": "vm1" }
→ { vm, host, port, reachable, latency_ms, reason }
```

Distro & platform info
```
tool: ssh_vm_distro_info
args: { "vm_name": "vm1" }
→ { vm, host, port, status, distro, platform, network, user, notes }
```

Run a command
```
tool: ssh_run_command
args: { "vm_name": "vm1", "command": "uname -a" }
→ { command, status: 'executed', stdout, stderr, return_code }
```

## Development
- Lint/format: Ruff (configured in `pyproject.toml`).
- Tracing: Weave initialized as `mcp-ssh`.
- Entry points: `main.py` (HTTP by default), `src/server.py` (FastMCP instance, tool registration).

## Troubleshooting
- fastmcp not found: activate your venv; ensure FastMCP installed.
- Python version errors: this repo targets Python 3.13.
- Permission errors: ensure you send the right Authorization header and that your API key belongs to a user with groups that include the VM.
- SSH errors: verify host, user, port, and key material for the VM in your YAML.

## Acknowledgements
Created during the Mistral AI MCP Server Hackathon 2025. Thanks to the organizers, mentors, partners, and the open-source community around FastMCP, Paramiko, and Weave.
