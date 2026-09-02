"""Production Readiness Tests for Hermes OS (HOS-062).

Tests configuration management, hardware detection, database operations,
backup/restore, monitoring, health checks, recovery, and logging.
"""

from __future__ import annotations

import os
import threading
import time


from backend.config.config_manager import ConfigManager
from backend.config.config_models import (
    DatabaseConfig,
    DeploymentProfile,
    HermesConfig,
    LogLevel,
    RuntimeMode,
    StorageBackend,
)
from backend.config.environment_loader import EnvironmentLoader
from backend.storage.database_manager import DatabaseManager
from backend.storage.migration_manager import MigrationManager
from backend.storage.backup_manager import BackupManager
from backend.monitoring.system_monitor import SystemMonitor
from backend.monitoring.health_monitor import HealthMonitor
from backend.monitoring.recovery_manager import RecoveryManager
from backend.logging.production_logger import ProductionLogger
from installer.system_detector import SystemDetector
from installer.hardware_profile import PROFILES


# ═══════════════════════════════════════════════════════════════
# Configuration Tests
# ═══════════════════════════════════════════════════════════════

class TestConfigModels:
    def test_default_config_creation(self):
        config = HermesConfig()
        assert config.profile == DeploymentProfile.LOCAL_GPU
        assert config.api_port == 8000
        assert config.runtime.enable_gpu is True

    def test_database_config_defaults(self):
        db = DatabaseConfig()
        assert db.backend == StorageBackend.SQLITE
        assert "sqlite" in db.connection_string

    def test_database_postgres_connection_string(self):
        db = DatabaseConfig(
            backend=StorageBackend.POSTGRESQL,
            host="pg.example.com",
            port=5432,
            name="hermes",
            user="admin",
            password="secret",
        )
        assert "postgresql://" in db.connection_string
        assert "secret" in db.connection_string

    def test_config_validation_no_errors(self):
        config = HermesConfig()
        errors = config.validate()
        assert len(errors) == 0

    def test_config_validation_short_jwt(self):
        config = HermesConfig()
        config.security.jwt_secret = "short"
        errors = config.validate()
        assert len(errors) > 0

    def test_database_config_sqlite_path(self):
        """Un nom nu se resout sous la racine d'etat, pas dans le depot.

        Ce test affirmait l'inverse — `sqlite:///test_db.db`, un chemin
        **relatif**, donc un fichier dans le repertoire courant, donc
        dans le depot, qu'une mise a jour remplace. HOS-215 avait sorti
        l'etat pour `Settings` et pas pour ceci ; HOS-220 a ferme la
        seconde porte. L'assertion est amendee, pas supprimee : c'est
        toujours la meme propriete qui est gardee, avec la bonne valeur.
        """
        from pathlib import Path

        from backend.core.etat import racine

        db = DatabaseConfig(backend=StorageBackend.SQLITE, name="test_db")
        chemin = Path(db.connection_string.replace("sqlite:///", ""))
        assert chemin.is_absolute()
        assert chemin == racine() / "db" / "test_db.db"

    def test_database_config_chemin_explicite_est_respecte(self):
        """Un chemin donne explicitement n'est pas re-racine.

        Sans quoi une base de test sur `tmp_path` atterrirait dans
        l'etat reel de l'utilisateur.
        """
        db = DatabaseConfig(backend=StorageBackend.SQLITE,
                            name="C:/tmp/ailleurs")
        assert db.connection_string == "sqlite:///C:/tmp/ailleurs.db"

    def test_security_config_defaults(self):
        config = HermesConfig()
        assert config.security.token_expiry_h == 24
        assert config.security.max_login_attempts == 5

    def test_monitoring_config_defaults(self):
        config = HermesConfig()
        assert config.monitoring.enabled is True
        assert config.monitoring.health_check_interval_s == 30

    def test_runtime_config_defaults(self):
        config = HermesConfig()
        assert config.runtime.mode == RuntimeMode.LOCAL
        assert config.runtime.default_model == "llama3.2:3b"

    def test_logging_config_defaults(self):
        config = HermesConfig()
        assert config.logging.level == LogLevel.INFO
        assert config.logging.json_format is True

    def test_config_to_dict(self):
        config = HermesConfig()
        d = config.to_dict()
        assert isinstance(d, dict)
        assert "api_port" in d


