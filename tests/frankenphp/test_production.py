"""
Test production-specific configurations for FrankenPHP.
"""


class TestProductionPHP:
    """Production PHP configuration."""

    def test_opcache_validate_timestamps_is_disabled(self, production_container):
        value = production_container.php_ini_get("opcache.validate_timestamps")
        assert value in ("0", "Off", ""), (
            f"[{production_container.combo_id}] opcache.validate_timestamps "
            f"should be disabled in production, got: {value}"
        )

    def test_xdebug_is_not_installed(self, production_container):
        modules = production_container.php_modules()
        assert "xdebug" not in modules, (
            f"[{production_container.combo_id}] xdebug should NOT be installed in production"
        )


class TestProductionOctane:
    """Production octane-specific env vars."""

    def test_octane_https_is_true(self, production_container):
        output = production_container.exec("env")
        env_lines = output.splitlines()
        octane_https = [l for l in env_lines if l.startswith("OCTANE_HTTPS=")]
        assert octane_https, (
            f"[{production_container.combo_id}] OCTANE_HTTPS not found in env"
        )
        assert octane_https[0] == "OCTANE_HTTPS=true", (
            f"[{production_container.combo_id}] Expected OCTANE_HTTPS=true, got {octane_https[0]}"
        )


class TestProductionUser:
    """Production container should run as non-root."""

    def test_runs_as_non_root(self, production_container):
        output = production_container.exec_as_app_user("id")
        assert "uid=0" not in output, (
            f"[{production_container.combo_id}] Container should not run as root. id output: {output}"
        )
