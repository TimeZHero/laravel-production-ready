"""
Test that the correct processes are running for FrankenPHP containers.

FrankenPHP bundles Caddy – there is no separate nginx or supervisor process.
Uses /proc to inspect running processes (ps is not available on Debian minimal).
"""


def _get_running_cmdlines(container) -> str:
    """Read all /proc/*/cmdline entries (NUL-delimited, convert to spaces)."""
    return container.exec(
        "sh -c 'for f in /proc/[0-9]*/cmdline; do tr \"\\0\" \" \" < \"$f\" 2>/dev/null; echo; done'"
    )


def _has_process(output: str, name: str) -> bool:
    """Check if a process matching `name` appears in cmdline output."""
    for line in output.splitlines():
        if name in line:
            return True
    return False


class TestProductionProcesses:
    """Verify processes in production containers."""

    def test_octane_is_running(self, production_container):
        output = _get_running_cmdlines(production_container)
        assert _has_process(output, "octane") or _has_process(output, "frankenphp"), (
            f"[{production_container.combo_id}] octane/frankenphp not found in processes:\n{output}"
        )

    def test_no_nginx(self, production_container):
        """FrankenPHP should not have nginx."""
        output = _get_running_cmdlines(production_container)
        assert not _has_process(output, "nginx"), (
            f"[{production_container.combo_id}] nginx should not be present in FrankenPHP:\n{output}"
        )

    def test_no_supervisor(self, production_container):
        """FrankenPHP should not have supervisord."""
        output = _get_running_cmdlines(production_container)
        assert not _has_process(output, "supervisord"), (
            f"[{production_container.combo_id}] supervisord should not be present in FrankenPHP:\n{output}"
        )


class TestDevelopmentProcesses:
    """Verify processes in development containers."""

    def test_octane_is_running(self, development_container):
        output = _get_running_cmdlines(development_container)
        assert _has_process(output, "octane") or _has_process(output, "frankenphp"), (
            f"[{development_container.combo_id}] octane/frankenphp not found in processes:\n{output}"
        )

    def test_no_nginx(self, development_container):
        """FrankenPHP should not have nginx."""
        output = _get_running_cmdlines(development_container)
        assert not _has_process(output, "nginx"), (
            f"[{development_container.combo_id}] nginx should not be present in FrankenPHP:\n{output}"
        )

    def test_no_supervisor(self, development_container):
        """FrankenPHP should not have supervisord."""
        output = _get_running_cmdlines(development_container)
        assert not _has_process(output, "supervisord"), (
            f"[{development_container.combo_id}] supervisord should not be present in FrankenPHP:\n{output}"
        )