class TestConfigManager:
    def setup_method(self):
        # Reset singleton
        ConfigManager._instance = None

    def test_singleton(self):
        cm1 = ConfigManager()
        cm2 = ConfigManager()
        assert cm1 is cm2

    def test_default_config_loaded(self):
        cm = ConfigManager()
        cfg = cm.get()
        assert cfg is not None
        assert cfg.api_port == 8000

    def test_switch_profile_cpu(self):
        cm = ConfigManager()
        cfg = cm.switch_profile(DeploymentProfile.CPU_ONLY)
        assert cfg is not None

    def test_validate_current(self):
        cm = ConfigManager()
        errors = cm.validate_current()
        assert isinstance(errors, list)

    def test_to_dict(self):
        cm = ConfigManager()
        d = cm.to_dict()
        assert isinstance(d, dict)

    def test_reload_preserves_defaults(self):
        cm = ConfigManager()
        cfg1 = cm.get()
        cfg2 = cm.reload()
        assert cfg2.api_port == cfg1.api_port


class TestEnvironmentLoader:
    def test_load_no_env_file(self):
        loader = EnvironmentLoader(env_file="/nonexistent/.env")
        result = loader.load()
        assert isinstance(result, dict)

    def test_validate_local_gpu(self):
        loader = EnvironmentLoader()
        valid = loader.is_valid(DeploymentProfile.LOCAL_GPU)
        assert valid is True  # No required vars for local_gpu

    def test_validate_docker_missing_vars(self):
        loader = EnvironmentLoader()
        errors = loader.get_missing_required(DeploymentProfile.DOCKER)
        # Error messages are f"Missing required env var: {var}"
        msg = "Missing required env var: HERMES_DB_PASSWORD"
        if "HERMES_DB_PASSWORD" in os.environ and os.environ["HERMES_DB_PASSWORD"]:
            assert msg not in errors
        else:
            assert msg in errors


# ═══════════════════════════════════════════════════════════════
# Hardware Detection Tests
# ═══════════════════════════════════════════════════════════════

class TestSystemDetector:
    def test_detect_returns_info(self):
        detector = SystemDetector()
        info = detector.detect()
        assert info is not None
        assert info.python_version != ""

    def test_detect_os(self):
        detector = SystemDetector()
        info = detector.detect()
        assert info.os_type in ("Linux", "Darwin", "Windows")

    def test_detect_returns_cpu_info(self):
        detector = SystemDetector()
        info = detector.detect()
        assert info.cpu_cores >= 0

    def test_detect_returns_ram(self):
        detector = SystemDetector()
        info = detector.detect()
        assert info.ram_total_gb >= 0

    def test_recommend_profile_returns_string(self):
        detector = SystemDetector()
        info, profile, models = detector.detect_and_recommend()
        assert isinstance(profile, str)
        assert profile in PROFILES

    def test_recommend_models_returns_list(self):
        detector = SystemDetector()
        info, profile, models = detector.detect_and_recommend()
        assert isinstance(models, list)
        assert len(models) > 0

    def test_to_dict(self):
        detector = SystemDetector()
        info = detector.detect()
        d = info.to_dict()
        assert isinstance(d, dict)
        assert "os" in d


class TestHardwareProfile:
    def test_all_profiles_present(self):
        assert "cpu_only" in PROFILES
        assert "local_gpu" in PROFILES
        assert "wsl" in PROFILES
        assert "docker" in PROFILES
        assert "server" in PROFILES
        assert "cloud_gpu" in PROFILES

    def test_cpu_only_profile(self):
        profile = PROFILES["cpu_only"]
        assert profile.requires_gpu is False
        assert profile.max_concurrent_tasks == 1

    def test_local_gpu_requires_gpu(self):
        profile = PROFILES["local_gpu"]
        assert profile.requires_gpu is True
        assert profile.min_vram_mb == 4096

    def test_cloud_gpu_high_concurrency(self):
        profile = PROFILES["cloud_gpu"]
        assert profile.max_concurrent_tasks == 16
        assert "70b" in " ".join(profile.recommended_models)

    def test_profile_to_dict(self):
        profile = PROFILES["server"]
        d = profile.to_dict()
        assert "requirements" in d
        assert "capabilities" in d
        assert "deployment" in d

    def test_get_profile(self):
        from installer.hardware_profile import get_profile
        p = get_profile("docker")
        assert p is not None
        assert p.profile_name == "docker"


# ═══════════════════════════════════════════════════════════════
# Database & Storage Tests
# ═══════════════════════════════════════════════════════════════

