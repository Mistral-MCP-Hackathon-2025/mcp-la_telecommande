"""Configuration loader for VM credentials and permissions.

Reads a YAML file containing VMs and optionally users/groups permissions.
Exposes helpers to list available VM names, obtain typed credentials, and
perform permission checks based on plaintext API keys.
"""

from pathlib import Path
from typing import Any, Union

import yaml

from .credentials import VMCredentials
from .permissions import (
    assert_user_can_access_vm,
    authorized_vm_names,
    validate_config_schema,
)


class ConfigManager:
    """Manage access to VM configuration defined in a YAML file.

    The YAML file is expected to contain a top-level "vms" key with a list of
    VM objects. Each VM object must define at least: "name", "host", and
    "user". Optional keys include "port" (int, default 22) and "key" (str).

    Args:
        config_path: Path to the YAML configuration file.
    """

    def __init__(self, config_path: Union[str, Path]):
        self.config_path = Path(config_path)
        self._data = self._load_yaml()
        # validate schema including optional permissions
        validate_config_schema(self._data)
        self._vms = self._index_vms(self._data)

    def _load_yaml(self) -> dict[str, Any]:
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if "vms" not in data:
            raise ValueError("YAML file must contain a 'vms' field")
        return data

    @staticmethod
    def _index_vms(data: dict[str, Any]) -> dict[str, dict]:
        return {vm["name"]: vm for vm in data["vms"]}

    def list_vms(self) -> list[str]:
        """Return the list of VM names available in the configuration."""
        return list(self._vms.keys())

    @property
    def raw(self) -> dict[str, Any]:
        """Return raw loaded YAML data."""
        return self._data

    def get_vm_creds(self, vm_name: str) -> VMCredentials:
        """Return validated SSH credentials for the requested VM.

        Args:
            vm_name: Name of the VM as specified in the YAML configuration.

        Returns:
            A populated VMCredentials instance.

        Raises:
            ValueError: If the VM name cannot be found in the configuration.
        """
        if vm_name not in self._vms:
            raise ValueError(f"VM '{vm_name}' not found")
        vm = self._vms[vm_name]
        host = vm["host"]
        user = vm["user"]
        port = int(vm.get("port", 22))
        key = vm.get("key")
        return VMCredentials(
            host,
            user,
            port,
            key,
        )

    # -------------
    # Permissions
    # -------------

    def authorized_vms_for_key(self, api_key: str) -> list[str]:
        """Return list of VM names the API key is allowed to access.

        If permissions are disabled in the YAML, returns all VMs.
        """
        return authorized_vm_names(self._data, api_key)

    def ensure_can_access(self, api_key: str, vm_name: str) -> None:
        """Raise ValueError if API key cannot access the specified VM.

        Error message intentionally matches tooling expectations: "API key invalid or VM not permitted".
        """
        assert_user_can_access_vm(self._data, api_key, vm_name)
