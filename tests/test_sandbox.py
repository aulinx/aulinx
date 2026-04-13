"""Tests for the sandbox module."""

from aulinx.sandbox import SandboxConfig, is_sandbox_available, sandbox_command


class TestSandboxConfigDefaults:
    def test_defaults(self):
        cfg = SandboxConfig()
        assert cfg.enabled is False
        assert cfg.backend == "none"
        assert cfg.allow_network is False
        assert cfg.allow_home_write is False
        assert cfg.timeout_s == 30


class TestSandboxCommandNone:
    def test_backend_none(self):
        cfg = SandboxConfig(enabled=True, backend="none")
        argv = sandbox_command("echo hi", cfg)
        assert argv == ["sh", "-c", "echo hi"]

    def test_disabled_ignores_backend(self):
        cfg = SandboxConfig(enabled=False, backend="bubblewrap")
        argv = sandbox_command("echo hi", cfg)
        assert argv == ["sh", "-c", "echo hi"]


class TestSandboxCommandBubblewrap:
    def test_basic_bwrap(self):
        cfg = SandboxConfig(enabled=True, backend="bubblewrap")
        argv = sandbox_command("ls /", cfg)
        assert argv[0] == "bwrap"
        assert "--ro-bind" in argv
        assert "--die-with-parent" in argv
        assert "--unshare-net" in argv
        assert argv[-3:] == ["sh", "-c", "ls /"]

    def test_bwrap_allow_network(self):
        cfg = SandboxConfig(enabled=True, backend="bubblewrap", allow_network=True)
        argv = sandbox_command("curl example.com", cfg)
        assert "--unshare-net" not in argv

    def test_bwrap_allow_home_write(self):
        cfg = SandboxConfig(
            enabled=True, backend="bubblewrap", allow_home_write=True
        )
        argv = sandbox_command("touch ~/file", cfg)
        assert "--bind" in argv
        # --ro-bind should still be present for /
        assert "--ro-bind" in argv

    def test_bwrap_deny_home_write(self):
        cfg = SandboxConfig(
            enabled=True, backend="bubblewrap", allow_home_write=False
        )
        argv = sandbox_command("touch ~/file", cfg)
        assert "--bind" not in argv


class TestSandboxCommandFirejail:
    def test_basic_firejail(self):
        cfg = SandboxConfig(enabled=True, backend="firejail")
        argv = sandbox_command("ls /", cfg)
        assert argv[0] == "firejail"
        assert "--quiet" in argv
        assert "--private" in argv
        assert "--net=none" in argv
        assert argv[-3:] == ["sh", "-c", "ls /"]

    def test_firejail_allow_network(self):
        cfg = SandboxConfig(enabled=True, backend="firejail", allow_network=True)
        argv = sandbox_command("curl example.com", cfg)
        assert "--net=none" not in argv

    def test_firejail_allow_home_write(self):
        cfg = SandboxConfig(
            enabled=True, backend="firejail", allow_home_write=True
        )
        argv = sandbox_command("touch ~/file", cfg)
        assert "--private" not in argv


class TestIsSandboxAvailable:
    def test_none_always_available(self):
        assert is_sandbox_available("none") is True

    def test_unknown_backend(self):
        assert is_sandbox_available("unknown_xyz") is False

    def test_bubblewrap_returns_bool(self):
        result = is_sandbox_available("bubblewrap")
        assert isinstance(result, bool)

    def test_firejail_returns_bool(self):
        result = is_sandbox_available("firejail")
        assert isinstance(result, bool)


class TestSecurityConfig:
    """Verify SecurityConfig is importable and has correct defaults."""

    def test_import_security_config(self):
        from aulinx.config import SecurityConfig

        cfg = SecurityConfig()
        assert cfg.sandbox_enabled is False
        assert cfg.sandbox_backend == "none"
        assert cfg.sandbox_allow_network is False
        assert cfg.sandbox_allow_home_write is False
        assert cfg.sandbox_timeout_s == 30

    def test_config_has_security(self):
        from aulinx.config import Config, SecurityConfig

        config = Config()
        assert isinstance(config.security, SecurityConfig)