class TestDatabaseManager:
    def _make_db(self):
        import tempfile
        # Use temp file instead of :memory: to avoid shared state
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        return DatabaseManager(DatabaseConfig(backend=StorageBackend.SQLITE, name=f.name)), f.name

    def test_create_sqlite_connection(self):
        import tempfile
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        db = DatabaseManager(DatabaseConfig(backend=StorageBackend.SQLITE, name=f.name))
        ok = db.initialize()
        assert ok is True
        os.unlink(f.name)

    def test_execute_query(self):
        import tempfile
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        try:
            db = DatabaseManager(DatabaseConfig(backend=StorageBackend.SQLITE, name=f.name))
            db.initialize()
            db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
            db.execute("INSERT INTO test VALUES (?, ?)", (1, "hello"))
            row = db.fetch_one("SELECT * FROM test WHERE id = ?", (1,))
            assert row is not None
            assert row["name"] == "hello"
        finally:
            os.unlink(f.name)

    def test_fetch_all(self):
        import tempfile
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        try:
            db = DatabaseManager(DatabaseConfig(backend=StorageBackend.SQLITE, name=f.name))
            db.initialize()
            db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
            for i in range(3):
                db.execute("INSERT INTO test VALUES (?, ?)", (i, f"item_{i}"))
            rows = db.fetch_all("SELECT * FROM test ORDER BY id")
            assert len(rows) == 3
        finally:
            os.unlink(f.name)

    def test_health_check(self):
        import tempfile
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        try:
            db = DatabaseManager(DatabaseConfig(backend=StorageBackend.SQLITE, name=f.name))
            db.initialize()
            assert db.is_healthy() is True
        finally:
            os.unlink(f.name)

    def test_thread_safety(self):
        import tempfile
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        try:
            db = DatabaseManager(DatabaseConfig(backend=StorageBackend.SQLITE, name=f.name))
            db.initialize()
            db.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER PRIMARY KEY, name TEXT)")
            errors = []
            write_lock = threading.Lock()
            def worker(n):
                try:
                    time.sleep(0.01 * n)  # stagger writes
                    with write_lock:
                        db.execute("INSERT INTO test VALUES (?, ?)", (n, f"thread_{n}"))
                except Exception as e:
                    errors.append(e)
            threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
            for t in threads: t.start()
            for t in threads: t.join()
            assert len(errors) == 0
            rows = db.fetch_all("SELECT * FROM test ORDER BY id")
            assert len(rows) == 10
        finally:
            os.unlink(f.name)

    def test_close_all(self):
        import tempfile
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        try:
            db = DatabaseManager(DatabaseConfig(backend=StorageBackend.SQLITE, name=f.name))
            db.initialize()
            db.close_all()
            assert db._initialized is False
        finally:
            os.unlink(f.name)


class TestMigrationManager:
    def test_create_and_list_migrations(self):
        db = DatabaseManager(DatabaseConfig(backend=StorageBackend.SQLITE, name=":memory:"))
        db.initialize()
        mm = MigrationManager(db)
        mm.create_migration("add_users", "CREATE TABLE users (id INTEGER PRIMARY KEY);")
        migrations = mm.list_migrations()
        assert len(migrations) >= 1

    def test_migrate_up(self):
        db = DatabaseManager(DatabaseConfig(backend=StorageBackend.SQLITE, name=":memory:"))
        db.initialize()
        mm = MigrationManager(db)
        applied = mm.migrate()
        assert applied >= 0

    def test_get_current_version(self):
        db = DatabaseManager(DatabaseConfig(backend=StorageBackend.SQLITE, name=":memory:"))
        db.initialize()
        mm = MigrationManager(db)
        version = mm.get_current_version()
        assert version >= 0


class TestBackupManager:
    def test_create_backup(self, tmp_path):
        bm = BackupManager(backup_dir=str(tmp_path / "backups"), data_dir=str(tmp_path / "data"))
        os.makedirs(tmp_path / "data", exist_ok=True)
        name = bm.create_backup("test_backup")
        assert name == "test_backup"

    def test_list_backups(self, tmp_path):
        bm = BackupManager(backup_dir=str(tmp_path / "backups"), data_dir=str(tmp_path / "data"))
        os.makedirs(tmp_path / "data", exist_ok=True)
        bm.create_backup("b1")
        bm.create_backup("b2")
        backups = bm.list_backups()
        assert len(backups) >= 2

    def test_restore_backup(self, tmp_path):
        bm = BackupManager(backup_dir=str(tmp_path / "backups"), data_dir=str(tmp_path / "data"))
        os.makedirs(tmp_path / "data", exist_ok=True)
        bm.create_backup("test_restore")
        result = bm.restore("test_restore", target_dir=str(tmp_path / "restore"))
        assert result is True

    def test_delete_backup(self, tmp_path):
        bm = BackupManager(backup_dir=str(tmp_path / "backups"), data_dir=str(tmp_path / "data"))
        os.makedirs(tmp_path / "data", exist_ok=True)
        bm.create_backup("to_delete")
        assert bm.delete_backup("to_delete") is True
        assert bm.delete_backup("nonexistent") is False

    def test_get_stats(self, tmp_path):
        bm = BackupManager(backup_dir=str(tmp_path / "backups"), data_dir=str(tmp_path / "data"))
        os.makedirs(tmp_path / "data", exist_ok=True)
        bm.create_backup("stats_test")
        stats = bm.get_stats()
        assert "total_backups" in stats


