"""Linux systemd --user backend."""

import subprocess
import textwrap
from pathlib import Path

from nanoclaw.daemon.base import ServiceBackend, ServiceInfo

_UNIT_DIR = Path.home() / ".config" / "systemd" / "user"
UNIT_NAME = "nanoclaw-gateway"
UNIT_PATH = _UNIT_DIR / f"{UNIT_NAME}.service"


class SystemdBackend(ServiceBackend):
    """Manages a systemd user service for the nanoclaw gateway."""

    # ------------------------------------------------------------------
    # Install / Uninstall
    # ------------------------------------------------------------------

    def install(
        self,
        command: list[str],
        env: dict[str, str],
        log_out: Path,
        log_err: Path,
    ) -> Path:
        env_lines = "\n".join(f'Environment="{k}={v}"' for k, v in env.items())

        unit = textwrap.dedent(f"""\
            [Unit]
            Description=Nanoclaw Gateway Service
            After=network.target

            [Service]
            Type=simple
            ExecStart={" ".join(command)}
            Restart=on-failure
            RestartSec=5
            StandardOutput=append:{log_out}
            StandardError=append:{log_err}
            {env_lines}

            [Install]
            WantedBy=default.target
        """)

        _UNIT_DIR.mkdir(parents=True, exist_ok=True)
        UNIT_PATH.write_text(unit)
        _systemctl("daemon-reload")
        return UNIT_PATH

    def uninstall(self) -> None:
        if self.is_running():
            self.stop()
        _systemctl("disable", ignore_errors=True)
        if UNIT_PATH.exists():
            UNIT_PATH.unlink()
        _systemctl("daemon-reload")

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------

    def start(self) -> None:
        _systemctl("start")

    def stop(self) -> None:
        _systemctl("stop")

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def is_running(self) -> bool:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", UNIT_NAME],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() == "active"

    def get_info(self) -> ServiceInfo:
        return ServiceInfo(
            name=UNIT_NAME,
            service_file=UNIT_PATH if UNIT_PATH.exists() else None,
            installed=UNIT_PATH.exists(),
            running=self.is_running(),
            pid=self._get_pid(),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_pid(self) -> int | None:
        """Read MainPID from systemctl show."""
        try:
            result = subprocess.run(
                ["systemctl", "--user", "show", "--property=MainPID", UNIT_NAME],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return None
            # Output: "MainPID=12345"
            for line in result.stdout.splitlines():
                if line.startswith("MainPID="):
                    pid = int(line.split("=", 1)[1])
                    return pid if pid > 0 else None
            return None
        except (OSError, ValueError):
            return None


def _systemctl(verb: str, *, ignore_errors: bool = False) -> None:
    """Run ``systemctl --user <verb> <unit>``."""
    cmd = ["systemctl", "--user", verb]
    if verb != "daemon-reload":
        cmd.append(UNIT_NAME)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 and not ignore_errors:
        msg = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"systemctl {verb} failed: {msg}")
