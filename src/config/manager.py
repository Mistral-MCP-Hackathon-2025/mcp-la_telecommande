from pathlib import Path
from typing import Union
import yaml

from .credentials import VMCredentials


class ConfigManager:
    def __init__(self, config_path: Union[str, Path]):
        self.config_path = Path(config_path)
        self._vms = self._load_vms_config()

    def _load_vms_config(self) -> dict:
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if "vms" not in data:
            raise ValueError("YAML file must contain a 'vms' field")
        return {vm["name"]: vm for vm in data["vms"]}

    def list_vms(self) -> list[str]:
        return list(self._vms.keys())

    def get_vm_creds(self, vm_name: str) -> VMCredentials:
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
