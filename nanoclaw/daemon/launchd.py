"""macOS LaunchAgent backend."""

import plistlib
import subprocess
from pathlib import Path

from nanoclaw.daemon.base import ServiceBackend, ServiceInfo

_LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
LABEL = "com.nanoclaw.gateway"
PLIST_PATH = _LAUNCH_AGENTS_DIR / f"{LABEL}.plist"


class LaunchdBackend(ServiceBackend):
    """Manages a macOS LaunchAgent plist for the nanoclaw gateway."""

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
        plist: dict = {
            "Label": LABEL,
            "ProgramArguments": command,
            "KeepAlive": {"SuccessfulExit": False},
            "RunAtLoad": False,
            "StandardOutPath": str(log_out),
            "StandardErrorPath": str(log_err),
        }
        if env:
            plist["EnvironmentVariables"] = env

        PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(PLIST_PATH, "wb") as f:
            plistlib.dump(plist, f)

        # Register the agent (idempotent: unload first if already loaded)
        _launchctl("unload", ignore_errors=True)
        _launchctl("load")
        return PLIST_PATH

    def uninstall(self) -> None:
        if PLIST_PATH.exists():
            _launchctl("unload", ignore_errors=True)
            PLIST_PATH.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------

    def start(self) -> None:
        _launchctl("load")

    def stop(self) -> None:
        _launchctl("unload")

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def is_running(self) -> bool:
        pid = self._get_pid()
        return pid is not None and pid > 0

    def get_info(self) -> ServiceInfo:
        return ServiceInfo(
            name=LABEL,
            service_file=PLIST_PATH if PLIST_PATH.exists() else None,
            installed=PLIST_PATH.exists(),
            running=self.is_running(),
            pid=self._get_pid(),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_pid(self) -> int | None:
        """Parse PID from ``launchctl list <label>``."""
        try:
            result = subprocess.run(
                ["launchctl", "list", LABEL],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return None
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 3 and parts[2] == '"PID"':
                    return int(parts[0])
                # Typical format: "<PID>\t<status>\t<label>"
                if len(parts) >= 1 and parts[0].isdigit():
                    return int(parts[0])
            # Also check the first line after header
            lines = result.stdout.strip().splitlines()
            for line in lines:
                # launchctl list output: "PID\tStatus\tLabel" or key-value pairs
                if '"PID"' in line:
                    for part in line.split():
                        if part.isdigit():
                            return int(part)
            return None
        except (OSError, ValueError):
            return None


def _launchctl(
    verb: str,
    *,
    use_label: bool = False,
    ignore_errors: bool = False,
) -> None:
    """Run ``launchctl <verb> ...``."""
    if use_label:
        cmd = ["launchctl", verb, LABEL]
    else:
        cmd = ["launchctl", verb, str(PLIST_PATH)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 and not ignore_errors:
        msg = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"launchctl {verb} failed: {msg}")
