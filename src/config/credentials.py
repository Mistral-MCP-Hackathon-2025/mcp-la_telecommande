"""Credentials data models for SSH-enabled virtual machines.

This module defines lightweight, typed containers representing the minimum
information required to establish an SSH connection to a remote VM.
"""

from dataclasses import dataclass


@dataclass
class VMCredentials:
    """Typed credentials required to connect to a VM over SSH.

    Attributes:
        host: DNS name or IP of the remote VM.
        user: Username to authenticate with on the remote VM.
        port: SSH server port on the remote VM (defaults to 22 at the caller).
        key: Private key material (OpenSSH or PEM) as a string, or None to rely
            on agent/known keys configuration.
    """

    host: str
    user: str
    port: int
    key: str | None
