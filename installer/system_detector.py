"""System Detection for Hermes OS (HOS-062).

Detects OS, CPU, RAM, GPU, VRAM, storage, and recommends
hardware profile and models.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SystemInfo:
    os_type: str = ""
    os_version: str = ""
    cpu_model: str = ""
    cpu_cores: int = 0
    cpu_threads: int = 0
    ram_total_gb: float = 0.0
    ram_available_gb: float = 0.0
    swap_total_gb: float = 0.0
    gpu_count: int = 0
    gpu_models: list[str] = field(default_factory=list)
    gpu_vram_total_mb: int = 0
    gpu_vram_free_mb: int = 0
    has_cuda: bool = False
    has_rocm: bool = False
    has_vulkan: bool = False
    disk_total_gb: float = 0.0
    disk_free_gb: float = 0.0
    is_wsl: bool = False
    is_docker: bool = False
    python_version: str = ""
    docker_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "os": f"{self.os_type} {self.os_version}",
            "cpu": f"{self.cpu_model} ({self.cpu_cores}C/{self.cpu_threads}T)",
            "ram": f"{self.ram_total_gb:.1f} GB",
            "gpu": self.gpu_models or ["None"],
            "vram": f"{self.gpu_vram_total_mb} MB" if self.gpu_vram_total_mb > 0 else "N/A",
            "disk": f"{self.disk_free_gb:.0f}/{self.disk_total_gb:.0f} GB free",
            "cuda": self.has_cuda,
            "rocm": self.has_rocm,
            "wsl": self.is_wsl,
            "docker": self.docker_available,
        }


class SystemDetector:
    """Detects system hardware and software configuration."""

    def detect(self) -> SystemInfo:
        info = SystemInfo()
        self._detect_os(info)
        self._detect_cpu(info)
        self._detect_ram(info)
        self._detect_gpu(info)
        self._detect_disk(info)
        self._detect_environment(info)
        info.python_version = platform.python_version()
        info.docker_available = self._check_command("docker")
        return info

    def detect_and_recommend(self) -> tuple[SystemInfo, str, list[str]]:
        """Detect system and return (info, recommended_profile, recommended_models)."""
        info = self.detect()
        profile = self._recommend_profile(info)
        models = self._recommend_models(info)
        return info, profile, models

    # ── Private detection ──

    def _detect_os(self, info: SystemInfo) -> None:
        info.os_type = platform.system()
        info.os_version = platform.release()
        if info.os_type == "Linux":
            try:
                with open("/proc/version") as f:
                    if "microsoft" in f.read().lower():
                        info.is_wsl = True
            except OSError:
                pass

    def _detect_cpu(self, info: SystemInfo) -> None:
        try:
            info.cpu_cores = os.cpu_count() or 0
            info.cpu_threads = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else info.cpu_cores
        except Exception:
            info.cpu_cores = 0
            info.cpu_threads = 0

        info.cpu_model = platform.processor() or "Unknown"
        if info.os_type == "Linux":
            try:
                with open("/proc/cpuinfo") as f:
                    for line in f:
                        if "model name" in line:
                            info.cpu_model = line.split(":")[1].strip()
                            break
            except OSError:
                pass

    def _detect_ram(self, info: SystemInfo) -> None:
        if info.os_type == "Linux":
            try:
                with open("/proc/meminfo") as f:
                    for line in f:
                        if "MemTotal" in line:
                            kb = int(line.split()[1])
                            info.ram_total_gb = kb / 1024 / 1024
                        elif "MemAvailable" in line:
                            kb = int(line.split()[1])
                            info.ram_available_gb = kb / 1024 / 1024
                        elif "SwapTotal" in line:
                            kb = int(line.split()[1])
                            info.swap_total_gb = kb / 1024 / 1024
            except OSError:
                pass
        else:
            import psutil  # type: ignore
            try:
                info.ram_total_gb = psutil.virtual_memory().total / (1024**3)
                info.ram_available_gb = psutil.virtual_memory().available / (1024**3)
            except Exception:
                pass

    def _detect_gpu(self, info: SystemInfo) -> None:
        # NVIDIA / CUDA
        nvidia_smi = shutil.which("nvidia-smi")
        if nvidia_smi:
            try:
                result = subprocess.run(
                    [nvidia_smi, "--query-gpu=name,memory.total,memory.free",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    for line in result.stdout.strip().split("\n"):
                        parts = [p.strip() for p in line.split(",")]
                        if len(parts) >= 3:
                            info.gpu_models.append(parts[0])
                            info.gpu_vram_total_mb += int(float(parts[1]))
                            info.gpu_vram_free_mb += int(float(parts[2]))
                            info.gpu_count += 1
                    info.has_cuda = info.gpu_count > 0
            except (subprocess.TimeoutExpired, OSError, ValueError):
                pass

        # AMD ROCm
        rocm_smi = shutil.which("rocm-smi")
        if rocm_smi or os.path.exists("/opt/rocm"):
            info.has_rocm = True
            if not rocm_smi:
                try:
                    result = subprocess.run(
                        ["rocm-smi", "--showproductname"],
                        capture_output=True, text=True, timeout=10,
                    )
                    if result.returncode == 0:
                        info.gpu_count = result.stdout.count("GPU")
                except (subprocess.TimeoutExpired, OSError):
                    pass

    def _detect_disk(self, info: SystemInfo) -> None:
        try:
            stat = shutil.disk_usage(os.getcwd())
            info.disk_total_gb = stat.total / (1024**3)
            info.disk_free_gb = stat.free / (1024**3)
        except OSError:
            pass

    def _detect_environment(self, info: SystemInfo) -> None:
        if os.path.exists("/.dockerenv"):
            info.is_docker = True

    def _check_command(self, cmd: str) -> bool:
        return shutil.which(cmd) is not None

    def _recommend_profile(self, info: SystemInfo) -> str:
        if info.gpu_count > 0 and info.gpu_vram_total_mb >= 8000:
            if info.is_docker:
                return "cloud_gpu" if info.ram_total_gb >= 16 else "docker"
            return "local_gpu"
        if info.gpu_vram_total_mb >= 4000:
            return "local_gpu"
        if info.is_wsl:
            return "wsl"
        if info.is_docker:
            return "docker"
        if info.ram_total_gb >= 32:
            return "server"
        return "cpu_only"

    def _recommend_models(self, info: SystemInfo) -> list[str]:
        models = []
        if info.gpu_vram_total_mb >= 24000:
            models.extend(["llama3.1:70b", "codellama:34b", "llama3.2:3b"])
        elif info.gpu_vram_total_mb >= 8000:
            models.extend(["llama3.2:3b", "codellama:7b", "mistral:7b"])
        elif info.gpu_vram_total_mb >= 4000:
            models.extend(["llama3.2:3b", "phi3:3.8b"])
        elif info.ram_total_gb >= 16:
            models.extend(["llama3.2:3b", "phi3:3.8b", "tinyllama"])
        else:
            models.append("tinyllama")
        return models
