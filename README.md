<div align="center">

<img src="docs/logo.png" alt="La Télécommande Logo" width="200" />

# La Télécommande

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![FastMCP](https://img.shields.io/badge/Framework-FastMCP-8A2BE2)](https://github.com/fastmcp/fastmcp)
[![Vector search](https://img.shields.io/badge/Vector-Qdrant-8A2BE2?logo=qdrant&logoColor=white)](https://qdrant.tech)
[![Embeddings](https://img.shields.io/badge/Embeddings-Mistral%20Embed-FFB703?logo=mistral&logoColor=white)](https://docs.mistral.ai)
[![Tracing: Weave by W&B](https://img.shields.io/badge/Tracing-Weave%20by%20W%26B-FFBE0B?logo=weightsandbiases&logoColor=000)](https://wandb.ai/site)
[![Deploy on ALPIC.ai](https://img.shields.io/badge/Deploy-ALPIC.ai-ff69b4?logo=alpic&logoColor=white)](https://alpic.ai/deploy?repo=https://github.com/Mistral-MCP-Hackathon-2025/mcp-ssh)
[![Paramiko](https://img.shields.io/badge/SSH-Paramiko-2E8B57)](https://www.paramiko.org/)
[![Lint](https://img.shields.io/badge/Lint-Ruff-46A9E1)](https://github.com/astral-sh/ruff)
[![Lockfile](https://img.shields.io/badge/Deps-uv.lock-000000)](uv.lock)

<br/>

🚀 Built during the Mistral AI MCP Server Hackathon

<br/>

## Authors

[Lucas Duport](https://www.linkedin.com/in/lucas-duport/) • [Armand Blin](https://www.linkedin.com/in/armandblin/) • [Arthur Courselle](https://www.linkedin.com/in/arthur-courselle/) • [Samy Yacef](https://www.linkedin.com/in/samy-yacef-b88543146/) • [Flavien Goeffray](https://www.linkedin.com/in/flavien-geoffray/)

</div>

## What is La Télécommande?

**La Télécommande** (French for "The Remote") transforms Mistral into a true DevOps co-pilot, solving one of the most persistent challenges in modern infrastructure management: **the complexity barrier between human intent and machine execution**.

### The Problem We Solve

Whether you're a DevOps engineer managing hundreds of VMs or an occasional developer who dreads command lines, infrastructure management has always been the same story: tedious, error-prone, and time-consuming. You know what you want to achieve, but getting there means remembering countless commands, dealing with different OS distributions, managing SSH keys, and worst of all — doing everything sequentially, one machine at a time.

**What if you could simply describe what you want in natural language and have it executed instantly across your entire infrastructure?**

### Our Solution

La Télécommande is an SSH-powered Model Context Protocol (MCP) server that bridges the gap between natural language and infrastructure operations. It transforms Le Chat into an actual operator for your infrastructure, enabling you to:

- **Configure servers** with simple prompts
- **Install packages** on any distribution or OS (yes, even Arch Linux!)
- **Get monitoring insights** and surface logs instantly
- **Orchestrate deployments** across multiple machines simultaneously
- **Execute commands in parallel** — deploy to your entire fleet in seconds, not hours

### Key Innovation: Natural Language → Infrastructure Action

The principle is beautifully simple:

1. **Set up machine access** through our MCP Server configuration
2. **Describe your intent** to Le Chat in natural language
3. **Le Chat understands** and uses our MCP tools to execute actions
4. **Commands run in parallel** across your infrastructure automatically

### Built for Everyone

This isn't just for hardcore DevOps professionals. Thanks to our natural language interface, both seasoned infrastructure engineers and developers who prefer to avoid command lines can manage infrastructure with the same ease — just by asking questions and describing what they want to accomplish.

La Télécommande makes remote operations dead-simple for MCP clients while keeping access control transparent and configuration-first, ensuring your infrastructure remains secure and manageable at scale.

---

## Highlights

- SSH over Paramiko with typed results
- YAML-first config: VMs, users, groups
- Opt-in permission model (off by default if no users/groups)
- Clean FastMCP bootstrap with HTTP and stdio transports
- Strong, friendly error messages: “API key invalid or VM not permitted”
- Tracing and observability with Weave (by Weights & Biases)
- Semantic log search & insights powered by Qdrant + Mistral embeddings

## Quick start

Prereqs

- Python 3.13+
- macOS/Linux with zsh/bash

1. Create a virtual env and install deps (via uv)

```bash
curl -sSL https://astral.sh/uv/install.sh | sh
uv venv
source .venv/bin/activate
uv pip install -r pyproject.toml
```

2. Configure VMs

- Copy `config_examples.yaml` to `config.yaml` and edit hosts/keys/users.
- Set the `CONFIG` environment variable to point to your YAML file if not using the default path.

3. Run

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

- `CONFIG` (optional): absolute or relative path to your YAML file. If set, it will be used directly and the auto-fetch behavior is skipped.
- `CONFIG_FILENAME`: the filename to look for at the project root (default `config.yaml`).
- `VERSION`: version segment appended to the fetch URL.
- `URL`: base URL to fetch the config from.
- `API_KEY`: API key sent as `X-API-Key` header when fetching.
- `WANDB_API_KEY`: API key for Weights & Biases; used to authenticate Weave tracing.

Startup behavior

- On server start, if `CONFIG` is not set, the server expects a file named `<CONFIG_FILENAME>` at the project root.
- If that file does not exist, the server will fetch it from `${URL}/${VERSION}/${CONFIG_FILENAME}` with the header `X-API-Key: ${API_KEY}` and save it locally before continuing startup.
- If any of `URL`, `VERSION`, or `API_KEY` are missing when a fetch is required, startup will fail with a helpful error message.

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

1. ssh_list_vms

- Purpose: List VM names the caller can access.
- Params: none
- Returns: `{ vms: string[] }`
- Errors: `ValueError` when permissions are enabled and the API key is missing/invalid.

2. ssh_is_vm_up

- Purpose: Quick TCP probe to the VM’s SSH port with rough latency.
- Params: `vm_name: string`
- Returns: `{ vm, host, port, reachable, latency_ms, reason }`
- Errors: `ValueError` on authorization failure when permissions are enabled.

3. ssh_vm_distro_info

- Purpose: Read-only diagnostics: distro, kernel, init, pkg manager, host/user basics.
- Params: `vm_name: string`
- Returns: `{ vm, host, port, status, distro, platform, network, user, notes[] }`
- Errors: `ValueError` on authorization failure or SSH errors.

4. ssh_run_command

- Purpose: Execute a shell command on a permitted VM (bash -lc).
- Params: `command: string`, `vm_name: string`
- Returns: `{ command, status: 'executed', stdout, stderr, return_code }`
- Errors: `ValueError` on authorization failure, SSH/auth issues, or non-zero exit (includes stderr).

5. ssh_search_logs

- Purpose: Semantic search across SSH history (commands, stdout, stderr).
- Args:
  - `query` (string, required): natural language (e.g. "oom killer", "failed scp to backup").
  - `collection` (string, optional): one of `commands` | `stdout` | `stderr` (default: `commands`).
  - `host_filter` (string|null, optional): only from this host.
  - `user_filter` (string|null, optional): only from this user.
  - `time_hours` (int|null, optional): restrict to last N hours.
  - `limit` (int, optional): max results (default: 10).
- Returns: `{ query, total_found, results[] }` where each result contains:
  - `relevance_score` (float), `host` (string), `command` (string), `job_id` (string), `timestamp` (float), `formatted_time` (string), `stdout` (string), `stderr` (string), `return_code` (int|null)
- Example:
  - Find recent OOM errors: `{ "query": "oom killer", "collection": "stderr", "time_hours": 6 }`

6. ssh_get_statistics

- Purpose: Aggregate usage stats over SSH command history.
- Args:
  - `time_hours` (int, optional): lookback window (default: 24)
  - `user_filter` (string|null, optional): limit to one user
  - `host_filter` (string|null, optional): limit to one host
- Returns: `{ time_period_hours, commands_executed, successful_commands, failed_commands, most_used_hosts, most_common_commands, recent_errors[] }`
  - `recent_errors[]` elements: `{ host, command, error, timestamp }`
- Notes: success/failed based on `return_code == 0`.

7. ssh_suggest_commands

- Purpose: Suggest commands from prior successful executions using semantic similarity.
- Args:
  - `context` (string, required): natural language goal, e.g. "check disk space"
  - `host` (string|null, optional): bias to a specific host
  - `limit` (int, optional): number of suggestions (default: 5)
- Returns: `{ context, host, total_suggestions, suggestions[] }`
  - Suggestions have: `{ command, relevance_score, host, last_used, success_rate }`
- Notes: only sourced from history where `return_code == 0`; duplicates removed by command.

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
- Tracing: Weave (by Weights & Biases) initialized as `la-telecommande`.
- Entry points: `main.py` (HTTP by default), `src/server.py` (FastMCP instance, tool registration).

### Module layout

- `src/SSH/tools.py`: Public MCP tools for SSH. Thin orchestration layer only.
- `src/SSH/remote_executor.py`: Paramiko-based SSH client wrapper.
- `src/SSH/utils/`:
  - `auth.py`: Authorization header parsing helpers.
  - `masking.py`: Safe masking for logging (avoid secret leakage).
  - `network.py`: TCP reachability and latency check utilities.
  - `osinfo.py`: Distro parsing and package manager detection.
  - `types.py`: Shared TypedDict result contracts for tools.

Config and permissions

- `src/config/manager.py`: Loads YAML, indexes VMs, exposes helpers.
- `src/config/permissions.py`: Optional users/groups model and checks.
- `src/config/credentials.py`: Typed VM credential container.

## Semantic log search (Qdrant + Mistral)

La Télécommande can log each SSH operation and index it for semantic search and analytics.

How it works

- `src/qdrant/log_manager.py` embeds command/stdout/stderr with Mistral Embed and upserts into Qdrant.
- Collections are auto-created (if missing) on first use, along with payload indexes used for filters.
- Tools in `src/qdrant/tools.py` query Qdrant to power search, stats, and suggestions.

Collections & payload schema

- `ssh_commands` (vector size 1024, cosine)
  - payload: `job_id` (str), `host` (str), `user` (str), `command` (str), `timestamp` (float), `return_code` (int)
- `ssh_stdout` (vector size 1024, cosine)
  - payload: same base fields + `stdout` (str)
- `ssh_stderr` (vector size 1024, cosine)
  - payload: same base fields + `stderr` (str)

Environment variables

- `QDRANT_URL`: e.g. `http://localhost:6333` or hosted endpoint
- `QDRANT_API_KEY`: if your Qdrant instance requires auth
- `MISTRAL_API_KEY`: for embeddings

Enable logging

- Logging is invoked by the SSH executor via `log_ssh_operation(job_id, host, user, command, result)`.
- If you only run the core SSH tools and never call the logger, Qdrant collections will stay empty.

Query examples

- Search last 12h of failed commands: `ssh_search_logs { query: "failed", collection: "commands", time_hours: 12 }`
- Get usage stats for a host: `ssh_get_statistics { host_filter: "vm1", time_hours: 72 }`
- Suggest common disk checks: `ssh_suggest_commands { context: "check disk space" }`

Troubleshooting

- Missing packages: ensure `mistralai` and `qdrant-client` are installed (see `pyproject.toml`).
- Empty results: verify the SSH executor is calling `log_ssh_operation` and that env vars point to your Qdrant.
- Embedding limits: stdout/stderr are truncated to ~30k characters to fit model limits.

## Troubleshooting

- fastmcp not found: activate your venv; ensure FastMCP installed.
- Python version errors: La Télécommande targets Python 3.13.
- Permission errors: ensure you send the right Authorization header and that your API key belongs to a user with groups that include the VM.
- SSH errors: verify host, user, port, and key material for the VM in your YAML.

## Acknowledgements

Created during the Mistral AI MCP Server Hackathon 2025. Thanks to the organizers, mentors, partners, and the open-source community around FastMCP, Paramiko, and Weave.
