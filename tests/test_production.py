"""
Test production-specific configurations across all engines.
"""

import pytest


class TestProductionNginx:
    """Production nginx configuration."""

    def test_sendfile_is_enabled(self, production_container):
        output = production_container.exec("nginx -T")
        assert "sendfile on" in output, (
            f"[{production_container.combo_id}] sendfile should be 'on' in production"
        )


class TestProductionPHP:
    """Production PHP configuration."""

    def test_opcache_validate_timestamps_is_disabled(self, production_container):
        output = production_container.exec("php -i")
        for line in output.splitlines():
            if "opcache.validate_timestamps" in line:
                # PHP reports "0" or "Off" depending on the directive type
                disabled_values = ("=> 0 =>", "=> Off =>", "=> 0", "=> Off")
                assert any(v in line for v in disabled_values), (
                    f"[{production_container.combo_id}] opcache.validate_timestamps "
                    f"should be disabled in production, got: {line.strip()}"
                )
                return
        pytest.fail(
            f"[{production_container.combo_id}] opcache.validate_timestamps not found in php -i"
        )

    def test_xdebug_is_not_installed(self, production_container):
        output = production_container.exec("php -m")
        modules = output.lower().splitlines()
        assert "xdebug" not in modules, (
            f"[{production_container.combo_id}] xdebug should NOT be installed in production"
        )


class TestProductionOctane:
    """Production octane-specific env vars."""

    def test_octane_https_is_true(self, production_container):
        if not production_container.is_octane:
            pytest.skip("Only applies to octane engines")

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
