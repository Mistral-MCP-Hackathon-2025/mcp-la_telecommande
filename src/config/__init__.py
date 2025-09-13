"""
Config Module

This package provides functions to get VMs names and creds from a YAML config file.
"""

from src.config.credentials import VMCredentials
from src.config.manager import ConfigManager

__all__ = ["VMCredentials", "ConfigManager"]
