from __future__ import annotations

import io
import os
import shlex
from typing import Dict, Optional, Tuple

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
        password: Optional[str] = None,
        key_filename: Optional[str] = None,
        key_content: Optional[str] = None,
        timeout: Optional[float] = 15.0,
        look_for_keys: bool = True,
        allow_agent: bool = True,
        known_hosts_policy: paramiko.MissingHostKeyPolicy = paramiko.AutoAddPolicy(),
    ):
        self.hostname = hostname
        self.username = username
        self.port = port
        self.password = password
        self.key_filename = os.path.expanduser(key_filename) if key_filename else None
        self.key_content = key_content
        self.timeout = timeout
        self.look_for_keys = look_for_keys
        self.allow_agent = allow_agent

        # Validate that only one key method is provided
        if key_filename and key_content:
            raise ValueError("Cannot specify both key_filename and key_content")

        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(known_hosts_policy)
        self._connected = False
        self._pkey = None

    def __enter__(self) -> "RemoteExecutor":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def connect(self) -> None:
        if self._connected:
            return
        
        # Prepare the private key if key_content is provided
        pkey = None
        if self.key_content:
            try:
                pkey = self._parse_private_key(self.key_content)
            except Exception as e:
                raise ValueError(f"Failed to parse private key: {e}")
        
        try:
            self._client.connect(
                hostname=self.hostname,
                port=self.port,
                username=self.username,
                password=self.password,
                key_filename=self.key_filename,
                pkey=pkey,
                timeout=self.timeout,
                look_for_keys=self.look_for_keys,
                allow_agent=self.allow_agent,
            )
            self._connected = True
        except paramiko.AuthenticationException as e:
            raise ValueError(f"SSH Authentication failed for {self.username}@{self.hostname}: {e}")
        except Exception as e:
            raise ValueError(f"SSH Connection failed to {self.hostname}:{self.port}: {e}")

    def close(self) -> None:
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
                
                base64_lines = [base64_content[i:i+64] for i in range(0, len(base64_content), 64)]
                key_content = begin_marker + "\n" + "\n".join(base64_lines) + "\n" + end_marker
        
        if "BEGIN OPENSSH PRIVATE KEY" in key_content:
            key_file = io.StringIO(key_content)
            try:
                if hasattr(paramiko, 'Ed25519Key'):
                    return paramiko.Ed25519Key.from_private_key(key_file)
            except Exception as e:
                raise ValueError(f"Failed to parse OpenSSH private key as Ed25519: {e}")
        
        key_file = io.StringIO(key_content)
        try:
            if hasattr(paramiko, 'RSAKey'):
                return paramiko.RSAKey.from_private_key(key_file)
        except Exception as e:
            raise ValueError(f"Failed to parse PEM private key as RSA: {e}")

    def run(
        self,
        command: str,
        *,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        get_pty: bool = False,
    ) -> Tuple[str, str, int]:
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
        remote_path: Optional[str] = None,
        interpreter: str = "/bin/bash",
        timeout: Optional[float] = None,
        env: Optional[Dict[str, str]] = None,
        get_pty: bool = False,
    ) -> Tuple[str, str, int]:
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

        exec_cmd = f'{shlex.quote(interpreter)} -lc {shlex.quote(remote_path)}'
        return self.run(exec_cmd, timeout=timeout, env=env, get_pty=get_pty)

    @staticmethod
    def _prepare_command(
        command: str,
        *,
        cwd: Optional[str],
        env: Optional[Dict[str, str]],
    ) -> str:
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

