## SSH MCP — Developer README

This repository is a minimal example MCP (Model Context Protocol) application using the `fastmcp` stack. The instructions below show how to set up a local development environment (recommended: Python 3.13), install dependencies using `uv`, enable linting with `ruff`, and run the app in development / debug mode with `fastmcp`.

## Checklist (what this document covers)
- Install and use `uv` (recommended package runner used in this repo)
- Create and activate a virtual environment (venv)
- Install project dependencies
- Use `ruff` for linting (CLI + VS Code extension notes)
- Run the app in development/debug mode with `fastmcp dev main.py` and how to switch transports

## Requirements
- Python >= 3.13 (project `pyproject.toml` targets py313)
- A POSIX-compatible shell (examples use bash/zsh on macOS and Linux)

## Quick start (recommended)

1) Install uv
```bash
curl -sSL https://astral.sh/uv/install.sh | sh
```

After installing `uv` make sure it's available on your PATH (reopen the shell if needed).

2) Install project dependencies (inside the venv)

The project includes `pyproject.toml` and a `uv.lock` file. Using `uv` we can install the dependencies into the active environment. From the repo root (after activating `.venv`):

```bash
# upgrade pip/setuptools/wheel first
uv pip install --upgrade pip setuptools wheel

# then install the project dependencies listed in pyproject.toml
uv pip install -r pyproject.toml
```

Notes:
- The Dockerfile in this repo installs dependencies with `uv pip install --system --upgrade pip setuptools wheel -r pyproject.toml`. In a local venv you should omit `--system`.
- If you prefer not to use `uv`, installing directly with pip will also work after you export requirements or run `pip install .` if you make the project installable. The recommended approach here is to use `uv` so the `uv.lock` constraints are respected.

## Run the app in development / debug mode

This project uses `fastmcp` for the MCP runtime. The entry point is `main.py` at the repository root.

- Start in the default (stdio) transport:

```bash
# with the venv activated
fastmcp dev main.py
```

By default `main.py` reads `MCP_TRANSPORT` (defaults to `stdio`) and will run the MCP in stdio mode, which is useful for local tooling and embedding.

- Run the app as an HTTP server (useful for testing with curl or browser-based tooling):

```bash
MCP_TRANSPORT=http MCP_HOST=127.0.0.1 MCP_PORT=8000 fastmcp dev main.py
```

When using `http` transport the app will bind to `MCP_HOST:MCP_PORT` (the defaults are `127.0.0.1:8000`), and you can interact with the service over HTTP. `main.py` contains this logic:

- If `MCP_TRANSPORT` == `http` -> `mcp.run(transport="http", host=host, port=port)`
- If `MCP_TRANSPORT` == `stdio` -> `mcp.run(transport="stdio")`

Example: test HTTP endpoint with curl (replace path as appropriate for your MCP implementation):

```bash
curl -v http://127.0.0.1:8000/
```

If `fastmcp` is not on your PATH, make sure your venv is activated; the `fastmcp` CLI is provided by the `fastmcp` package installed in the environment.

## SSH tools (remote exec) 🔐

This project includes optional SSH-based tools under `src/ssh/`:
- `ssh_create_file` — create a file on a remote host using `touch`.
- `ssh_run_command` — run an arbitrary shell command remotely and return stdout/stderr/rc.

Configure environment variables (create a `.env` from `.env.example` or set them in your shell):

```
HOST=<remote host>
USER=<ssh username>
KEY_FILENAME=<path to private key>  # optional if using agent/known keys
PORT=22                             # optional (defaults to 22)
```

When the server starts, these tools are auto-registered via imports in `src/sample/server.py`.

## Debugging notes
- Use `fastmcp dev` for local development — it enables the developer-friendly runtime and reload behaviour provided by `fastmcp`.
- Switch transports with the `MCP_TRANSPORT` env var. `stdio` is often used by editor integrations and local harnesses; `http` exposes a network endpoint.
- Common env vars used by `main.py`:
  - `MCP_TRANSPORT` (stdio | http) — default: `stdio`
  - `MCP_HOST` — default: `127.0.0.1` (only used by `http` transport)
  - `MCP_PORT` — default: `8000` (only used by `http` transport)

## Docker

This repository includes a `Dockerfile` which installs `uv` and uses it to install pinned dependencies from `pyproject.toml` / `uv.lock`. The Dockerfile installs with `uv pip install --system --upgrade pip setuptools wheel -r pyproject.toml` inside the image to produce a small, reproducible container.

## Troubleshooting
- If `fastmcp` or `uv` commands are not found, ensure your venv is activated and that the tools are installed into the active environment.
- If you see Python version errors, confirm you are running Python 3.13 as required by `pyproject.toml`.
- If `ruff` reports many issues, run `ruff check src/ --fix` and commit the changes.

## Where to look in this repo
- Entry point: `main.py` — shows how the MCP server is started and how `MCP_TRANSPORT`, `MCP_HOST`, and `MCP_PORT` are used.
- Dependencies and linting config: `pyproject.toml` and `uv.lock`.

## Quick summary
- Create a venv, activate it, install `uv`, then run `uv pip install -r pyproject.toml` to install deps. Use `fastmcp dev main.py` to run locally. Use `ruff check` (or the VS Code Ruff extension) for linting and auto-fixing.

Thanks for checking out this sample MCP project.