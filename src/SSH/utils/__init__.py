"""Utility helpers for SSH MCP tools.

This package groups small, focused helpers used by SSH tools:
- auth: request-context auth header parsing
- masking: safe value masking for logs
- osinfo: parsing and detection for distro/platform
- network: lightweight reachability checks
- types: shared TypedDict contracts for tool results
"""

from .types import (
    BaseResult,
    DistroInfo,
    ListVMsResult,
    NetworkInfo,
    PlatformInfo,
    RunCommandResult,
    VMInfoResult,
    VMUpResult,
)

__all__ = [
    "BaseResult",
    "RunCommandResult",
    "ListVMsResult",
    "VMUpResult",
    "DistroInfo",
    "PlatformInfo",
    "NetworkInfo",
    "VMInfoResult",
]
