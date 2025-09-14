"""Shared TypedDict contracts for SSH MCP tools."""

from __future__ import annotations

from typing import TypedDict


class BaseResult(TypedDict):
    status: str
    stdout: str
    stderr: str
    return_code: int


class RunCommandResult(BaseResult):
    command: str


class ListVMsResult(TypedDict):
    vms: list[str]


class VMUpResult(TypedDict):
    vm: str
    host: str
    port: int
    reachable: bool
    latency_ms: float | None
    reason: str | None


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
