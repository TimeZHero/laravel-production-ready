"""
Test development-specific configurations across all engines.
"""

import pytest


class TestDevelopmentNginx:
    """Development nginx configuration."""

    def test_sendfile_is_not_enabled(self, development_container):
        output = development_container.exec("nginx -T")
        assert "sendfile on" not in output, (
            f"[{development_container.combo_id}] sendfile should not be 'on' in development "
            f"(enable-sendfile.conf should not be present)"
        )


class TestDevelopmentPHP:
    """Development PHP configuration."""

    def test_opcache_validate_timestamps_is_enabled(self, development_container):
        output = development_container.exec("php -i")
        for line in output.splitlines():
            if "opcache.validate_timestamps" in line:
                # PHP reports "1" or "On" depending on the directive type
                enabled_values = ("=> 1 =>", "=> On =>", "=> 1", "=> On")
                assert any(v in line for v in enabled_values), (
                    f"[{development_container.combo_id}] opcache.validate_timestamps "
                    f"should be enabled in development, got: {line.strip()}"
                )
                return
        pytest.fail(
            f"[{development_container.combo_id}] opcache.validate_timestamps not found in php -i"
        )

    def test_xdebug_is_installed(self, development_container):
        output = development_container.exec("php -m")
        modules = [m.strip().lower() for m in output.splitlines()]
        assert "xdebug" in modules, (
            f"[{development_container.combo_id}] xdebug should be installed in development"
        )


class TestDevelopmentOctane:
    """Development octane-specific env vars."""

    def test_octane_https_is_false(self, development_container):
        if not development_container.is_octane:
            pytest.skip("Only applies to octane engines")

        output = development_container.exec("env")
        env_lines = output.splitlines()
        octane_https = [l for l in env_lines if l.startswith("OCTANE_HTTPS=")]
        assert octane_https, (
            f"[{development_container.combo_id}] OCTANE_HTTPS not found in env"
        )
        assert octane_https[0] == "OCTANE_HTTPS=false", (
            f"[{development_container.combo_id}] Expected OCTANE_HTTPS=false, got {octane_https[0]}"
        )

    def test_octane_options_has_watch(self, development_container):
        if not development_container.is_octane:
            pytest.skip("Only applies to octane engines")

        output = development_container.exec("env")
        env_lines = output.splitlines()
        octane_options = [l for l in env_lines if l.startswith("OCTANE_OPTIONS=")]
        assert octane_options, (
            f"[{development_container.combo_id}] OCTANE_OPTIONS not found in env"
        )
        assert "--watch" in octane_options[0], (
            f"[{development_container.combo_id}] Expected --watch in OCTANE_OPTIONS, "
            f"got {octane_options[0]}"
        )


class TestDevelopmentUser:
    """Development container should run as non-root."""

    def test_runs_as_non_root(self, development_container):
        output = development_container.exec_as_app_user("id")
        assert "uid=0" not in output, (
            f"[{development_container.combo_id}] Container should not run as root. id output: {output}"
        )
