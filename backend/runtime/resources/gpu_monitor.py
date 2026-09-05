"""GPU Monitor for the Runtime Resource Manager (HOS-035).

Provides GPU/VRAM/temperature monitoring with a no-op fallback
for environments without a GPU (CI, docker, CPU-only).
"""

from __future__ import annotations

import os
import subprocess
import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from backend.runtime.resources import vram_physique
from backend.runtime.resources.resource_models import GPUInfo


class GPUMonitor:
    """Monitor GPU resources (VRAM, temperature, utilisation).

    ## La chaîne de sondes, et pourquoi `/api/ps` n'y est plus (A-15)

    `rocm-smi`, puis `nvidia-smi`, puis les compteurs Windows. Les trois
    mesurent la même chose — l'occupation physique de la carte — et c'est
    la seule sémantique que l'admission sait interpréter.

    `/api/ps` en était le quatrième maillon. Il mesure autre chose : les
    **poids** des modèles résidents d'Ollama, sans le cache KV, sans les
    tampons de calcul, sans un octet de ce que tient un autre processus.
    Sur cette machine, ni `rocm-smi` ni `nvidia-smi` n'existent : ce repli
    de sémantique différente était le chemin **normal** de l'admission, et
    il sous-estimait l'occupation de 1,3 à 2,4 Gio selon la charge —
    toujours dans le sens qui fait croire qu'il reste de la place. Détail
    mesuré dans `vram_physique`.

    Quand aucune sonde ne répond mais que la carte existe, le moniteur le
    dit (`occupation_mesuree=False`) au lieu de rendre un chiffre. Il n'y a
    pas de repli silencieux vers une autre sémantique : c'était le défaut.

    Thread-safe.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._info: GPUInfo = GPUInfo()
        self._last_update: Optional[datetime] = None
        self._update_interval_s: float = 2.0
        self._on_alert: Optional[Callable[[GPUInfo], None]] = None

    def set_alert_handler(self, handler: Callable[[GPUInfo], None]) -> None:
        """Register a callback for when GPU enters warning/critical state."""
        self._on_alert = handler

    def poll(self) -> GPUInfo:
        """Fetch current GPU state. Thread-safe."""
        with self._lock:
            now = datetime.now(timezone.utc)
            if self._last_update and (
                now - self._last_update
            ).total_seconds() < self._update_interval_s:
                return self._info
            self._info = self._poll_now()
            self._last_update = now
            return self._info

    def _poll_now(self) -> GPUInfo:
        """Internal: attempt various monitoring methods.

        Trois sondes de même sémantique, puis l'aveu. Jamais un repli vers
        une mesure qui répond à une autre question (A-15).
        """
        info = self._try_rocm_smi()
        if info is not None:
            return info
        info = self._try_nvidia_smi()
        if info is not None:
            return info
        info = self._try_compteurs_windows()
        if info is not None:
            return info
        return self._non_mesure()

    def _non_mesure(self) -> GPUInfo:
        """Aucune sonde n'a répondu. Reste à savoir s'il y a une carte.

        Sans carte détectable, il n'y a pas de contrainte VRAM à faire
        respecter et l'admission passe — comportement inchangé, et correct
        sur une machine sans GPU.

        Avec une carte dont on ne sait pas lire l'occupation, on ne rend
        **pas** de chiffres : `occupation_mesuree=False` fait refuser
        l'admission. Prétendre 0 octet occupé sur une carte qu'on ne lit
        pas est exactement l'erreur que A-15 corrige.
        """
        nom, total = self._adapter_vram_total()
        if not total:
            return GPUInfo(available=False)
        return GPUInfo(
            name=nom or "unknown",
            vendor="AMD" if nom and "AMD" in nom.upper() else "unknown",
            vram_total_bytes=total,
            # Volontairement à zéro et non « total » : ces champs ne
            # doivent pas être lus quand `occupation_mesuree` est faux.
            vram_used_bytes=0,
            vram_free_bytes=0,
            available=True,
            occupation_mesuree=False,
        )

    def _try_rocm_smi(self) -> Optional[GPUInfo]:
        """Attempt to query AMD GPU via rocm-smi."""
        try:
            result = subprocess.run(
                ["rocm-smi", "--showmeminfo", "vram", "--json"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return None
            import json
            data = json.loads(result.stdout)
            for card_id, card_data in data.items():
                # Fields vary by rocm-smi version
                vram_total = _find_int(card_data, "VRAM Total Memory (B)", "VRAM Total")
                vram_used = _find_int(card_data, "VRAM Total Used Memory (B)", "VRAM Used")
                vram_free = max(0, vram_total - vram_used)
                return GPUInfo(
                    name=f"AMD-{card_id}",
                    vendor="AMD",
                    vram_total_bytes=vram_total,
                    vram_used_bytes=vram_used,
                    vram_free_bytes=vram_free,
                    available=True,
                )
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass
        return None

    def _try_nvidia_smi(self) -> Optional[GPUInfo]:
        """Attempt to query NVIDIA GPU via nvidia-smi."""
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,memory.used,memory.free,temperature.gpu,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return None
            parts = result.stdout.strip().split(",")
            return GPUInfo(
                name=parts[0].strip(),
                vendor="NVIDIA",
                vram_total_bytes=int(float(parts[1])) * 1024 * 1024,
                vram_used_bytes=int(float(parts[2])) * 1024 * 1024,
                vram_free_bytes=int(float(parts[3])) * 1024 * 1024,
                temperature_celsius=(
                    float(parts[4]) if len(parts) > 4 and parts[4].strip() != "[N/A]" else None
                ),
                utilization_pct=(
                    float(parts[5]) if len(parts) > 5 and parts[5].strip() != "[N/A]" else None
                ),
                available=True,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass
        return None

    def _try_compteurs_windows(self) -> Optional[GPUInfo]:
        """L'occupation réelle de la carte, via les compteurs de Windows.

        Ce qui remplace le repli `/api/ps`. Même sémantique que `rocm-smi` :
        la mémoire vidéo dédiée effectivement détenue sur la machine, tous
        détenteurs confondus. La capacité vient du registre — `AdapterRAM`
        de WMI est un champ 32 bits qui annonce 4 Gio pour cette carte de 16.

        `None` quand la mesure n'aboutit pas : l'appelant doit alors dire
        qu'il ne sait pas, pas inventer un chiffre.
        """
        occupation = vram_physique.occupation_physique_octets()
        if occupation is None:
            return None

        nom, total = self._adapter_vram_total()
        if not total:
            # Une occupation sans capacité ne se compare à rien. Laisser
            # `_non_mesure` trancher plutôt que rendre un pourcentage
            # calculé sur zéro.
            return None

        return GPUInfo(
            name=nom or "unknown",
            vendor="AMD" if nom and "AMD" in nom.upper() else "unknown",
            vram_total_bytes=total,
            vram_used_bytes=occupation,
            vram_free_bytes=max(total - occupation, 0),
            available=True,
        )

    @staticmethod
    def _adapter_vram_total() -> tuple[str, int]:
        """The adapter's real VRAM capacity. ``("", 0)`` when undetectable.

        On Windows the driver publishes it as ``HardwareInformation.qwMemorySize``.
        WMI's ``Win32_VideoController.AdapterRAM`` is *not* used: it is a 32-bit
        field and reports 4 GiB for this 16 GiB card.
        """
        if os.name != "nt":
            return "", 0
        try:
            import winreg
        except ImportError:  # pragma: no cover - non-Windows
            return "", 0

        key_path = (r"SYSTEM\CurrentControlSet\Control\Class"
                    r"\{4d36e968-e325-11ce-bfc1-08002be10318}")
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as root:
                for index in range(16):
                    try:
                        subkey_name = winreg.EnumKey(root, index)
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(root, subkey_name) as sub:
                            size, _ = winreg.QueryValueEx(
                                sub, "HardwareInformation.qwMemorySize")
                            try:
                                desc, _ = winreg.QueryValueEx(sub, "DriverDesc")
                            except OSError:
                                desc = ""
                            if int(size) > 0:
                                return str(desc), int(size)
                    except OSError:
                        continue
        except OSError:
            pass
        return "", 0


class NoopGPUMonitor(GPUMonitor):
    """GPU monitor that returns empty data (for testing/CI)."""

    def _poll_now(self) -> GPUInfo:
        return GPUInfo(available=False)


# ── Helpers ─────────────────────────────────────────────────


def _find_int(data: dict, *keys: str) -> int:
    """Find the first matching key in a dict and return its int value."""
    for key in keys:
        if key in data:
            try:
                return int(data[key])
            except (ValueError, TypeError):
                pass
    return 0
