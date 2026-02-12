"""Abstract base for OS service backends."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ServiceInfo:
    """Status snapshot of the daemon service."""

    name: str
    service_file: Path | None = None
    installed: bool = False
    running: bool = False
    pid: int | None = None


class ServiceBackend(ABC):
    """ABC that each OS-specific backend implements."""

    @abstractmethod
    def install(
        self,
        command: list[str],
        env: dict[str, str],
        log_out: Path,
        log_err: Path,
    ) -> Path:
        """Write service definition and register it. Returns path to service file."""

    @abstractmethod
    def uninstall(self) -> None:
        """Stop (if running) and remove the service definition."""

    @abstractmethod
    def start(self) -> None:
        """Start the service via the OS service manager."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the service via the OS service manager."""

    @abstractmethod
    def is_running(self) -> bool:
        """Return True if the service is currently active."""

    @abstractmethod
    def get_info(self) -> ServiceInfo:
        """Return a status snapshot."""
