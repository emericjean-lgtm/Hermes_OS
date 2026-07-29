"""Hardware profile for Hermes OS (HOS-062).

Determines recommended installation profile and compatible models
based on detected hardware.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HardwareProfile:
    """Recommended hardware profile for Hermes OS installation."""

    profile_name: str = "cpu_only"
    label: str = "CPU Only"
    description: str = "Basic profile for systems without dedicated GPU"

    min_ram_gb: int = 4
    recommended_ram_gb: int = 8
    min_disk_gb: int = 10
    recommended_disk_gb: int = 50
    requires_gpu: bool = False
    requires_cuda: bool = False
    requires_rocm: bool = False
    min_vram_mb: int = 0
    recommended_vram_mb: int = 0
    max_concurrent_tasks: int = 1
    recommended_models: list[str] = field(default_factory=lambda: ["tinyllama"])
    supports_ollama: bool = True
    supports_ktransformers: bool = False
    docker_compose_file: str = "docker-compose.cpu.yml"
    frontend_build: str = "standalone"

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile_name,
            "label": self.label,
            "description": self.description,
            "requirements": {
                "min_ram_gb": self.min_ram_gb,
                "recommended_ram_gb": self.recommended_ram_gb,
                "min_disk_gb": self.min_disk_gb,
                "recommended_disk_gb": self.recommended_disk_gb,
                "requires_gpu": self.requires_gpu,
                "requires_cuda": self.requires_cuda,
                "requires_rocm": self.requires_rocm,
                "min_vram_mb": self.min_vram_mb,
                "recommended_vram_mb": self.recommended_vram_mb,
            },
            "capabilities": {
                "max_concurrent_tasks": self.max_concurrent_tasks,
                "recommended_models": self.recommended_models,
                "supports_ollama": self.supports_ollama,
                "supports_ktransformers": self.supports_ktransformers,
            },
            "deployment": {
                "docker_compose": self.docker_compose_file,
                "frontend_build": self.frontend_build,
            },
        }


# Predefined hardware profiles
PROFILES: dict[str, HardwareProfile] = {
    "cpu_only": HardwareProfile(
        profile_name="cpu_only",
        label="CPU Only",
        description="For systems without a dedicated GPU or with limited RAM (<8GB)",
        min_ram_gb=4,
        recommended_ram_gb=8,
        min_disk_gb=10,
        recommended_disk_gb=30,
        max_concurrent_tasks=1,
        recommended_models=["tinyllama", "phi3:3.8b"],
        docker_compose_file="docker-compose.cpu.yml",
    ),
    "local_gpu": HardwareProfile(
        profile_name="local_gpu",
        label="Local GPU",
        description="For desktops/laptops with NVIDIA GPU (4GB+ VRAM)",
        min_ram_gb=8,
        recommended_ram_gb=16,
        min_disk_gb=20,
        recommended_disk_gb=100,
        requires_gpu=True,
        requires_cuda=True,
        min_vram_mb=4096,
        recommended_vram_mb=8192,
        max_concurrent_tasks=2,
        recommended_models=["llama3.2:3b", "codellama:7b", "mistral:7b"],
        supports_ktransformers=True,
        docker_compose_file="docker-compose.gpu.yml",
    ),
    "wsl": HardwareProfile(
        profile_name="wsl",
        label="Windows WSL",
        description="For Windows users via WSL2 with optional GPU passthrough",
        min_ram_gb=8,
        recommended_ram_gb=16,
        min_disk_gb=20,
        recommended_disk_gb=50,
        max_concurrent_tasks=2,
        recommended_models=["llama3.2:3b", "phi3:3.8b"],
        docker_compose_file="docker-compose.cpu.yml",
    ),
    "docker": HardwareProfile(
        profile_name="docker",
        label="Docker Deployment",
        description="Containerized deployment for servers without GPU",
        min_ram_gb=8,
        recommended_ram_gb=16,
        min_disk_gb=20,
        recommended_disk_gb=50,
        max_concurrent_tasks=2,
        recommended_models=["llama3.2:3b", "phi3:3.8b"],
        docker_compose_file="docker-compose.yml",
    ),
    "server": HardwareProfile(
        profile_name="server",
        label="Production Server",
        description="Production server with PostgreSQL, Redis, and full monitoring",
        min_ram_gb=16,
        recommended_ram_gb=32,
        min_disk_gb=50,
        recommended_disk_gb=200,
        requires_gpu=False,
        max_concurrent_tasks=8,
        recommended_models=["llama3.2:3b", "codellama:7b", "mistral:7b"],
        docker_compose_file="docker-compose.gpu.yml",
    ),
    "cloud_gpu": HardwareProfile(
        profile_name="cloud_gpu",
        label="Cloud GPU",
        description="Cloud deployment with GPU (24GB+ VRAM recommended)",
        min_ram_gb=16,
        recommended_ram_gb=64,
        min_disk_gb=50,
        recommended_disk_gb=500,
        requires_gpu=True,
        requires_cuda=True,
        min_vram_mb=8192,
        recommended_vram_mb=24000,
        max_concurrent_tasks=16,
        recommended_models=["llama3.1:70b", "codellama:34b", "llama3.2:3b"],
        supports_ktransformers=True,
        docker_compose_file="docker-compose.gpu.yml",
    ),
}


def get_profile(name: str) -> HardwareProfile | None:
    return PROFILES.get(name)
