"""Permission system for YAML-defined users, groups, and VMs.

This module provides:
- YAML schema validation for users/groups/vms relationships
- Authentication helpers based on plaintext API keys
- Authorization helpers to compute allowed VMs for a given API key

Design goals:
- No external dependencies beyond PyYAML already used in the project
- Backward compatible: if no `users` section is present in YAML, permissions
  are considered disabled and access is unrestricted
"""

from __future__ import annotations

from typing import Any, Iterable, TypeVar


class SchemaError(ValueError):
    """Raised when the YAML configuration structure is invalid."""


T = TypeVar("T")


def _as_list(x: T | list[T] | None) -> list[T]:
    """Return a list form of the input.

    - None -> []
    - list[T] -> same list
    - T -> [T]
    """
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def validate_config_schema(data: dict[str, Any]) -> None:
    """Validate the high-level config schema.

    Checks:
    - vms: list of objects with required keys (name, host, user), optional port(int), key(str)
    - groups: list of objects with name and list of vms (must reference existing vms)
    - users: list of objects with name, api_key, and groups (must reference existing groups)

    Backward compatibility: when `users` or `groups` are absent, the function only
    validates the `vms` portion and returns without error (permissions disabled).

    Raises:
        SchemaError: on structural issues; the message contains human-friendly details.
    """
    if not isinstance(data, dict):
        raise SchemaError("Top-level YAML must be a mapping/object")

    # Validate VMs
    vms = data.get("vms")
    if not isinstance(vms, list) or not vms:
        raise SchemaError("'vms' must be a non-empty list")
    vm_names: set[str] = set()
    for i, vm in enumerate(vms):
        if not isinstance(vm, dict):
            raise SchemaError(f"vms[{i}] must be a mapping/object")
        for req in ("name", "host", "user"):
            if req not in vm:
                raise SchemaError(f"vms[{i}] is missing required field '{req}'")
        name = str(vm["name"]).strip()
        if not name:
            raise SchemaError(f"vms[{i}].name cannot be empty")
        if name in vm_names:
            raise SchemaError(f"Duplicate VM name '{name}'")
        vm_names.add(name)
        if "port" in vm and not isinstance(vm["port"], int):
            raise SchemaError(f"vms[{i}].port must be an integer if provided")
        if "key" in vm and vm["key"] is not None and not isinstance(vm["key"], str):
            raise SchemaError(f"vms[{i}].key must be a string if provided")

    # If no users/groups defined, permissions are disabled: stop here
    users = data.get("users")
    groups = data.get("groups")
    if users is None and groups is None:
        return

    # Validate groups if present
    group_names: set[str] = set()
    if groups is not None:
        if not isinstance(groups, list):
            raise SchemaError("'groups' must be a list if provided")
        for i, grp in enumerate(groups):
            if not isinstance(grp, dict):
                raise SchemaError(f"groups[{i}] must be a mapping/object")
            if "name" not in grp:
                raise SchemaError(f"groups[{i}] missing 'name'")
            gname = str(grp["name"]).strip()
            if not gname:
                raise SchemaError(f"groups[{i}].name cannot be empty")
            if gname in group_names:
                raise SchemaError(f"Duplicate group name '{gname}'")
            group_names.add(gname)
            vms_list = _as_list(grp.get("vms"))
            for vmn in vms_list:
                if vmn not in vm_names:
                    raise SchemaError(
                        f"groups[{i}] references unknown VM '{vmn}'"
                    )

    # Validate users if present
    if users is not None:
        if not isinstance(users, list):
            raise SchemaError("'users' must be a list if provided")
        seen_api_keys: set[str] = set()
        for i, usr in enumerate(users):
            if not isinstance(usr, dict):
                raise SchemaError(f"users[{i}] must be a mapping/object")
            for req in ("name", "api_key"):
                if req not in usr:
                    raise SchemaError(f"users[{i}] missing '{req}'")
            name = str(usr["name"]).strip()
            if not name:
                raise SchemaError(f"users[{i}].name cannot be empty")
            api_key = usr["api_key"]
            if not isinstance(api_key, str) or not api_key:
                raise SchemaError(f"users[{i}].api_key must be a non-empty string")
            if api_key in seen_api_keys:
                raise SchemaError("Duplicate api_key across users is not allowed")
            seen_api_keys.add(api_key)
            groups_list = _as_list(usr.get("groups"))
            for g in groups_list:
                if groups is None or g not in group_names:
                    raise SchemaError(
                        f"users[{i}] references unknown group '{g}'"
                    )


def permissions_enabled(data: dict[str, Any]) -> bool:
    """Return True if the config enables permissions (has a users section)."""
    return isinstance(data.get("users"), list)


def find_user_by_api_key(data: dict[str, Any], api_key: str) -> dict[str, Any] | None:
    """Return the user dict matching the api_key, or None."""
    users = data.get("users")
    if not isinstance(users, list):
        return None
    for user in users:
        if isinstance(user, dict) and user.get("api_key") == api_key:
            return user
    return None


def groups_for_user(data: dict[str, Any], user: dict[str, Any]) -> list[str]:
    """Return the list of group names for a user object from the YAML data.

    The `data` param is unused but kept for future-proofing/symmetry.
    """
    return [str(g) for g in _as_list(user.get("groups"))]


def vms_for_groups(data: dict[str, Any], groups: Iterable[str]) -> list[str]:
    """Return a de-duplicated list of VM names for the provided groups."""
    # Build group -> vms index once
    idx: dict[str, list[str]] = {}
    for grp in _as_list(data.get("groups")):
        if isinstance(grp, dict):
            idx[str(grp.get("name"))] = [str(v) for v in _as_list(grp.get("vms"))]
    # Flatten VMs for provided groups
    result: list[str] = []
    seen: set[str] = set()
    for g in groups:
        for vmn in idx.get(g, []):
            if vmn not in seen:
                seen.add(vmn)
                result.append(vmn)
    return result


def authorized_vm_names(data: dict[str, Any], api_key: str) -> list[str]:
    """Return list of VM names a user can access for given api_key.

    Behavior:
    - If permissions are disabled (no 'users' key), return all VM names.
    - If enabled and api_key matches a user, return VMs via their groups.
    - If enabled and api_key invalid, raise ValueError.
    """
    # If permissions are disabled, anyone can access all VMs
    if not permissions_enabled(data):
        vms = data.get("vms") or []
        return [str(vm.get("name")) for vm in vms if isinstance(vm, dict) and vm.get("name")]

    user = find_user_by_api_key(data, api_key)
    if user is None:
        raise ValueError("API key invalid or VM not permitted")
    groups = groups_for_user(data, user)
    return vms_for_groups(data, groups)


def assert_user_can_access_vm(data: dict[str, Any], api_key: str, vm_name: str) -> None:
    """Raise ValueError if api_key is invalid or vm_name not permitted for that user."""
    allowed = authorized_vm_names(data, api_key)
    if vm_name not in allowed:
        raise ValueError("API key invalid or VM not permitted")
