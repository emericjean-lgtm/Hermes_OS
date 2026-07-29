"""Configuration models for Hermes OS (HOS-062)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DeploymentProfile(str, Enum):
    LOCAL_GPU = "local_gpu"
    CPU_ONLY = "cpu_only"
    WSL = "wsl"
    DOCKER = "docker"
    SERVER = "server"
    CLOUD_GPU = "cloud_gpu"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class StorageBackend(str, Enum):
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


class VectorBackend(str, Enum):
    NONE = "none"
    CHROMADB = "chromadb"
    QDRANT = "qdrant"
    PINECONE = "pinecone"


class RuntimeMode(str, Enum):
    LOCAL = "local"
    DISTRIBUTED = "distributed"
    HYBRID = "hybrid"


@dataclass
class DatabaseConfig:
    backend: StorageBackend = StorageBackend.SQLITE
    host: str = "localhost"
    port: int = 5432
    name: str = "hermes_os"
    user: str = "hermes"
    password: str = ""
    pool_size: int = 10
    max_overflow: int = 20
    echo: bool = False
    ssl_mode: str = "prefer"

    @property
    def connection_string(self) -> str:
        if self.backend == StorageBackend.SQLITE:
            return f"sqlite:///{self.name}.db"
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


@dataclass
class RedisConfig:
    host: str = "localhost"
    port: int = 6379
    password: str = ""
    db: int = 0
    socket_timeout_s: int = 5
    retry_on_timeout: bool = True
    max_connections: int = 20


@dataclass
class VectorConfig:
    backend: VectorBackend = VectorBackend.CHROMADB
    host: str = "localhost"
    port: int = 8000
    collection: str = "hermes_embeddings"
    dimension: int = 768
    api_key: str = ""


@dataclass
class SecurityConfig:
    jwt_secret: str = ""
    token_expiry_h: int = 24
    max_login_attempts: int = 5
    lockout_minutes: int = 15
    enable_ssl: bool = False
    ssl_cert_path: str = ""
    ssl_key_path: str = ""


@dataclass
class MonitoringConfig:
    enabled: bool = True
    metrics_port: int = 9090
    health_check_interval_s: int = 30
    alert_on_crash: bool = True
    alert_on_high_memory: bool = True
    memory_threshold_mb: int = 8192
    cpu_threshold_pct: float = 90.0
    recovery_attempts: int = 3
    recovery_cooldown_s: int = 60


@dataclass
class LoggingConfig:
    level: LogLevel = LogLevel.INFO
    json_format: bool = True
    log_dir: str = "logs"
    max_file_size_mb: int = 100
    backup_count: int = 10
    correlation_id: bool = True
    console_output: bool = True
    file_output: bool = True


@dataclass
class RuntimeConfig:
    mode: RuntimeMode = RuntimeMode.LOCAL
    default_model: str = "llama3.2:3b"
    max_concurrent_tasks: int = 4
    task_timeout_s: int = 300
    enable_gpu: bool = True
    enable_cpu_fallback: bool = True
    memory_limit_mb: int = 4096
    cache_size_mb: int = 1024


@dataclass
class HermesConfig:
    """Root configuration for Hermes OS."""

    profile: DeploymentProfile = DeploymentProfile.LOCAL_GPU
    version: str = "1.0.0"
    debug: bool = False

    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    vector: VectorConfig = field(default_factory=VectorConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    frontend_url: str = "http://localhost:3000"
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:3000"])
    workspace_dir: str = "workspace"
    data_dir: str = "data"

    def to_dict(self) -> dict[str, Any]:
        return {k: str(v) if isinstance(v, Enum) else v for k, v in self.__dict__.items()}

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.security.jwt_secret and len(self.security.jwt_secret) < 16:
            errors.append("JWT secret must be at least 16 characters")
        if self.api_port < 1 or self.api_port > 65535:
            errors.append(f"Invalid API port: {self.api_port}")
        if self.runtime.max_concurrent_tasks < 1:
            errors.append("max_concurrent_tasks must be >= 1")
        return errors
