"""Platform-aware daemon manager facade."""

import os
import platform
import shutil
import sys
from pathlib import Path

from nanobot.daemon.base import ServiceBackend, ServiceInfo

# Environment variable patterns to forward into the service
_ENV_PATTERNS: list[str] = [
    "NANOBOT_*",
    "OPENAI_*",
    "ANTHROPIC_*",
    "OPENROUTER_*",
    "DEEPSEEK_*",
    "GROQ_*",
    "GOOGLE_*",
    "BRAVE_*",
]

# Always forward these base env vars
_BASE_ENV_KEYS: list[str] = ["PATH", "HOME", "USER", "LANG"]


class DaemonManager:
    """Facade: detects OS, resolves paths, delegates to the correct backend."""

    def __init__(self, extra_env_passthrough: list[str] | None = None):
        self._backend = self._detect_backend()
        self._extra_passthrough = extra_env_passthrough or []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def install(self) -> Path:
        """Generate and register the OS service. Returns path to service file."""
        command = self._resolve_nanobot_command()
        env = self._collect_env()
        log_out, log_err = self._log_paths()
        log_out.parent.mkdir(parents=True, exist_ok=True)
        return self._backend.install(command, env, log_out, log_err)

    def uninstall(self) -> None:
        self._backend.uninstall()

    def start(self) -> None:
        info = self._backend.get_info()
        if not info.installed:
            raise RuntimeError("Service not installed. Run 'nanobot gateway install' first.")
        self._backend.start()

    def stop(self) -> None:
        info = self._backend.get_info()
        if not info.installed:
            raise RuntimeError("Service not installed.")
        self._backend.stop()

    def restart(self) -> None:
        info = self._backend.get_info()
        if not info.installed:
            raise RuntimeError("Service not installed. Run 'nanobot gateway install' first.")
        if info.running:
            self._backend.stop()
        self._backend.start()

    def is_running(self) -> bool:
        return self._backend.is_running()

    def get_info(self) -> ServiceInfo:
        return self._backend.get_info()

    def log_paths(self) -> tuple[Path, Path]:
        """Return (stdout_log, stderr_log) paths."""
        return self._log_paths()

    # ------------------------------------------------------------------
    # Platform detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_backend() -> ServiceBackend:
        system = platform.system()
        if system == "Darwin":
            from nanobot.daemon.launchd import LaunchdBackend

            return LaunchdBackend()
        if system == "Linux":
            if not shutil.which("systemctl"):
                raise RuntimeError(
                    "systemctl not found. On this Linux system, use foreground mode: "
                    "'nanobot gateway' (without subcommand)."
                )
            from nanobot.daemon.systemd import SystemdBackend

            return SystemdBackend()
        raise RuntimeError(
            f"Daemon mode is not supported on {system}. "
            "Use foreground mode: 'nanobot gateway' (without subcommand)."
        )

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_nanobot_command() -> list[str]:
        """Find the best way to invoke ``nanobot gateway run``."""
        # Strategy 1: look for nanobot binary next to current Python
        bin_dir = Path(sys.executable).parent
        candidate = bin_dir / "nanobot"
        if candidate.is_file():
            return [str(candidate), "gateway", "run"]

        # Strategy 2: shutil.which
        which = shutil.which("nanobot")
        if which:
            return [which, "gateway", "run"]

        # Strategy 3: python -m nanobot
        return [sys.executable, "-m", "nanobot", "gateway", "run"]

    # ------------------------------------------------------------------
    # Environment
    # ------------------------------------------------------------------

    def _collect_env(self) -> dict[str, str]:
        """Build env dict to embed in the service file."""
        env: dict[str, str] = {}

        # Base vars
        for key in _BASE_ENV_KEYS:
            val = os.environ.get(key)
            if val:
                env[key] = val

        # Pattern-matched vars
        all_patterns = _ENV_PATTERNS + self._extra_passthrough
        for key, val in os.environ.items():
            if any(self._matches(key, pat) for pat in all_patterns):
                env[key] = val

        return env

    @staticmethod
    def _matches(key: str, pattern: str) -> bool:
        """Simple glob match (only supports trailing ``*``)."""
        if pattern.endswith("*"):
            return key.startswith(pattern[:-1])
        return key == pattern

    # ------------------------------------------------------------------
    # Logs
    # ------------------------------------------------------------------

    @staticmethod
    def _log_paths() -> tuple[Path, Path]:
        log_dir = Path.home() / ".nanobot" / "logs"
        return log_dir / "gateway.out.log", log_dir / "gateway.err.log"
