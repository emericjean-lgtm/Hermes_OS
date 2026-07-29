"""Installer package for Hermes OS (HOS-062)."""

from .hardware_profile import HardwareProfile
from .system_detector import SystemDetector, SystemInfo

__all__ = [
    "SystemDetector",
    "SystemInfo",
    "HardwareProfile",
]
