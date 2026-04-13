"""Sandboxing — wraps shell commands with bubblewrap or firejail."""

import shutil
from dataclasses import dataclass
from typing import Literal


@dataclass
class SandboxConfig:
    """Configuration for command sandboxing."""

    enabled: bool = False
    backend: Literal["bubblewrap", "firejail", "none"] = "none"
    allow_network: bool = False
    allow_home_write: bool = False
    timeout_s: int = 30


def is_sandbox_available(backend: str) -> bool:
    """Check whether the given sandbox backend binary is installed."""
    if backend == "bubblewrap":
        return shutil.which("bwrap") is not None
    if backend == "firejail":
        return shutil.which("firejail") is not None
    if backend == "none":
        return True
    return False


def sandbox_command(cmd: str, config: SandboxConfig) -> list[str]:
    """Wrap *cmd* according to *config*, returning an argv list.

    If sandboxing is disabled or the backend is ``"none"``, the command is
    returned as a plain ``sh -c`` invocation.
    """
    if not config.enabled or config.backend == "none":
        return ["sh", "-c", cmd]

    if config.backend == "bubblewrap":
        return _bwrap_argv(cmd, config)

    if config.backend == "firejail":
        return _firejail_argv(cmd, config)

    # Unknown backend — fall back to unsandboxed execution.
    return ["sh", "-c", cmd]


# ── private helpers ──────────────────────────────────────────────────


def _bwrap_argv(cmd: str, config: SandboxConfig) -> list[str]:
    argv = [
        "bwrap",
        "--ro-bind", "/", "/",
        "--dev", "/dev",
        "--proc", "/proc",
        "--tmpfs", "/tmp",
    ]

    if config.allow_home_write:
        import os

        home = os.path.expanduser("~")
        argv += ["--bind", home, home]

    if not config.allow_network:
        argv.append("--unshare-net")

    argv += [
        "--unshare-pid",
        "--die-with-parent",
        "--",
        "sh", "-c", cmd,
    ]
    return argv


def _firejail_argv(cmd: str, config: SandboxConfig) -> list[str]:
    argv = ["firejail", "--quiet"]

    if not config.allow_home_write:
        argv.append("--private")

    if not config.allow_network:
        argv.append("--net=none")

    argv += ["--", "sh", "-c", cmd]
    return argv
