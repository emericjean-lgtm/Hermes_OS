"""Backup Manager for Hermes OS (HOS-062).

Handles automated backups, restoration, and export/import
of Hermes OS configuration and memory data.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class BackupManager:
    """Manages backups of Hermes OS data."""

    def __init__(self, backup_dir: str = "backups", data_dir: str = "data"):
        self._backup_dir = Path(backup_dir)
        self._data_dir = Path(data_dir)
        self._lock = threading.Lock()
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        self._backup_history: list[dict[str, Any]] = []

    # ── Public API ──

    def create_backup(self, name: str = "") -> str:
        """Create a full backup of Hermes OS data."""
        with self._lock:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            backup_name = name or f"hermes_backup_{timestamp}"
            backup_path = self._backup_dir / f"{backup_name}.zip"

            with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
                if self._data_dir.exists():
                    for file_path in self._data_dir.rglob("*"):
                        if file_path.is_file():
                            arcname = str(file_path.relative_to(self._data_dir.parent))
                            zf.write(file_path, arcname)

                config_files = list(Path("backend/config/profiles").glob("*.json"))
                config_files += [Path("config.json"), Path("hermes_config.json")]
                for cf in config_files:
                    if cf.exists():
                        zf.write(cf, f"config/{cf.name}")

                meta = {
                    "backup_name": backup_name,
                    "created_at": timestamp,
                    "version": "1.0.0",
                    "files": [str(f) for f in self._data_dir.rglob("*") if f.is_file()],
                }
                zf.writestr("backup_metadata.json", json.dumps(meta, indent=2))

            info = {
                "name": backup_name,
                "path": str(backup_path),
                "size_mb": round(backup_path.stat().st_size / (1024 * 1024), 2),
                "created_at": timestamp,
            }
            self._backup_history.append(info)
            return backup_name

    def restore(self, backup_name: str, target_dir: str | None = None) -> bool:
        """Restore data from a backup."""
        with self._lock:
            backup_path = self._backup_dir / f"{backup_name}.zip"
            if not backup_path.exists():
                raise FileNotFoundError(f"Backup not found: {backup_name}")

            restore_dir = Path(target_dir) if target_dir else self._data_dir
            restore_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(backup_path, "r") as zf:
                zf.extractall(restore_dir.parent)
            return True

    def list_backups(self) -> list[dict[str, Any]]:
        backups = []
        for f in sorted(self._backup_dir.glob("*.zip"), reverse=True):
            stats = f.stat()
            backups.append({
                "name": f.stem,
                "path": str(f),
                "size_mb": round(stats.st_size / (1024 * 1024), 2),
                "created_at": datetime.fromtimestamp(stats.st_mtime, tz=timezone.utc).isoformat(),
            })
        return backups

    def delete_backup(self, backup_name: str) -> bool:
        backup_path = self._backup_dir / f"{backup_name}.zip"
        if backup_path.exists():
            backup_path.unlink()
            return True
        return False

    def export_config(self, path: str = "hermes_export.json") -> str:
        """Export current configuration to JSON."""
        from backend.config import get_config
        config = get_config()
        data = config.to_dict()
        export_path = Path(path)
        with open(export_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        return str(export_path)

    def import_config(self, path: str) -> bool:
        """Import configuration from JSON."""
        import_path = Path(path)
        if not import_path.exists():
            return False
        with open(import_path) as f:
            data = json.load(f)
        from backend.config import ConfigManager
        cm = ConfigManager()
        cm.reload()
        return True

    def auto_backup(self, interval_h: int = 24) -> None:
        """Run automatic backup if enough time has passed."""
        backups = self.list_backups()
        if backups:
            last = datetime.fromisoformat(backups[0]["created_at"])
            elapsed = (datetime.now(timezone.utc) - last).total_seconds()
            if elapsed < interval_h * 3600:
                return
        self.create_backup("auto")

    def get_stats(self) -> dict[str, Any]:
        backups = self.list_backups()
        total_size = sum(b["size_mb"] for b in backups)
        return {
            "total_backups": len(backups),
            "total_size_mb": round(total_size, 2),
            "latest_backup": backups[0] if backups else None,
            "backup_dir": str(self._backup_dir),
            "data_dir": str(self._data_dir),
        }
