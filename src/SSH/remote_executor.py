"""Paramiko-based SSH utilities for remote command execution.

This module provides a small `RemoteExecutor` class that can open an SSH
connection, execute commands, and upload+run local scripts on a remote host.
It aims to be minimal, typed, and safe by default.
"""

from __future__ import annotations

import io
import os
import shlex
from types import TracebackType

import paramiko


class RemoteExecutor:
    """
    Minimal SSH wrapper that can run commands or upload+run scripts on a remote host.

    Usage:
        # Using a key file:
        with RemoteExecutor("server.example.com", "alice", key_filename="~/.ssh/id_rsa") as rx:
            out, err, rc = rx.run("echo hello && uname -a")
            print(out, err, rc)

        # Using key content directly:
        with RemoteExecutor("server.example.com", "alice", key_content=KEY) as rx:
            out, err, rc = rx.run("echo hello && uname -a")
            print(out, err, rc)

            out, err, rc = rx.run_script("deploy.sh")  # uploads to /tmp/deploy.sh and executes
            print(out, err, rc)
    """

    def __init__(
        self,
        hostname: str,
        username: str,
        *,
        port: int = 22,
        password: str | None = None,
        key: str | None = None,
        timeout: float | None = 15.0,
        look_for_keys: bool = True,
        allow_agent: bool = True,
        known_hosts_policy: paramiko.MissingHostKeyPolicy = paramiko.AutoAddPolicy(),
    ):
        """Create a new `RemoteExecutor`.

        Args:
            hostname: Target host (DNS or IP).
            username: SSH username.
            port: SSH port, default 22.
            password: Password to authenticate, if any.
            key: Private key material as a string (OpenSSH or PEM). If None,
                agent/known keys may be used depending on `look_for_keys` and
                `allow_agent`.
            timeout: Socket timeout in seconds, or None for library default.
            look_for_keys: Whether to search for keys in typical locations.
            allow_agent: Whether to allow using the SSH agent.
            known_hosts_policy: Policy for unknown host keys (defaults to auto-add).
        """
        self.hostname = hostname
        self.username = username
        self.port = port
        self.password = password
        self.key = key
        self.timeout = timeout
        self.look_for_keys = look_for_keys
        self.allow_agent = allow_agent

        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(known_hosts_policy)
        self._connected = False
        self._pkey: paramiko.PKey | None = None

    def __enter__(self) -> "RemoteExecutor":
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def connect(self) -> None:
        """Open the SSH connection if not already connected.

        Raises:
            ValueError: On authentication failure or connection errors.
        """
        if self._connected:
            return

        # Prepare the private key if key_content is provided
        pkey = None
        if self.key:
            try:
                pkey = self._parse_private_key(self.key)
            except Exception as e:
                raise ValueError(f"Failed to parse private key: {e}")

        try:
            self._client.connect(
                hostname=self.hostname,
                port=self.port,
                username=self.username,
                password=self.password,
                pkey=pkey,
                timeout=self.timeout,
                look_for_keys=self.look_for_keys,
                allow_agent=self.allow_agent,
            )
            self._connected = True
        except paramiko.AuthenticationException as e:
            raise ValueError(
                f"SSH Authentication failed for {self.username}@{self.hostname}: {e}"
            )
        except Exception as e:
            raise ValueError(
                f"SSH Connection failed to {self.hostname}:{self.port}: {e}"
            )

    def close(self) -> None:
        """Close the SSH connection if it is open."""
        if self._connected:
            self._client.close()
            self._connected = False

    def _parse_private_key(self, key_content: str) -> paramiko.PKey:
        """
        Parse a private key from string content.
        Attempts to detect and parse RSA, DSS, ECDSA, or Ed25519 keys.
        """
        key_content = key_content.strip()

        if "BEGIN OPENSSH PRIVATE KEY" in key_content and "\n" not in key_content:

            begin_marker = "-----BEGIN OPENSSH PRIVATE KEY-----"
            end_marker = "-----END OPENSSH PRIVATE KEY-----"

            if begin_marker in key_content and end_marker in key_content:
                start_idx = key_content.find(begin_marker) + len(begin_marker)
                end_idx = key_content.find(end_marker)

                base64_content = key_content[start_idx:end_idx].strip().replace(" ", "")

                base64_lines = [
                    base64_content[i : i + 64]
                    for i in range(0, len(base64_content), 64)
                ]
                key_content = (
                    begin_marker + "\n" + "\n".join(base64_lines) + "\n" + end_marker
                )

        if "BEGIN OPENSSH PRIVATE KEY" in key_content:
            key_file = io.StringIO(key_content)
            try:
                if hasattr(paramiko, "Ed25519Key"):
                    return paramiko.Ed25519Key.from_private_key(key_file)
            except Exception as e:
                # Do not abort immediately; some OpenSSH keys may be RSA/ECDSA.
                # We'll try RSA next; if that fails, we re-raise a clearer error.
                ed25519_err = e
            else:
                ed25519_err = None

        key_file = io.StringIO(key_content)
        try:
            if hasattr(paramiko, "RSAKey"):
                return paramiko.RSAKey.from_private_key(key_file)
        except Exception as e:
            # Prefer the RSA error message if Ed25519 also failed; otherwise report Ed25519.
            if 'ed25519_err' in locals() and ed25519_err is not None:
                raise ValueError(
                    f"Failed to parse OpenSSH private key as Ed25519 ({ed25519_err}) or RSA ({e})."
                )
            raise ValueError(f"Failed to parse PEM private key as RSA: {e}")

        # If no parser matched, raise a generic error.
        raise ValueError("Unsupported or unrecognized private key format.")

    def run(
        self,
        command: str,
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
        get_pty: bool = False,
    ) -> tuple[str, str, int]:
        """
        Execute a shell command on the remote host.

        Returns:
            (stdout, stderr, returncode)
        """
        self.connect()

        prepared_cmd = self._prepare_command(command, cwd=cwd, env=env)

        stdin, stdout, stderr = self._client.exec_command(
            prepared_cmd, timeout=timeout, get_pty=get_pty
        )
        # Ensure we don't hold STDIN open on the remote process
        try:
            stdin.close()
        except Exception:
            pass

        exit_status = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        return out, err, exit_status

    def run_script(
        self,
        local_path: str,
        *,
        remote_path: str | None = None,
        interpreter: str = "/bin/bash",
        timeout: float | None = None,
        env: dict[str, str] | None = None,
        get_pty: bool = False,
    ) -> tuple[str, str, int]:
        """
        Upload a local shell script to the remote machine and execute it.

        Args:
            local_path: Path to the local script file.
            remote_path: Where to place it on the remote (defaults to /tmp/<basename>).
            interpreter: Interpreter to use (e.g., /bin/bash, /usr/bin/env bash).
        Returns:
            (stdout, stderr, returncode)
        """
        self.connect()

        if remote_path is None:
            remote_path = f"/tmp/{os.path.basename(local_path)}"

        sftp = self._client.open_sftp()
        try:
            sftp.put(local_path, remote_path)
            sftp.chmod(remote_path, 0o755)
        finally:
            sftp.close()

        exec_cmd = f"{shlex.quote(interpreter)} -lc {shlex.quote(remote_path)}"
        return self.run(exec_cmd, timeout=timeout, env=env, get_pty=get_pty)

    @staticmethod
    def _prepare_command(
        command: str,
        *,
        cwd: str | None,
        env: dict[str, str] | None,
    ) -> str:
        """Prepare a shell command with optional env and working directory.

        This safely quotes environment variable values and working directory,
        then wraps the command under `bash -lc` to ensure a login-like shell
        with expected expansions.
        """
        # Build an "export ..." prefix for env vars (safe quoting)
        env_prefix = ""
        if env:
            exports = "; ".join(
                f'export {k}={shlex.quote(v if v is not None else "")}'
                for k, v in env.items()
            )
            env_prefix = exports + "; "

        # Optional working directory
        if cwd:
            command = f"cd {shlex.quote(cwd)} && {command}"

        # Execute under bash -lc so we get a login-like shell and proper expansions
        return f"/bin/bash -lc {shlex.quote(env_prefix + command)}"
