"""
Test that the correct processes are running for each ENGINE x TARGET.

Uses `ps aux` instead of `supervisorctl` to avoid requiring a supervisor
unix socket configuration.
"""

import pytest


def _get_running_processes(container) -> str:
    """Get the full `ps aux` output from the container."""
    return container.exec("ps aux")


def _has_process(ps_output: str, name: str) -> bool:
    """Check if a process matching `name` appears in ps output."""
    for line in ps_output.splitlines():
        # Skip the header and the ps/grep commands themselves
        if "PID" in line and "COMMAND" in line:
            continue
        if "ps aux" in line or "grep" in line:
            continue
        if name in line:
            return True
    return False


# =========================================================================
# Production
# =========================================================================


class TestProductionProcesses:
    """Verify processes in production containers."""

    def test_nginx_is_running(self, production_container):
        ps = _get_running_processes(production_container)
        assert _has_process(ps, "nginx"), (
            f"[{production_container.combo_id}] nginx not found in processes:\n{ps}"
        )

    def test_engine_process_is_running(self, production_container):
        ps = _get_running_processes(production_container)

        if production_container.is_fpm:
            assert _has_process(ps, "php-fpm"), (
                f"[{production_container.combo_id}] php-fpm not found:\n{ps}"
            )
        else:
            assert _has_process(ps, "octane"), (
                f"[{production_container.combo_id}] octane not found:\n{ps}"
            )

    def test_no_queue_worker(self, production_container):
        ps = _get_running_processes(production_container)
        assert not _has_process(ps, "queue:work"), (
            f"[{production_container.combo_id}] queue worker should not be in production:\n{ps}"
        )

    def test_no_scheduler(self, production_container):
        ps = _get_running_processes(production_container)
        assert not _has_process(ps, "schedule:"), (
            f"[{production_container.combo_id}] scheduler should not be in production:\n{ps}"
        )


# =========================================================================
# Development
# =========================================================================


class TestDevelopmentProcesses:
    """Verify processes in development containers."""

    def test_nginx_is_running(self, development_container):
        ps = _get_running_processes(development_container)
        assert _has_process(ps, "nginx"), (
            f"[{development_container.combo_id}] nginx not found:\n{ps}"
        )

    def test_engine_process_is_running(self, development_container):
        ps = _get_running_processes(development_container)

        if development_container.is_fpm:
            assert _has_process(ps, "php-fpm"), (
                f"[{development_container.combo_id}] php-fpm not found:\n{ps}"
            )
        else:
            assert _has_process(ps, "octane"), (
                f"[{development_container.combo_id}] octane not found:\n{ps}"
            )

    def test_queue_worker_is_running(self, development_container):
        ps = _get_running_processes(development_container)
        assert _has_process(ps, "queue:work"), (
            f"[{development_container.combo_id}] queue worker not found:\n{ps}"
        )

    def test_scheduler_is_running(self, development_container):
        ps = _get_running_processes(development_container)
        assert _has_process(ps, "schedule:"), (
            f"[{development_container.combo_id}] scheduler not found:\n{ps}"
        )