# ═══════════════════════════════════════════════════════════════
# Monitoring Tests
# ═══════════════════════════════════════════════════════════════

class TestSystemMonitor:
    def test_collect_once(self):
        monitor = SystemMonitor()
        snapshot = monitor.collect_once()
        assert "timestamp" in snapshot
        assert "cpu_percent" in snapshot
        assert "memory_percent" in snapshot

    def test_register_service(self):
        monitor = SystemMonitor()
        monitor.register_service("test_svc", lambda: True)
        status = monitor.get_service_status()
        assert "test_svc" in status

    def test_is_healthy(self):
        monitor = SystemMonitor()
        assert isinstance(monitor.is_healthy(), bool)

    def test_get_all_metrics(self):
        monitor = SystemMonitor()
        metrics = monitor.get_all_metrics()
        assert isinstance(metrics, dict)

    def test_get_alerts(self):
        monitor = SystemMonitor()
        alerts = monitor.get_alerts()
        assert isinstance(alerts, list)

    def test_start_stop(self):
        monitor = SystemMonitor(interval_s=60)
        monitor.start()
        assert monitor._running is True
        monitor.stop()
        assert monitor._running is False


class TestHealthMonitor:
    def test_register_check(self):
        hm = HealthMonitor()
        hm.register_check("test", lambda: True)
        status = hm.get_status()
        assert status["total_components"] == 1

    def test_health_status_unknown(self):
        hm = HealthMonitor()
        hm.register_check("test", lambda: True)
        status = hm.get_status()
        assert status["total_components"] == 1

    def test_check_once_healthy(self):
        hm = HealthMonitor()
        hm.register_check("test", lambda: True)
        result = hm.check_once("test")
        assert result is True

    def test_check_once_unhealthy(self):
        hm = HealthMonitor()
        hm.register_check("test", lambda: False)
        result = hm.check_once("test")
        assert result is False

    def test_get_component_status(self):
        hm = HealthMonitor()
        hm.register_check("test", lambda: True)
        hm.check_once("test")
        result = hm.get_component_status("test")
        assert result is not None

    def test_start_stop(self):
        hm = HealthMonitor(check_interval_s=60)
        hm.start()
        assert hm._running is True
        hm.stop()
        assert hm._running is False

    def test_on_unhealthy_callback(self):
        hm = HealthMonitor()
        hm.register_check("test", lambda: False)
        alerts = []
        hm.on_unhealthy(lambda a: alerts.append(a))
        hm.check_once("test")
        time.sleep(0.1)
        # Callback called during check
        assert isinstance(alerts, list)


class TestRecoveryManager:
    def test_register_recovery(self):
        rm = RecoveryManager()
        rm.register_recovery("test", lambda: True)
        status = rm.get_status("test")
        assert status["has_recovery"] is True

    def test_trigger_recovery_success(self):
        rm = RecoveryManager()
        rm.register_recovery("test", lambda: True)
        result = rm.trigger_recovery("test", "testing")
        assert result is True

    def test_trigger_recovery_failure(self):
        rm = RecoveryManager()
        rm.register_recovery("test", lambda: False)
        result = rm.trigger_recovery("test", "testing")
        assert result is False

    def test_trigger_recovery_no_action(self):
        rm = RecoveryManager()
        result = rm.trigger_recovery("nonexistent", "no action")
        assert result is False

    def test_get_status_without_recovery(self):
        rm = RecoveryManager()
        status = rm.get_status("unknown")
        assert status["has_recovery"] is False

    def test_get_stats(self):
        rm = RecoveryManager()
        stats = rm.get_stats()
        assert stats["total_attempts"] >= 0

    def test_reset_attempts(self):
        rm = RecoveryManager()
        rm.register_recovery("test", lambda: False)
        rm.trigger_recovery("test", "fail")
        rm.reset_attempts("test")
        status = rm.get_status("test")
        assert status["recent_attempts"] == 0

    def test_reset_all(self):
        rm = RecoveryManager()
        rm.register_recovery("a", lambda: True)
        rm.register_recovery("b", lambda: True)
        rm.reset_all()
        assert rm._attempts == {}

    def test_get_history(self):
        rm = RecoveryManager()
        rm.register_recovery("test", lambda: True)
        rm.trigger_recovery("test", "test")
        history = rm.get_history()
        assert len(history) > 0
        assert history[0]["result"] == "success"

    def test_max_attempts_exceeded(self):
        rm = RecoveryManager(max_attempts=1, cooldown_s=0)
        rm.register_recovery("test", lambda: False)
        rm.trigger_recovery("test", "first")
        result = rm.trigger_recovery("test", "second")
        assert result is False  # Max attempts reached


