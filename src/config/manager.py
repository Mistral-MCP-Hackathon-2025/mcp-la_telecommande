"""Configuration loader for VM credentials.

Reads a YAML file containing a list of VM entries and exposes helpers to
list available VM names and obtain typed credentials for a given VM.
"""

from pathlib import Path
from typing import Union

import yaml

from .credentials import VMCredentials


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
        self._vms = self._load_vms_config()

    def _load_vms_config(self) -> dict[str, dict]:
        """Load and validate VM entries from the YAML configuration file.

        Returns:
            A mapping of VM name -> raw VM dictionary from YAML.

        Raises:
            ValueError: If the YAML does not contain the required "vms" field.
        """
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if "vms" not in data:
            raise ValueError("YAML file must contain a 'vms' field")
        return {vm["name"]: vm for vm in data["vms"]}

    def list_vms(self) -> list[str]:
        """Return the list of VM names available in the configuration."""
        return list(self._vms.keys())

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
