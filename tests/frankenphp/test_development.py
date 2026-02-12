"""
Test development-specific configurations for FrankenPHP.
"""


class TestDevelopmentPHP:
    """Development PHP configuration."""

    def test_opcache_validate_timestamps_is_enabled(self, development_container):
        value = development_container.php_ini_get("opcache.validate_timestamps")
        assert value in ("1", "On"), (
            f"[{development_container.combo_id}] opcache.validate_timestamps "
            f"should be enabled in development, got: {value}"
        )

    def test_xdebug_is_installed(self, development_container):
        modules = development_container.php_modules()
        assert "xdebug" in modules, (
            f"[{development_container.combo_id}] xdebug should be installed in development"
        )


class TestDevelopmentOctane:
    """Development octane-specific env vars."""

    def test_octane_https_is_false(self, development_container):
        output = development_container.exec("env")
        env_lines = output.splitlines()
        octane_https = [l for l in env_lines if l.startswith("OCTANE_HTTPS=")]
        assert octane_https, (
            f"[{development_container.combo_id}] OCTANE_HTTPS not found in env"
        )
        assert octane_https[0] == "OCTANE_HTTPS=false", (
            f"[{development_container.combo_id}] Expected OCTANE_HTTPS=false, got {octane_https[0]}"
        )


class TestDevelopmentUser:
    """Development container should run as non-root."""

    def test_runs_as_non_root(self, development_container):
        output = development_container.exec_as_app_user("id")
        assert "uid=0" not in output, (
            f"[{development_container.combo_id}] Container should not run as root. id output: {output}"
        )