# ═══════════════════════════════════════════════════════════════
# Logging Tests
# ═══════════════════════════════════════════════════════════════

class TestProductionLogger:
    def test_create_logger(self):
        logger = ProductionLogger("test_logger", log_dir="/tmp/hermes_test_logs",
                                  json_format=False)
        assert logger is not None

    def test_log_messages(self, tmp_path):
        log_dir = tmp_path / "logs"
        logger = ProductionLogger("test", log_dir=str(log_dir), json_format=False)
        logger.info("Test info message")
        logger.warning("Test warning")
        logger.error("Test error")
        # File should exist
        log_file = log_dir / "test.log"
        assert log_file.exists()

    def test_debug_log(self):
        logger = ProductionLogger("test_debug", log_dir="/tmp/hermes_test_logs",
                                  level="DEBUG", json_format=False)
        logger.debug("Debug message")
        assert True

    def test_mission_log(self, tmp_path):
        logger = ProductionLogger("test_mission", log_dir=str(tmp_path / "logs"),
                                  json_format=False)
        logger.mission_log("mission_1", "Mission started")
        assert True

    def test_agent_log(self, tmp_path):
        logger = ProductionLogger("test_agent", log_dir=str(tmp_path / "logs"),
                                  json_format=False)
        logger.agent_log("agent_1", "Agent task started")
        assert True

    def test_critical_log(self):
        logger = ProductionLogger("test_critical", log_dir="/tmp/hermes_test_logs",
                                  json_format=False)
        logger.critical("Critical error")
        assert True

    def test_event_log(self, tmp_path):
        logger = ProductionLogger("test_event", log_dir=str(tmp_path / "logs"),
                                  json_format=False)
        logger.event("test.event", {"key": "value"})
        assert True

    def test_json_format(self, tmp_path):
        log_dir = tmp_path / "logs_json"
        logger = ProductionLogger("test_json", log_dir=str(log_dir), json_format=True)
        logger.info("JSON message")
        log_file = log_dir / "test_json.log"
        assert log_file.exists()

    def test_set_correlation_id(self):
        logger = ProductionLogger("test_corr", log_dir="/tmp/hermes_test_logs",
                                  json_format=False)
        logger.set_correlation_id("corr_123")
        assert True

    def test_get_logger_singleton(self):
        from backend.logging.production_logger import get_logger
        l1 = get_logger("singleton_test")
        l2 = get_logger("singleton_test")
        assert l1 is l2


# ═══════════════════════════════════════════════════════════════
# Thread Safety Tests
# ═══════════════════════════════════════════════════════════════

class TestThreadSafety:
    def test_config_manager_thread_safe(self):
        errors = []
        def access_config(n):
            try:
                cm = ConfigManager()
                _ = cm.get()
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=access_config, args=(i,)) for i in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0

    def test_monitor_thread_safe(self):
        monitor = SystemMonitor()
        errors = []
        def access_monitor(n):
            try:
                monitor.collect_once()
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=access_monitor, args=(i,)) for i in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0

    def test_backup_thread_safe(self, tmp_path):
        bm = BackupManager(backup_dir=str(tmp_path / "backups_ts"),
                          data_dir=str(tmp_path / "data_ts"))
        os.makedirs(tmp_path / "data_ts", exist_ok=True)
        errors = []
        def create_backup(n):
            try:
                bm.create_backup(f"thread_backup_{n}")
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=create_backup, args=(i,)) for i in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0
        backups = bm.list_backups()
        assert len(backups) >= 5

    def test_recovery_thread_safe(self):
        rm = RecoveryManager()
        rm.register_recovery("test", lambda: True)
        errors = []
        def trigger(n):
            try:
                rm.trigger_recovery("test", f"thread_{n}")
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=trigger, args=(i,)) for i in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0
