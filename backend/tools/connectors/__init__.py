"""Connector abstractions (HOS-049)."""

from .browser import BrowserConnector
from .database import DatabaseConnector
from .docker import DockerConnector
from .filesystem import FilesystemConnector
from .github import GitHubConnector
from .gitlab import GitLabConnector
from .klaatcode import KlaatCodeClient, KlaatCodeMCPAdapter
from .rest_api import RestAPIConnector

__all__ = [
    "GitHubConnector", "GitLabConnector", "DockerConnector",
    "DatabaseConnector", "FilesystemConnector", "RestAPIConnector",
    "BrowserConnector",
    "KlaatCodeClient", "KlaatCodeMCPAdapter",
]
